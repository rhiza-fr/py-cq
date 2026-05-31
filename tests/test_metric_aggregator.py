"""Tests for metric_aggregator and CombinedToolResults score arithmetic."""

import pytest

from py_cq.localtypes import CombinedToolResults, RawResult, ToolResult
from py_cq.metric_aggregator import aggregate_metrics


def _tr(metrics: dict, tool_name: str = "tool") -> ToolResult:
    """Helper function to create a ToolResult."""
    return ToolResult(metrics=metrics, raw=RawResult(tool_name=tool_name))


def test_score_empty_tool_results():
    """Test that the score for empty tool results is 0.0."""
    c = CombinedToolResults(path=".", tool_results=[])
    assert c.score == 0.0


def test_score_single_metric():
    """Test that the combined score correctly reflects a single metric value."""
    c = CombinedToolResults(path=".", tool_results=[_tr({"m": 0.5})])
    assert c.score == 0.5


def test_score_is_mean_of_per_result_means_not_flat_mean():
    """Test that score is mean of per-result means, not a flat mean of all metrics."""
    # One result: 3 metrics all at 1.0 -> mean 1.0
    # One result: 1 metric at 0.0 -> mean 0.0
    # Score should be (1.0 + 0.0) / 2 = 0.5, not (1+1+1+0)/4 = 0.75
    tr1 = _tr({"a": 1.0, "b": 1.0, "c": 1.0})
    tr2 = _tr({"x": 0.0})
    c = CombinedToolResults(path=".", tool_results=[tr1, tr2])
    assert c.score == 0.5


def test_score_tool_result_with_no_metrics_contributes_zero():
    """Test that tool results with no metrics contribute zero to the score."""
    tr_good = _tr({"m": 1.0})
    tr_empty = _tr({})
    c = CombinedToolResults(path=".", tool_results=[tr_good, tr_empty])
    # tr_empty is excluded from scored list -> only tr_good counts
    assert c.score == 1.0


def test_score_all_metrics_at_one():
    """Test that the combined score is 1.0 when all metrics are 1.0."""
    trs = [_tr({"a": 1.0, "b": 1.0}), _tr({"c": 1.0})]
    c = CombinedToolResults(path=".", tool_results=trs)
    assert c.score == 1.0


def test_aggregate_metrics_matches_direct_construction():
    """Test that aggregating metrics matches direct construction of CombinedToolResults."""
    trs = [_tr({"lint": 0.8}), _tr({"tests": 0.6})]
    via_func = aggregate_metrics("proj/", trs)
    direct = CombinedToolResults(path="proj/", tool_results=trs)
    assert via_func.score == direct.score
    assert via_func.path == direct.path


def test_all_tools_empty_metrics_score_zero():
    """Test that score is zero when all tools have empty metrics."""
    trs = [_tr({}), _tr({})]
    c = CombinedToolResults(path=".", tool_results=trs)
    assert c.score == 0.0


def test_single_tool_multiple_metrics_mean():
    """Test that the mean is correctly calculated for multiple metrics in a single tool result."""
    c = CombinedToolResults(path=".", tool_results=[_tr({"a": 0.8, "b": 0.6})])
    assert c.score == pytest.approx(0.7)


def test_score_is_mean_of_per_tool_means():
    """Test that the combined score is the mean of the per-tool means."""
    trs = [_tr({"m": 0.5}), _tr({"m": 0.75}), _tr({"m": 1.0})]
    c = CombinedToolResults(path=".", tool_results=trs)
    assert c.score == pytest.approx(0.75)


def test_mixed_empty_and_nonempty_tools():
    """Test that empty tool results are excluded from the mean calculation."""
    # Empty tool is excluded from scored list, so only the nonempty tool's mean counts
    tr_good = _tr({"m": 0.6})
    tr_empty = _tr({})
    c = CombinedToolResults(path=".", tool_results=[tr_good, tr_empty])
    assert c.score == pytest.approx(0.6)


@pytest.mark.parametrize(
    "metrics_list",
    [
        [{"a": 0.0}],
        [{"a": 1.0}],
        [{"a": 0.5, "b": 0.3}],
        [{"a": 0.0}, {"b": 1.0}],
        [{"a": 0.5}, {"b": 0.5}, {"c": 0.5}],
        [{"a": 0.0, "b": 0.0}, {"c": 1.0, "d": 1.0}],
    ],
)
def test_score_always_in_bounds(metrics_list):
    trs = [_tr(m) for m in metrics_list]
    c = CombinedToolResults(path=".", tool_results=trs)
    assert 0.0 <= c.score <= 1.0


def test_adding_perfect_tool_never_decreases_score():
    base = [_tr({"m": 0.4})]
    with_perfect = base + [_tr({"m": 1.0})]
    score_base = CombinedToolResults(path=".", tool_results=base).score
    score_with = CombinedToolResults(path=".", tool_results=with_perfect).score
    assert score_with >= score_base


def test_adding_zero_tool_never_increases_score():
    base = [_tr({"m": 0.7})]
    with_zero = base + [_tr({"m": 0.0})]
    score_base = CombinedToolResults(path=".", tool_results=base).score
    score_with = CombinedToolResults(path=".", tool_results=with_zero).score
    assert score_with <= score_base


@pytest.mark.parametrize(
    "metrics_list,expected",
    [
        ([{"m": 0.4}], 0.4),
        ([{"m": 0.6}, {"m": 0.8}], 0.7),
        ([], 0.0),
    ],
)
def test_score_exact_known_values(metrics_list, expected):
    trs = [_tr(m) for m in metrics_list]
    c = CombinedToolResults(path=".", tool_results=trs)
    assert c.score == pytest.approx(expected)
