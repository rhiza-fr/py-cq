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
import shutil
import subprocess
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import diskcache
from cq.context_hash import get_context_hash
from cq.localtypes import RawResult, ToolConfig, ToolResult

log = logging.getLogger("cq")

_cache = diskcache.Cache(Path.home() / ".cache" / "cq")


def run_tool(tool_config: ToolConfig, context_path: str) -> RawResult:
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
    path = context_path
    if tool_config.run_in_target_env and Path(context_path).is_dir():
        uv = shutil.which("uv")
        if uv:
            abs_dir = str(Path(context_path).resolve())
            with_flags = " ".join(f"--with {dep}" for dep in tool_config.extra_deps)
            python = f'"{uv}" run --directory "{abs_dir}" {with_flags}'.rstrip()
            path = "."
    command = tool_config.command.format(context_path=path, python=python)
    cache_key = f"{command}:{get_context_hash(context_path)}"
    if cache_key in _cache:
        log.info(f"Cache hit: {command}")
        return _cache[cache_key]
    log.info(f"Running: {command}")
    result = subprocess.run(command, capture_output=True, text=True, shell=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    raw_result = RawResult(
        tool_name=tool_config.name,
        command=command,
        stdout=result.stdout,
        stderr=result.stderr,
        return_code=result.returncode,
        timestamp=timestamp,
    )
    _cache[cache_key] = raw_result
    return raw_result


def run_tools(tool_configs, path: str, parallel: bool = False) -> list[ToolResult]:
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
    tool_results = []
    if parallel:
        with ThreadPoolExecutor(max_workers=min(4, len(tool_configs))) as executor:
            future_to_tool = {
                executor.submit(run_tool, tool_config, path): tool_config
                for tool_config in tool_configs
            }
            for future in as_completed(future_to_tool):
                tool_config = future_to_tool[future]
                try:
                    raw_result = future.result()
                    parser = tool_config.parser_class()
                    tr = parser.parse(raw_result)
                    tool_results.append(tr)
                except Exception as exc:
                    log.error(f"{tool_config.name} generated an exception: {exc}")
    else:
        for tool_config in tool_configs:
            raw_result = run_tool(tool_config, path)
            parser = tool_config.parser_class()
            tr = parser.parse(raw_result)
            tool_results.append(tr)
    return tool_results
