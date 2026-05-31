"""CLI for static analysis of Python projects.

Provides a Typer command `check` that accepts a path to a Python file or project
directory, executes a suite of static analysis tools, aggregates their
results, and outputs the data either as JSON or as a human-readable Rich
table.  The command supports configurable logging, cache clearing,
score-only output, and optional parallel execution to accelerate
analysis.

Helper functions such as `format_as_table` convert the aggregated tool
results into a Rich Table for convenient console display.
"""
import io
import json
import logging
import time
import tomllib
from enum import Enum
from importlib.metadata import requires, version
from pathlib import Path

import tomlkit
import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from py_cq.api import CQ, _apply_user_config
from py_cq.language_detector import detect_language
from py_cq.metric_aggregator import aggregate_metrics
from py_cq.table_formatter import format_as_table
from py_cq.tool_registry import tool_registry

logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(markup=True)],
)
log = logging.getLogger("cq")
app = typer.Typer(
    epilog=(
        "Examples:\n\n"
        "  cq check .          # full table with all metrics (default)\n\n"
        "  cq check . -o llm      # top defect as markdown (primary LLM workflow)\n\n"
        "  cq check . -o llm-json # top defect as JSON with fingerprint for automation\n\n"
        "  cq check . -o score    # numeric score only\n\n"
        "  cq check . -o json     # parsed metrics as json\n\n"
        "  cq check . -o raw      # unprocessed tool output as json\n\n"
        "  cq config              # show effective tool configuration\n"
        "  cq config --path .     # show configuration for current project\n\n"
        "  cq config set radon-hal --warning 0.45 --error 0.25  # set thresholds\n\n"
        "  cq config set radon-hal --error 0.25 --path .        # set with path"
    ),
)


class OutputMode(str, Enum):
    """Enum of output types."""
    TABLE = "table"
    SCORE = "score"
    JSON = "json"
    LLM = "llm"
    LLM_JSON = "llm-json"
    RAW = "raw"


def _version_callback(value: bool) -> None:
    if not value:
        return
    import re
    pkg = "python-code-quality"
    pkg_version = version(pkg)
    dep_versions: list[tuple[str, str]] = []
    for req in (requires(pkg) or []):
        if "; extra ==" in req:
            continue
        dep_name = re.split(r"[>=<!;\s\[]", req)[0]
        try:
            dep_versions.append((dep_name, version(dep_name)))
        except Exception:
            pass
    typer.echo(f"{pkg} v{pkg_version}")
    for dep_name, dep_ver in sorted(dep_versions):
        typer.echo(f"+-- {dep_name} v{dep_ver}")
    raise typer.Exit()


@app.callback()
def callback(
    _: bool = typer.Option(
        False, "--version", "-V", callback=_version_callback, is_eager=True, help="Show version and dependencies"
    ),
) -> None:
    """Feed the results from 11+ code quality tools to an LLM. Try: cq check . -o llm"""
    import sys
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
console = Console()


@app.command()
def check(
    path: str = typer.Argument(".", help="Path to Python file or project directory"),
    output: OutputMode = typer.Option(
        OutputMode.TABLE, "--output", "-o", help="Output mode: table (default), score, json, llm"
    ),
    log_level: str = typer.Option(
        "CRITICAL",
        "--log-level",
        help="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    ),
    clear_cache: bool = typer.Option(
        False, "--clear-cache", help="Clear cached tool results before running"
    ),
    workers: int = typer.Option(
        0, "--workers", help="Max parallel workers (default: one per tool, use 1 for sequential)"
    ),
    language: str | None = typer.Option(
        None, "--language", "-l", help="Override language detection (e.g. python, typescript, rust)"
    ),
    only: str | None = typer.Option(
        None, "--only", help="Comma-separated tool IDs to run (e.g. ruff,ty,pytest)"
    ),
    skip: str | None = typer.Option(
        None, "--skip", help="Comma-separated tool IDs to skip (e.g. bandit,vulture)"
    ),
    exclude: str | None = typer.Option(
        None, "--exclude", help="Comma-separated paths to exclude (e.g. demo,docs)"
    ),
    hint: bool = typer.Option(
        False, "--hint", help="Append 'run cq again to verify' to -o llm output"
    ),
    limit: int = typer.Option(
        1, "--limit", help="Number of issues to show with -o llm (default: 1)"
    ),
    silence: list[str] = typer.Option(
        [], "--silence", "-s", help="Silence issues from -o llm output (e.g. -s src/foo.py or -s src/foo.py:42:E501)"
    ),
):
    """Feed the results from 11+ code quality tools to an LLM. Try: cq check . -o llm""" # --help
    path_obj = Path(path)
    if not path_obj.exists():
        raise typer.BadParameter(f"Path does not exist: {path}")

    resolved_language = language or detect_language(path_obj)

    if resolved_language is not None and resolved_language != "python":
        console.print(
            f"[yellow]{resolved_language.capitalize()} project detected. "
            "Non-Python language support is not yet available.[/yellow]"
        )
        raise typer.Exit(0)

    if path_obj.is_file():
        if path_obj.suffix != ".py":
            raise typer.BadParameter(f"File must be a Python file (.py): {path}")
    elif path_obj.is_dir():  # pragma: no branch
        if not (path_obj / "pyproject.toml").exists():
            raise typer.BadParameter(f"Directory must contain pyproject.toml: {path}")
    log.setLevel(log_level)

    only_list = [t.strip() for t in only.split(",")] if only else None
    skip_list = [t.strip() for t in skip.split(",")] if skip else None
    exclude_list = [e.strip() for e in exclude.split(",")] if exclude else None

    try:
        cq = CQ(path_obj, only=only_list, skip=skip_list, exclude=exclude_list, workers=workers, clear_cache=clear_cache)
    except ValueError as e:
        raise typer.BadParameter(str(e))

    is_llm = output in (OutputMode.LLM, OutputMode.LLM_JSON)
    t0 = time.perf_counter()
    tool_results = cq.raw(early_exit=is_llm)
    total_s = time.perf_counter() - t0
    combined = aggregate_metrics(path, tool_results)

    if output == OutputMode.SCORE:
        console.print(combined.score)
    elif output == OutputMode.JSON:
        print(json.dumps([tr.to_dict() for tr in tool_results], indent=2))
    elif output == OutputMode.RAW:
        print(json.dumps([tr.raw.to_dict() for tr in tool_results], indent=2))
    elif output == OutputMode.LLM:
        from py_cq.llm_formatter import format_for_llm
        print(format_for_llm(cq._registry, combined, context_lines=cq._context_lines, hint=hint, limit=limit, silence=silence))
    elif output == OutputMode.LLM_JSON:
        from py_cq.llm_formatter import format_for_llm_json
        print(json.dumps(format_for_llm_json(cq._registry, combined, context_lines=cq._context_lines, hint=hint, limit=limit, silence=silence, project_root=cq._project_root)))
    else:
        console.print(f"[bold green]{path_obj.resolve()}[/]")
        console.print(format_as_table(combined, cq._registry, total_s=total_s))

    tool_by_name = {tc.name: tc for tc in cq._registry.values()}
    if any(
        min(tr.metrics.values()) < tool_by_name[tr.raw.tool_name].error_threshold
        for tr in tool_results
        if tr.metrics and tr.raw.tool_name in tool_by_name
    ):
        raise typer.Exit(code=1)


config_app = typer.Typer(help="Show or modify tool configuration")
app.add_typer(config_app, name="config")


@config_app.callback(invoke_without_command=True)
def config(
    ctx: typer.Context,
    path: str = typer.Option(".", "--path", "-p", help="Path to Python file or project directory"),
) -> None:
    """Show the effective tool configuration for a project."""
    if ctx.invoked_subcommand is not None:
        return
    path_obj = Path(path).resolve()
    toml_path = (
        path_obj.parent / "pyproject.toml"
        if path_obj.is_file()
        else path_obj / "pyproject.toml"
    )

    if not toml_path.exists():
        status_text = "[yellow]file not found[/yellow]"
        user_cfg: dict = {}
    else:
        with toml_path.open("rb") as f:
            toml_data = tomllib.load(f)
        cq_section = toml_data.get("tool", {}).get("cq")
        if cq_section is None:
            status_text = "[yellow]no [tool.cq] section[/yellow]"
            user_cfg = {}
        else:
            status_text = "[green]merged from [tool.cq][/green]"
            user_cfg = cq_section

    console.print(f"Config: [bold]{toml_path}[/bold] ({status_text})\n")

    try:
        effective_registry = _apply_user_config(tool_registry, user_cfg)
    except ValueError as e:
        raise typer.BadParameter(str(e))
    disabled_ids = set(tool_registry.keys()) - set(effective_registry.keys())

    table = Table()
    table.add_column("Tool", style="cyan")
    table.add_column("Order", justify="right")
    table.add_column("Warning", justify="right")
    table.add_column("Error", justify="right")
    table.add_column("Status", justify="center")

    all_tool_ids = set(tool_registry) | set(effective_registry)
    for tool_id in sorted(all_tool_ids, key=lambda t: (effective_registry.get(t) or tool_registry[t]).order):
        tc = effective_registry.get(tool_id) or tool_registry[tool_id]
        is_disabled = tool_id in disabled_ids
        status = "[red]disabled[/red]" if is_disabled else "[green]enabled[/green]"
        table.add_row(
            tc.name,
            str(tc.order),
            f"{tc.warning_threshold:.2f}",
            f"{tc.error_threshold:.2f}",
            status,
        )

    console.print(table)


@config_app.command("set")
def config_set(
    tool_id: str = typer.Argument(..., help="Tool ID (e.g. radon-hal, ruff)"),
    warning: float | None = typer.Option(None, "--warning", "-w", help="Warning threshold (0-1)"),
    error: float | None = typer.Option(None, "--error", "-e", help="Error threshold (0-1)"),
    path: str = typer.Option(".", "--path", "-p", help="Path to project directory"),
) -> None:
    """Set warning/error thresholds for a tool in pyproject.toml."""
    if warning is None and error is None:
        raise typer.BadParameter("At least one of --warning or --error is required")

    if tool_id not in tool_registry:
        available = ", ".join(sorted(tool_registry))
        raise typer.BadParameter(
            f"Unknown tool: {tool_id!r}. Available tools: {available}"
        )

    path_obj = Path(path).resolve()
    if not path_obj.is_dir():
        raise typer.BadParameter(f"Path must be a directory: {path}")

    toml_path = path_obj / "pyproject.toml"
    if not toml_path.exists():
        raise typer.BadParameter(f"No pyproject.toml found at {toml_path}")

    with toml_path.open("r", encoding="utf-8") as f:
        doc = tomlkit.parse(f.read())

    if "tool" not in doc:
        doc["tool"] = tomlkit.table()
    tool_tbl = doc["tool"]
    if "cq" not in tool_tbl:
        tool_tbl["cq"] = tomlkit.table()
    cq_tbl = tool_tbl["cq"]
    if "thresholds" not in cq_tbl:
        cq_tbl["thresholds"] = tomlkit.table()
    thresholds = cq_tbl["thresholds"]

    if tool_id in thresholds:
        entry = thresholds[tool_id]
    else:
        entry = tomlkit.inline_table()

    if warning is not None:
        entry["warning"] = warning
    if error is not None:
        entry["error"] = error
    thresholds[tool_id] = entry

    with toml_path.open("w", encoding="utf-8") as f:
        f.write(tomlkit.dumps(doc))

    parts = []
    if warning is not None:
        parts.append(f"warning={warning}")
    if error is not None:
        parts.append(f"error={error}")
    console.print(
        f"[green]Set {tool_id} thresholds ({', '.join(parts)}) "
        f"in {toml_path}[/green]"
    )

    from py_cq.execution_engine import _cache
    _cache.clear()
    console.print("[dim]Tool cache cleared[/dim]")


@app.command()
def is_fixed(
    fingerprint: str = typer.Argument(..., help="Fingerprint from -o llm-json output (tool::project::path[::line[::code]])"),
) -> None:
    """Return True if the fingerprinted issue is no longer present."""
    try:
        cq = CQ(".")
        fixed = cq.is_fixed(fingerprint)
    except ValueError as e:
        raise typer.BadParameter(str(e))

    if fixed:
        typer.echo("FIXED")
    else:
        typer.echo(f"FAILED: {fingerprint}")
        raise typer.Exit(1)
