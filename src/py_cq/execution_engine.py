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
import tempfile
import time
from collections.abc import Collection
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, cast

from diskcache import Cache, JSONDisk

from py_cq.context_hash import get_context_hash
from py_cq.localtypes import RawResult, ToolConfig, ToolResult

log = logging.getLogger("cq")

_cache = Cache(
    Path.home() / ".cache" / "cq", size_limit=100 * 1024 * 1024, disk=JSONDisk
)


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


def _compute_scan_targets(
    context_path: str,
    scan_exclude_names: list[str],
    user_excludes: list[str] | None = None,
) -> str:
    """Return space-separated quoted absolute paths for bandit-style scanning.

    When context_path is a directory, enumerates its top-level children and
    omits any whose name is in scan_exclude_names or user_excludes.  When it's
    a file, returns just that file.  Falls back to the root itself if all
    children are excluded.
    """
    root = Path(context_path).resolve()
    if not root.is_dir():
        return f'"{root}"'
    excluded = set(scan_exclude_names) | {Path(e).name for e in (user_excludes or [])}
    targets = [str(p) for p in sorted(root.iterdir()) if p.name not in excluded]
    paths = targets if targets else [str(root)]
    return " ".join(f'"{p}"' for p in paths)


def _build_exclude_str(
    exclude_format: str, excludes: list[str], **extra_vars: str
) -> str:
    """Builds an exclude string from a list of excludes and a format string."""

    if not exclude_format or not excludes:
        return ""
    parts = []
    for exc in excludes:
        abs_posix_path = Path(exc).resolve().as_posix()
        abs_native_path = str(Path(exc).resolve())
        # shlex.quote prevents shell injection via exclude paths
        parts.append(
            exclude_format.format(
                path=shlex.quote(exc),
                abs_posix_path=shlex.quote(abs_posix_path),
                abs_native_path=shlex.quote(abs_native_path),
                **{k: shlex.quote(v) for k, v in extra_vars.items()},
            )
        )
    return "".join(parts)


def run_tool(
    tool_config: ToolConfig,
    context_path: str,
    excludes: list[str] | None = None,
    *,
    precomputed_hash: str | None = None,
    project_tag: str | None = None,
) -> RawResult:
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
            missing_deps = [
                d
                for d in tool_config.extra_deps
                if not _dep_in_venv(d, project_root_path)
            ]
            # Quote deps with shlex.quote to prevent injection via extra_deps.
            # The uv path and abs_dir use standard double-quoting which is
            # compatible with both POSIX and MSYS bash on Windows.
            with_flags = " ".join(f"--with {shlex.quote(dep)}" for dep in missing_deps)
            no_sync = "--no-sync" if sys.executable.startswith(abs_dir) else ""
            python = (
                f'"{uv}" run {no_sync} --directory "{abs_dir}" {with_flags}'.strip()
            )
            # Strip venv env vars so the target project's environment is used cleanly.
            # VIRTUAL_ENV pointing to cq's own venv would cause uv to warn and can
            # corrupt the subprocess's sys.path, mixing packages from both projects.
            run_env = {
                k: v
                for k, v in os.environ.items()
                if k not in ("VIRTUAL_ENV", "PYTHONHOME", "PYTHONPATH")
            }
    abs_context_path = str(Path(context_path).resolve())
    abs_context_path_posix = Path(context_path).resolve().as_posix()
    native_sep = os.sep
    if not project_dir:
        project_dir = (
            Path(abs_context_path).as_posix()
            if Path(abs_context_path).is_dir()
            else Path(abs_context_path).parent.as_posix()
        )
    input_path_posix = Path(context_path).as_posix().rstrip("/")
    exclude = _build_exclude_str(
        tool_config.exclude_format,
        excludes or [],
        input_path_posix=input_path_posix,
        abs_context_path_posix=abs_context_path_posix,
    )
    scan_targets = _compute_scan_targets(
        context_path, tool_config.scan_exclude_names, excludes
    )

    command = tool_config.command.format(
        context_path=path,
        abs_context_path=abs_context_path,
        abs_context_path_posix=abs_context_path_posix,
        input_path_posix=input_path_posix,
        native_sep=native_sep,
        scan_targets=scan_targets,
        python=python,
        exclude=exclude,
    )
    if precomputed_hash is not None:
        context_hash = precomputed_hash
    elif tool_config.cache_invariant == "ast":
        context_hash = get_context_hash(context_path, normalize=True)
    else:
        context_hash = get_context_hash(context_path)
    cache_key = f"{command}:{context_hash}"

    t_cache0 = time.perf_counter()
    cached = _cache.get(cache_key)
    t_cache = time.perf_counter() - t_cache0
    if cached is not None:
        log.debug(
            f"{tool_config.name}: [CACHE HIT] cache={t_cache * 1000:.1f}ms {command}"
        )
        return RawResult(**cast(dict[str, Any], cached))

    # shell=True is required because commands use shell features (&&, |) and
    # variable substitution ({python} expands to a compound uv command).
    # All user-supplied values (context_path, excludes) are properly quoted
    # via shlex.quote() to prevent injection - see _build_exclude_str and
    # the uv command assembly above.
    if run_env is None:
        run_env = dict(os.environ)
    _fd, coverage_tmp = tempfile.mkstemp(prefix=".coverage.cq.")
    os.close(_fd)
    run_env["COVERAGE_FILE"] = coverage_tmp
    t_sub0 = time.perf_counter()
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            shell=True,
            encoding="utf-8",
            errors="replace",
            env=run_env,
        )  # nosec
    finally:
        Path(coverage_tmp).unlink(missing_ok=True)
    t_sub = time.perf_counter() - t_sub0
    log.debug(
        f"{tool_config.name}: [MISS] cache={t_cache * 1000:.1f}ms tool={t_sub * 1000:.0f}ms: {command}"
    )
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
    _cache.set(cache_key, raw_result.to_dict(), expire=5 * 24 * 60 * 60, tag=project_tag)
    return raw_result


def run_tools(
    tool_configs: Collection[ToolConfig],
    path: str,
    max_workers: int = 0,
    early_exit: bool = False,
    order: str = "severity",
    excludes: list[str] | None = None,
    project_root: str | None = None,
) -> list[ToolResult]:
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
    if not tool_configs:
        return []
    t_start = time.perf_counter()
    t_hash0 = time.perf_counter()
    root = project_root or str(Path(path).resolve())
    shared_hash = get_context_hash(root)
    log.debug(f"context_hash: {(time.perf_counter() - t_hash0) * 1000:.1f}ms {shared_hash}")

    # Cache keys are content-based, so a changed project naturally produces new
    # keys; stale entries age out via TTL + size_limit (no blanket eviction).
    # Tools flagged cache_invariant="ast" key on the docstring-stripped AST so
    # docstring/comment/format-only edits stay cache hits.
    norm_hash: str | None = None

    def _hash_for(tool_config: ToolConfig) -> str:
        nonlocal norm_hash
        if tool_config.cache_invariant == "ast":
            if norm_hash is None:
                norm_hash = get_context_hash(root, normalize=True)
            return norm_hash
        return shared_hash

    def _run_and_parse(tool_config: ToolConfig) -> tuple[int, ToolResult]:
        t0 = time.perf_counter()
        raw_result = run_tool(tool_config, path, excludes, precomputed_hash=_hash_for(tool_config), project_tag=root)
        tr = tool_config.parser_class(tool_config.parser_config).parse(raw_result)
        tr.duration_s = time.perf_counter() - t0
        return tool_config.order, tr

    prioritized: list[tuple[int, ToolResult]] = []
    if early_exit:
        sorted_configs = sorted(tool_configs, key=lambda tc: tc.order)
        n_total = len(sorted_configs)
        for i, tool_config in enumerate(sorted_configs):
            try:
                prioritized.append(_run_and_parse(tool_config))
            except Exception as exc:
                log.error(f"{tool_config.name} generated an exception: {exc} {exc.__traceback__}")
                n_skipped = n_total - i - 1
                if n_skipped:
                    remaining = ", ".join(tc.name for tc in sorted_configs[i + 1 :])
                    log.warning(f"Early exit: skipped {n_skipped} tool(s): {remaining}")
                break
            _, tr = prioritized[-1]
            # order="phase" stops at the first phase with *any* finding (not
            # clean), so phase order is absolute and independent of error/warning
            # threshold tuning; "severity" stops at the first error.
            threshold = (
                tool_config.warning_threshold
                if order == "phase"
                else tool_config.error_threshold
            )
            if tr.metrics and min(tr.metrics.values()) < threshold:
                n_skipped = n_total - i - 1
                if n_skipped:
                    remaining = ", ".join(tc.name for tc in sorted_configs[i + 1 :])
                    log.debug(
                        f"{'Not clean' if order == 'phase' else 'Error threshold hit'} at {tool_config.name}: skipped {n_skipped} tool(s): {remaining}"
                    )
                break
        log.info(f"cq run_tools elapsed: {time.perf_counter() - t_start:.2f}s")
        return [tr for _, tr in sorted(prioritized)]
    configs_by_name = {tc.name: tc for tc in tool_configs}

    def _run_if_dep_passed(dep_future, tool_config: ToolConfig, dep_config: ToolConfig) -> tuple[int, ToolResult]:
        # Wait for the dependency within the same thread pool - no phase split,
        # so all other tools keep running in parallel while we block here.
        try:
            _, dep_tr = dep_future.result()
        except Exception:
            return _run_and_parse(tool_config)
        if dep_tr.metrics and min(dep_tr.metrics.values()) < dep_config.error_threshold:
            # Dependency failed its error threshold: skip this tool and return a
            # synthetic empty result. Coverage declares skip_if = "pytest" so that
            # it never re-invokes pytest (which the coverage command does internally)
            # when we already know pytest is broken.
            log.debug(f"{tool_config.name}: skipping because {tool_config.skip_if} failed")
            t0 = time.perf_counter()
            tr = tool_config.parser_class(tool_config.parser_config).parse(
                RawResult(tool_name=tool_config.name)
            )
            tr.duration_s = time.perf_counter() - t0
            return tool_config.order, tr
        return _run_and_parse(tool_config)

    timings: list[tuple[int, str, float]] = []
    # Sort by order so that when we build name_to_future below, a dependency's
    # future is always registered before the tool that declares skip_if on it.
    sorted_configs = sorted(tool_configs, key=lambda tc: tc.order)
    name_to_future: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=max_workers or len(tool_configs)) as executor:
        future_to_tool = {}
        for tc in sorted_configs:
            dep_name = tc.skip_if
            dep_future = name_to_future.get(dep_name) if dep_name else None
            dep_config = configs_by_name.get(dep_name) if dep_name else None
            if dep_future and dep_config:
                # Submit a wrapper that waits on the dependency future first.
                f = executor.submit(_run_if_dep_passed, dep_future, tc, dep_config)
            else:
                f = executor.submit(_run_and_parse, tc)
            future_to_tool[f] = tc
            name_to_future[tc.name] = f
        for future in as_completed(future_to_tool):
            tool_config = future_to_tool[future]
            try:
                tc_order, tr = future.result()
                prioritized.append((tc_order, tr))
                timings.append((tc_order, tool_config.name, tr.duration_s))
            except Exception as exc:
                log.error(f"{tool_config.name} generated an exception: {exc}")
    per_tool = ", ".join(f"{name}={dur:.2f}s" for _, name, dur in sorted(timings))
    log.debug(f"run_tools elapsed: {time.perf_counter() - t_start:.2f}s [{per_tool}]")
    return [tr for _, tr in sorted(prioritized)]
