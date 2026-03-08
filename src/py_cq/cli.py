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
import json
import logging
import tomllib
from enum import Enum
from pathlib import Path

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from py_cq.config import load_user_config
from py_cq.execution_engine import _cache as tool_cache
from py_cq.execution_engine import run_tools
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
    return registry


class OutputMode(str, Enum):
    """Enum of output types."""
    TABLE = "table"
    SCORE = "score"
    JSON = "json"
    LLM = "llm"
    RAW = "raw"


@app.callback()
def callback():
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
):
    """Feed the results from 11+ code quality tools to an LLM. Try: cq check . -o llm""" # --help
    path_obj = Path(path)
    if not path_obj.exists():
        raise typer.BadParameter(f"Path does not exist: {path}")
    if path_obj.is_file():
        if path_obj.suffix != ".py":
            raise typer.BadParameter(f"File must be a Python file (.py): {path}")
    elif path_obj.is_dir():
        if not (path_obj / "pyproject.toml").exists():
            raise typer.BadParameter(f"Directory must contain pyproject.toml: {path}")
    log.setLevel(log_level)
    effective_registry = _apply_user_config(tool_registry, load_user_config(path_obj))
    if clear_cache:
        tool_cache.clear()
    tool_results = run_tools(effective_registry.values(), path, workers, early_exit=(output == OutputMode.LLM))
    # for tr in tool_results:
    #     log.debug(json.dumps(tr.to_dict(), indent=2))
    combined_metrics = aggregate_metrics(path=path, metrics=tool_results)
    if output == OutputMode.SCORE:
        console.print(combined_metrics.score)
    elif output == OutputMode.JSON:
        console.print(json.dumps([tr.to_dict() for tr in tool_results], indent=2))
    elif output == OutputMode.RAW:
        console.print(json.dumps([tr.raw.to_dict() for tr in tool_results], indent=2))
    elif output == OutputMode.LLM:
        # log.setLevel("CRITICAL")
        from py_cq.llm_formatter import format_for_llm
        console.print(format_for_llm(effective_registry, combined_metrics))
    else:
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

    for tool_id in sorted(tool_registry, key=lambda t: tool_registry[t].order):
        tc = effective_registry.get(tool_id, tool_registry[tool_id])
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
    table = Table(title=f"[bold green]{data.path}[/]", width=80)
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
