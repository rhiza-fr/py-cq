"""Rich table formatter for combined tool results."""

from rich.table import Table

from py_cq.localtypes import CombinedToolResults, ToolConfig


def format_as_table(data: CombinedToolResults, registry: dict[str, ToolConfig]) -> Table:
    """Format combined tool results into a Rich Table."""
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
