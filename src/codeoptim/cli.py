import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

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
    tool_results = []

    with ThreadPoolExecutor() as executor:
        # Submit all tools for parallel execution
        future_to_tool = {
            executor.submit(run_tool, tool_config, path): tool_config
            for tool_config in tool_registry.values()
        }
        
        # Process results as they complete
        for future in as_completed(future_to_tool):
            tool_config = future_to_tool[future]
            try:
                raw_result = future.result()
                parser = tool_config.parser_class()
                tr = parser.parse(raw_result)
                tool_results.append(tr)
                log.debug(json.dumps(tr.to_dict(), indent=2))
            except Exception as exc:
                log.error(f"{tool_config.name} generated an exception: {exc}")

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
