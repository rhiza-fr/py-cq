"""Utilities for executing tools and caching their results.

This module provides helper functions to run command-line tools while
automatically caching their output.  The key capabilities are:

* ``run_tool`` - executes a single tool configuration, captures its
  stdout/stderr/return code, and records a timestamp.
* ``run_tools`` - runs many tool configurations, optionally in parallel,
  and returns the parsed results.

All functions are designed for reuse in data-processing pipelines
where tool invocations may be expensive and should be avoided
when a cached result already exists."""

import logging
import os
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Collection
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, cast

from diskcache import Cache, JSONDisk

from py_cq.context_hash import get_context_hash
from py_cq.localtypes import RawResult, ToolConfig, ToolResult

log = logging.getLogger("cq")

_cache = Cache(Path.home() / ".cache" / "cq", size_limit=100 * 1024 * 1024, disk=JSONDisk)


def _find_project_root(path: Path) -> Path | None:
    """Walk up from path to find the nearest directory containing pyproject.toml."""
    for parent in [path] + list(path.parents):
        candidate = parent if parent.is_dir() else parent.parent
        if (candidate / "pyproject.toml").exists():
            return candidate
    return None


def _dep_in_venv(dep: str, project_root: Path) -> bool:
    """Return True if `dep` is installed in the project's .venv."""
    venv = project_root / ".venv"
    if not venv.exists():
        return False
    for subdir in ("Scripts", "bin"):
        for suffix in ("", ".exe", ".cmd"):
            if (venv / subdir / f"{dep}{suffix}").exists():
                return True
    return False


def _build_exclude_str(exclude_format: str, excludes: list[str], **extra_vars: str) -> str:
    """Builds an exclude string from a list of excludes and a format string."""

    if not exclude_format or not excludes:
        return ""
    parts = []
    for exc in excludes:
        abs_posix_path = Path(exc).resolve().as_posix()
        # shlex.quote prevents shell injection via exclude paths
        parts.append(exclude_format.format(
            path=shlex.quote(exc),
            abs_posix_path=shlex.quote(abs_posix_path),
            **{k: shlex.quote(v) for k, v in extra_vars.items()},
        ))
    return "".join(parts)


def run_tool(tool_config: ToolConfig, context_path: str, excludes: list[str] | None = None) -> RawResult:
    """Runs a tool defined by its configuration and returns the execution result.

    Args:
        tool_config (ToolConfig): Configuration object containing the tool's name and a
            command template.
        context_path (str): Filesystem path that will be substituted into the command
            template via ``context_path`` formatting.

    Returns:
        RawResult: An object holding the tool name, the command that was executed,
            standard output, standard error, the process return code, and a timestamp
            of when the command finished.

    Example:
        >>> result = run_tool(my_tool_config, "/tmp/context")
        >>> result.return_code
        0"""
    python = sys.executable
    path = str(Path(context_path))
    run_env = None
    project_dir = ""
    if tool_config.run_in_target_env:
        uv = shutil.which("uv")
        if uv:
            resolved = Path(context_path).resolve()
            if resolved.is_dir():
                abs_dir = str(resolved)
                path = "."
            else:
                project_root = _find_project_root(resolved)
                abs_dir = str(project_root) if project_root else str(resolved.parent)
                path = str(resolved)
            project_dir = Path(abs_dir).as_posix()
            project_root_path = Path(abs_dir)
            missing_deps = [d for d in tool_config.extra_deps if not _dep_in_venv(d, project_root_path)]
            # Quote deps with shlex.quote to prevent injection via extra_deps.
            # The uv path and abs_dir use standard double-quoting which is
            # compatible with both POSIX and MSYS bash on Windows.
            with_flags = " ".join(f"--with {shlex.quote(dep)}" for dep in missing_deps)
            no_sync = "--no-sync" if sys.executable.startswith(abs_dir) else ""
            python = f'"{uv}" run {no_sync} --directory "{abs_dir}" {with_flags}'.strip()
            # Strip venv env vars so the target project's environment is used cleanly.
            # VIRTUAL_ENV pointing to cq's own venv would cause uv to warn and can
            # corrupt the subprocess's sys.path, mixing packages from both projects.
            run_env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "PYTHONHOME", "PYTHONPATH")}
    abs_context_path = str(Path(context_path).resolve())
    if not project_dir:
        project_dir = Path(abs_context_path).as_posix() if Path(abs_context_path).is_dir() else Path(abs_context_path).parent.as_posix()
    input_path_posix = Path(context_path).as_posix().rstrip("/")
    exclude = _build_exclude_str(tool_config.exclude_format, excludes or [], input_path_posix=input_path_posix)

    command = tool_config.command.format(context_path=path, abs_context_path=abs_context_path, input_path_posix=input_path_posix, python=python, exclude=exclude)
    cache_key = f"{command}:{get_context_hash(context_path)}"
    if cache_key in _cache:
        log.debug(f"Cache hit: {command}")
        return RawResult(**cast(dict[str, Any], _cache[cache_key]))
    log.debug(f"Running: {command}")
    # shell=True is required because commands use shell features (&&, |) and
    # variable substitution ({python} expands to a compound uv command).
    # All user-supplied values (context_path, excludes) are properly quoted
    # via shlex.quote() to prevent injection — see _build_exclude_str and
    # the uv command assembly above.
    result = subprocess.run(command, capture_output=True, text=True, shell=True, encoding="utf-8", errors="replace", env=run_env)  # nosec
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    raw_result = RawResult(
        tool_name=tool_config.name,
        command=command,
        stdout=result.stdout,
        stderr=result.stderr,
        return_code=result.returncode,
        timestamp=timestamp,
        project_path=project_dir,
    )
    _cache.set(cache_key, raw_result.to_dict(), expire=5 * 24 * 60 * 60)
    return raw_result


def run_tools(tool_configs: Collection[ToolConfig], path: str, max_workers: int = 0, early_exit: bool = False, excludes: list[str] | None = None) -> list[ToolResult]:
    """Run multiple tools and return their parsed results.

    Runs each tool specified in *tool_configs* on the file or directory at
    *path*. Each tool is executed through :func:`run_tool`, and its output is
    parsed by the tool's ``parser_class`` to produce a :class:`ToolResult`.
    When *parallel* is ``True`` the tools are run concurrently with a
    :class:`concurrent.futures.ThreadPoolExecutor` limited to at most four
    workers. Exceptions raised by a tool during parallel execution are logged
    via ``log.error``; in serial mode the exception propagates to the caller.

    Args:
        tool_configs (Iterable[ToolConfig]):
            A sequence of tool configuration objects.  Each object must expose
            a ``name`` attribute, a ``parser_class`` callable, and any other
            information required by :func:`run_tool`.
        path (str):
            Path to the input file or directory that the tools should analyze.
        parallel (bool, optional):
            If ``True``, run the tools in parallel using a thread pool
            (default: ``False``).

    Returns:
        list[ToolResult]:
            A list containing the parsed results for each tool, in the same
            order as *tool_configs*.

    Raises:
        RuntimeError:
            If a non-parallel execution encounters an exception from
            :func:`run_tool` or the parser.  In parallel mode exceptions are
            logged instead of being raised.

    Example:
        >>> from mymodule import run_tools, ToolConfig
        >>> configs = [
        ...     ToolConfig(name='lint', parser_class=LintParser),
        ...     ToolConfig(name='scan', parser_class=ScanParser),
        ... ]
        >>> results = run_tools(configs, '/path/to/project', parallel=True)"""
    def _run_and_parse(tool_config: ToolConfig) -> tuple[int, ToolResult]:
        t0 = time.perf_counter()
        raw_result = run_tool(tool_config, path, excludes)
        tr = tool_config.parser_class(tool_config.parser_config).parse(raw_result)
        tr.duration_s = time.perf_counter() - t0
        return tool_config.order, tr

    if not tool_configs:
        return []
    t_start = time.perf_counter()
    prioritized: list[tuple[int, ToolResult]] = []
    if early_exit:
        sorted_configs = sorted(tool_configs, key=lambda tc: tc.order)
        n_total = len(sorted_configs)
        for i, tool_config in enumerate(sorted_configs):
            try:
                prioritized.append(_run_and_parse(tool_config))
            except Exception as exc:
                log.error(f"{tool_config.name} generated an exception: {exc}")
                n_skipped = n_total - i - 1
                if n_skipped:
                    remaining = ", ".join(tc.name for tc in sorted_configs[i + 1:])
                    log.warning(f"Early exit: skipped {n_skipped} tool(s): {remaining}")
                break
            _, tr = prioritized[-1]
            if tr.metrics and min(tr.metrics.values()) < tool_config.error_threshold:
                n_skipped = n_total - i - 1
                if n_skipped:
                    remaining = ", ".join(tc.name for tc in sorted_configs[i + 1:])
                    log.debug(f"Error threshold hit at {tool_config.name}: skipped {n_skipped} tool(s): {remaining}")
                break
        log.info(f"run_tools elapsed: {time.perf_counter() - t_start:.2f}s")
        return [tr for _, tr in sorted(prioritized)]
    with ThreadPoolExecutor(max_workers=max_workers or len(tool_configs)) as executor:
        future_to_tool = {
            executor.submit(_run_and_parse, tool_config): tool_config
            for tool_config in tool_configs
        }
        timings: list[tuple[int, str, float]] = []
        for future in as_completed(future_to_tool):
            tool_config = future_to_tool[future]
            try:
                order, tr = future.result()
                prioritized.append((order, tr))
                timings.append((order, tool_config.name, tr.duration_s))
            except Exception as exc:
                log.error(f"{tool_config.name} generated an exception: {exc}")
    per_tool = ", ".join(f"{name}={dur:.2f}s" for _, name, dur in sorted(timings))
    log.debug(f"run_tools elapsed: {time.perf_counter() - t_start:.2f}s [{per_tool}]")
    return [tr for _, tr in sorted(prioritized)]
