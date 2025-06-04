from codeoptim.localtypes import CombinedToolResults, ToolResult


def aggregate_metrics(path: str, metrics: list[ToolResult]) -> CombinedToolResults:
    return CombinedToolResults(path=path, tool_results=metrics)
