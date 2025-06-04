import json
import logging

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from codeoptim.config import DEFAULT_STORAGE_FILE
from codeoptim.execution_engine import run_tool
from codeoptim.localtypes import CombinedToolResults
from codeoptim.metric_aggregator import aggregate_metrics
from codeoptim.storage import save_result
from codeoptim.tool_registry import tool_registry

logging.basicConfig(
    level="INFO", format="%(message)s", datefmt="[%X]", handlers=[RichHandler(markup=True)]
)

log = logging.getLogger("codeoptim")

app = typer.Typer()
console = Console()

# TODO make this work on projects


@app.command()
def run(
    path: str,
    log_level: str = "INFO",
    out_file: str = DEFAULT_STORAGE_FILE,
    clear_cache: bool = False,
    as_json: bool = False,
    as_score: bool = False,
    parallel: bool = typer.Option(False, "--parallel", help="Run tools in parallel"),
):
    """Runs analysis on a project or file."""
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
