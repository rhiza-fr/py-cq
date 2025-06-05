import json
import logging
from pathlib import Path

import typer
from cq.config import DEFAULT_STORAGE_FILE
from cq.execution_engine import run_tool, run_tools
from cq.localtypes import CombinedToolResults
from cq.metric_aggregator import aggregate_metrics
from cq.storage import save_result
from cq.tool_registry import tool_registry
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

logging.basicConfig(
    level="INFO", format="%(message)s", datefmt="[%X]", handlers=[RichHandler(markup=True)]
)

log = logging.getLogger("cq")

app = typer.Typer()
console = Console()

# TODO make this work on projects


@app.command()
def run(
    path: str = typer.Argument(..., help="Path to Python file or project directory"),
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        help="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    ),
    out_file: str = typer.Option(
        DEFAULT_STORAGE_FILE,
        "--out-file",
        help="File path to save results (defaults to analysis_results.json)",
    ),
    clear_cache: bool = typer.Option(
        False,
        "--clear-cache",
        help="Clear cached tool results before running",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Output results as JSON instead of saving to file",
    ),
    as_score: bool = typer.Option(
        False,
        "--score",
        help="Output only the final score instead of full results",
    ),
    parallel: bool = typer.Option(
        False,
        "--parallel",
        help="Run analysis tools in parallel for faster execution",
    ),
):
    """Runs analysis on a project or file.

    Args:
        path: Path to Python file or project directory (must contain pyproject.toml)
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        out_file: File path to save results (defaults to analysis_results.json)
        clear_cache: Whether to clear cached tool results before running
        as_json: Output results as JSON instead of saving to file
        as_score: Output only the final score instead of full results
        parallel: Run analysis tools in parallel for faster execution
    """
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
        run_tool.clear_cache()  # type: ignore # Use this to remove the tool cache

    tool_results = run_tools(tool_registry.values(), path, parallel)
    for tr in tool_results:
        log.debug(json.dumps(tr.to_dict(), indent=2))

    combined_metrics = aggregate_metrics(path=path, metrics=tool_results)
    if as_score:
        console.print(combined_metrics.score)
    elif as_json:
        console.print(json.dumps(combined_metrics.to_dict(), indent=2))
    else:
        save_result(combined_tool_results=combined_metrics, file_name=out_file)
        console.print(format_as_table(combined_metrics))


def format_as_table(data: CombinedToolResults):
    table = Table(title=f"[bold green]{data.path}[/]", width=80)
    table.add_column("Tool", justify="left", no_wrap=True)
    table.add_column("Metric", justify="right", style="cyan", no_wrap=True)
    table.add_column("Score", style="magenta")

    for tr in data.tool_results:
        tool_name = tr.raw.tool_name
        for name, value in tr.metrics.items():
            table.add_row(tool_name, name, f"{value:0.3f}")
    table.add_row("", "[bold]Score[/]", f"[bold]{data.score:0.3f}[/]")
    return table
