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
import copy
import io
import json
import logging
import tomllib
from enum import Enum
from importlib import import_module
from importlib.metadata import requires, version
from pathlib import Path

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from py_cq.config import load_user_config
from py_cq.execution_engine import _cache as tool_cache
from py_cq.execution_engine import run_tools
from py_cq.language_detector import detect_language
from py_cq.localtypes import CombinedToolResults, ToolConfig
from py_cq.metric_aggregator import aggregate_metrics
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
        "  cq check . -o llm   # top defect as markdown (primary LLM workflow)\n\n"
        "  cq check . -o score # numeric score only\n\n"
        "  cq check . -o json  # parsed metrics as json\n\n"
        "  cq check . -o raw   # unprocessed tool output as json\n\n"
        "  cq config .         # show effective tool configuration"
    ),
)


def _apply_user_config(base: dict[str, ToolConfig], user_cfg: dict) -> dict[str, ToolConfig]:
    """Return a modified copy of base with user overrides applied.

    Supports:
      - ``disable``: list of tool IDs to remove
      - ``thresholds.<tool_id>.warning`` / ``.error``: override per-tool thresholds
      - ``tools.<tool_id>``: declare new tools (or override built-ins)
    """
    registry = {k: copy.copy(v) for k, v in base.items()}
    for tool_id in user_cfg.get("disable", []):
        registry.pop(tool_id, None)
    for tool_id, thresholds in user_cfg.get("thresholds", {}).items():
        if tool_id in registry:
            if "warning" in thresholds:
                registry[tool_id].warning_threshold = float(thresholds["warning"])
            if "error" in thresholds:
                registry[tool_id].error_threshold = float(thresholds["error"])
    for tool_id, tool_data in user_cfg.get("tools", {}).items():
        try:
            parser_name = tool_data["parser"]
            module = import_module(f"py_cq.parsers.{parser_name.lower()}")
            parser_class = getattr(module, parser_name)
            registry[tool_id] = ToolConfig(
                name=tool_id,
                command=tool_data["command"],
                parser_class=parser_class,
                order=tool_data["order"],
                warning_threshold=tool_data["warning_threshold"],
                error_threshold=tool_data["error_threshold"],
                run_in_target_env=tool_data.get("run_in_target_env", False),
                extra_deps=tool_data.get("extra_deps", []),
                parser_config=tool_data.get("parser_config", {}),
                exclude_format=tool_data.get("exclude_format", ""),
            )
        except KeyError as e:
            raise typer.BadParameter(f"[tool.cq.tools.{tool_id}] missing required field {e}")
    return registry


class OutputMode(str, Enum):
    """Enum of output types."""
    TABLE = "table"
    SCORE = "score"
    JSON = "json"
    LLM = "llm"
    RAW = "raw"


def _version_callback(value: bool) -> None:
    if not value:
        return
    import re
    import sys
    if isinstance(sys.stdout,  io.TextIOWrapper):  
        sys.stdout.reconfigure(encoding="utf-8")
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
        typer.echo(f"\u251c\u2500\u2500 {dep_name} v{dep_ver}")
    raise typer.Exit()


@app.callback()
def callback(
    _: bool = typer.Option(
        False, "--version", "-V", callback=_version_callback, is_eager=True, help="Show version and dependencies"
    ),
) -> None:
    """Feed the results from 11+ code quality tools to an LLM. Try: cq check . -o llm"""
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

    # Python path (or unknown — fall through to existing validation).
    # Note: --language python still requires pyproject.toml; the flag selects
    # the tool set, not the input validation rules.
    if path_obj.is_file():
        if path_obj.suffix != ".py":
            raise typer.BadParameter(f"File must be a Python file (.py): {path}")
    elif path_obj.is_dir():
        if not (path_obj / "pyproject.toml").exists():
            raise typer.BadParameter(f"Directory must contain pyproject.toml: {path}")
    log.setLevel(log_level)
    user_cfg = load_user_config(path_obj)
    context_lines: int = int(user_cfg.get("context_lines", 15))
    effective_registry = _apply_user_config(tool_registry, user_cfg)
    if only:
        keep = set(only.split(","))
        effective_registry = {k: v for k, v in effective_registry.items() if k in keep}
    if skip:
        drop = set(skip.split(","))
        effective_registry = {k: v for k, v in effective_registry.items() if k not in drop}
    config_excludes: list[str] = user_cfg.get("exclude", [])
    cli_excludes: list[str] = [e.strip() for e in exclude.split(",")] if exclude else []
    excludes = list(dict.fromkeys(config_excludes + cli_excludes))
    if clear_cache:
        tool_cache.clear()
    tool_results = run_tools(effective_registry.values(), path, workers, early_exit=(output == OutputMode.LLM), excludes=excludes)
    # for tr in tool_results:
    #     log.debug(json.dumps(tr.to_dict(), indent=2))
    combined_metrics = aggregate_metrics(path=path, metrics=tool_results)
    if output == OutputMode.SCORE:
        console.print(combined_metrics.score)
    elif output == OutputMode.JSON:
        print(json.dumps([tr.to_dict() for tr in tool_results], indent=2))
    elif output == OutputMode.RAW:
        print(json.dumps([tr.raw.to_dict() for tr in tool_results], indent=2))
    elif output == OutputMode.LLM:
        # log.setLevel("CRITICAL")
        from py_cq.llm_formatter import format_for_llm
        console.print(format_for_llm(effective_registry, combined_metrics, context_lines=context_lines))
    else:
        console.print(f"[bold green]{path_obj.resolve()}[/]")
        console.print(format_as_table(combined_metrics, effective_registry))

    tool_by_name = {tc.name: tc for tc in effective_registry.values()}
    if any(
        min(tr.metrics.values()) < tool_by_name[tr.raw.tool_name].error_threshold
        for tr in tool_results
        if tr.metrics and tr.raw.tool_name in tool_by_name
    ):
        raise typer.Exit(code=1)


@app.command()
def config(
    path: str = typer.Argument(".", help="Path to Python file or project directory"),
) -> None:
    """Show the effective tool configuration for a project."""
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

    effective_registry = _apply_user_config(tool_registry, user_cfg)
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


def format_as_table(data: CombinedToolResults, registry: dict[str, ToolConfig]):
    """Format combined tool results into a Rich Table.

    Args:
        data (CombinedToolResults): Aggregated tool results, including the path,
            individual tool results, and the overall score.

    Returns:
        rich.table.Table: A Rich table with columns ``Tool``, ``Metric``, ``Score`` and
        ``Status``. Each metric row displays a status icon based on thresholds from
        the tool's configuration. The table is titled with the data path and ends
        with a row showing the overall score.

    Example:
        >>> table = format_as_table(combined_results)
        >>> console.print(table)
    """
    table = Table(width=80)
    table.add_column("Tool", justify="left", no_wrap=True)
    table.add_column("Time", justify="right", style="dim")
    table.add_column("Metric", justify="right", style="cyan", no_wrap=True)
    table.add_column("Score", style="magenta")
    table.add_column("Status")
    for tr in data.tool_results:
        tool_name = tr.raw.tool_name
        config = next((t for t in registry.values() if t.name == tool_name))
        for i, (name, value) in enumerate(tr.metrics.items()):
            status = ""
            if value < config.error_threshold:
                status = "[bold red]Error[/]"
            elif value < config.warning_threshold:
                status = "[yellow]Warning[/]"
            else:
                status = "[green]OK[/]"
            time_str = f"{tr.duration_s:.2f}s" if i == 0 else ""
            table.add_row(tool_name, time_str, name, f"{value:0.3f}", status)
    table.add_row("", "", "[bold]Score[/]", f"[bold]{data.score:0.3f}[/]", "")
    return table
