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

import json
import logging
from enum import Enum
from pathlib import Path
import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table
from cq.config import DEFAULT_STORAGE_FILE
from cq.execution_engine import run_tools, _cache as tool_cache
from cq.localtypes import CombinedToolResults
from cq.metric_aggregator import aggregate_metrics
from cq.storage import save_result
from cq.tool_registry import tool_registry

logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(markup=True)],
)
log = logging.getLogger("cq")
app = typer.Typer()


class OutputMode(str, Enum):
    TABLE = "table"
    SCORE = "score"
    JSON = "json"
    LLM = "llm"


@app.callback()
def callback():
    """CQ - Code Quality Analysis Tool."""
console = Console()
# TODO make this work on projects


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
    out_file: str = typer.Option(
        DEFAULT_STORAGE_FILE,
        "--out-file",
        help="File path to save results in table mode (defaults to analysis_results.json)",
    ),
    clear_cache: bool = typer.Option(
        False, "--clear-cache", help="Clear cached tool results before running"
    ),
    sequential: bool = typer.Option(
        False, "--sequential", help="Run analysis tools sequentially instead of in parallel"
    ),
):
    """Run static analysis on a Python file or project directory."""
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
    if clear_cache:
        tool_cache.clear()
    tool_results = run_tools(tool_registry.values(), path, not sequential)
    for tr in tool_results:
        log.debug(json.dumps(tr.to_dict(), indent=2))
    combined_metrics = aggregate_metrics(path=path, metrics=tool_results)
    if output == OutputMode.SCORE:
        console.print(combined_metrics.score)
    elif output == OutputMode.JSON:
        console.print(json.dumps(combined_metrics.to_dict(), indent=2))
    elif output == OutputMode.LLM:
        log.setLevel("CRITICAL")
        from cq.llm_formatter import format_for_llm
        console.print(format_for_llm(tool_registry, combined_metrics))
    else:
        save_result(combined_tool_results=combined_metrics, file_name=out_file)
        console.print(format_as_table(combined_metrics))


def format_as_table(data: CombinedToolResults):
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
    table.add_column("Metric", justify="right", style="cyan", no_wrap=True)
    table.add_column("Score", style="magenta")
    table.add_column("Status")
    for tr in data.tool_results:
        tool_name = tr.raw.tool_name
        config = next((t for t in tool_registry.values() if t.name == tool_name))
        for name, value in tr.metrics.items():
            status = ""
            if value < config.error_threshold:
                status = "[bold red]Error[/]"
            elif value < config.warning_threshold:
                status = "[yellow]Warning[/]"
            else:
                status = "[green]OK[/]"
            table.add_row(tool_name, name, f"{value:0.3f}", status)
    table.add_row("", "[bold]Score[/]", f"[bold]{data.score:0.3f}[/]", "")
    return table
