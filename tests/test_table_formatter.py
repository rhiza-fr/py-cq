"""Tests for table_formatter.format_as_table."""

from rich.table import Table

from py_cq.localtypes import CombinedToolResults, RawResult, ToolConfig, ToolResult
from py_cq.table_formatter import format_as_table

# Column indices in the table
COL_TOOL, COL_TIME, COL_METRIC, COL_SCORE, COL_STATUS = 0, 1, 2, 3, 4


def _make_registry(
    warning_threshold: float = 0.7,
    error_threshold: float = 0.5,
) -> dict[str, ToolConfig]:
    """Create a registry with default tool configurations."""
    return {"tool": ToolConfig(
        name="tool",
        command="cmd",
        parser_class=object,
        order=1,
        warning_threshold=warning_threshold,
        error_threshold=error_threshold,
    )}


def _combined(metrics: dict, tool_name: str = "tool") -> CombinedToolResults:
    tr = ToolResult(
        metrics=metrics,
        raw=RawResult(tool_name=tool_name),
        duration_s=0.1,
    )
    return CombinedToolResults(path=".", tool_results=[tr])


def _status_cells(table: Table) -> list:
    """Return non-empty cells from the Status column."""
    return [c for c in table.columns[COL_STATUS]._cells if c]


def test_returns_rich_table():
    """Test that format_as_table returns a Rich Table object."""
    result = format_as_table(_combined({"m": 0.9}), _make_registry())
    assert isinstance(result, Table)


def test_metric_below_error_threshold_shows_error():
    table = format_as_table(_combined({"m": 0.3}), _make_registry(error_threshold=0.5))
    assert any("Error" in c for c in _status_cells(table))


def test_metric_between_warning_and_error_shows_warning():
    table = format_as_table(_combined({"m": 0.6}), _make_registry(error_threshold=0.5, warning_threshold=0.7))
    assert any("Warning" in c for c in _status_cells(table))


def test_metric_above_warning_shows_ok():
    table = format_as_table(_combined({"m": 0.8}), _make_registry(warning_threshold=0.7))
    assert any("OK" in c for c in _status_cells(table))


def test_metric_exactly_at_error_threshold_shows_warning_not_error():
    # value < error_threshold → Error; value == error_threshold → Warning (not Error)
    table = format_as_table(_combined({"m": 0.5}), _make_registry(error_threshold=0.5, warning_threshold=0.7))
    statuses = _status_cells(table)
    assert any("Warning" in c for c in statuses)
    assert not any("Error" in c for c in statuses)


def test_metric_exactly_at_warning_threshold_shows_ok():
    # value < warning_threshold → Warning; value == warning_threshold → OK
    table = format_as_table(_combined({"m": 0.7}), _make_registry(error_threshold=0.5, warning_threshold=0.7))
    statuses = _status_cells(table)
    assert any("OK" in c for c in statuses)


def test_tool_with_multiple_metrics_all_rows_present():
    metrics = {"file_bug_free": 0.9, "file_smallness": 0.8, "func_bug_free": 0.7, "func_smallness": 0.6}
    tr = ToolResult(metrics=metrics, raw=RawResult(tool_name="tool"), duration_s=0.2)
    data = CombinedToolResults(path=".", tool_results=[tr])
    table = format_as_table(data, _make_registry())
    metric_cells = table.columns[COL_METRIC]._cells
    for name in metrics:
        assert name in metric_cells


def test_empty_tool_results_returns_valid_table():
    data = CombinedToolResults(path=".", tool_results=[])
    table = format_as_table(data, {})
    assert isinstance(table, Table)
    # Only the score summary row
    assert len(table.rows) == 1
