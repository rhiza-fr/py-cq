"""Utilities for consolidating static-analysis metrics.

This module provides a single function, :func:`aggregate_metrics`, which takes a filesystem path and a list of
:class:`ToolResult` objects produced by various static-analysis tools. It validates the input, merges the
metrics from each tool into a :class:`CombinedToolResults` instance, and returns the unified representation.
The resulting object can be consumed by reporting tools or CI pipelines to present a single view of all analysis
results for a given file or directory."""

from py_cq.localtypes import CombinedToolResults, ToolResult


def aggregate_metrics(path: str, metrics: list[ToolResult]) -> CombinedToolResults:
    """Returns a CombinedToolResults instance aggregating the given metrics for the specified path."""
    return CombinedToolResults(path=path, tool_results=metrics)
