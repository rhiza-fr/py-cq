"""Tests for RegexCountParser."""
import pytest
from conftest import raw
from py_cq.parsers.regexcountparser import RegexCountParser


def _parser(pattern, scale_factor=15):
    """Parser factory function."""
    return RegexCountParser({"pattern": pattern, "scale_factor": scale_factor})


def test_no_matches_scores_1():
    """Test that zero matches results in a score of 1.0."""
    result = _parser(r"^ERROR").parse(raw(stdout="info: all good\ninfo: done"))
    assert result.metrics["violations"] == 1.0


def test_matching_lines_counted():
    """Test that matching lines are correctly counted."""
    stdout = "ERROR: bad\ninfo: ok\nERROR: worse"
    result = _parser(r"^ERROR").parse(raw(stdout=stdout))
    assert 0.0 < result.metrics["violations"] < 1.0
    assert result.details["count"] == 2


def test_more_matches_score_lower():
    few = _parser(r"^E").parse(raw(stdout="E1\nok\nok"))
    many = _parser(r"^E").parse(raw(stdout="\n".join(f"E{i}" for i in range(20))))
    assert many.metrics["violations"] < few.metrics["violations"]


def test_missing_pattern_raises():
    with pytest.raises(KeyError):
        RegexCountParser({}).parse(raw(stdout="anything"))


def test_llm_message_shows_first_match():
    from py_cq.localtypes import RawResult, ToolResult
    tr = ToolResult(
        metrics={"violations": 0.5},
        raw=RawResult(tool_name="t", command="c", stdout=""),
        details={"count": 2, "matches": ["ERROR: first", "ERROR: second"]},
    )
    msg = _parser(r"^ERROR").format_llm_message(tr, context_lines=5)
    assert "ERROR: first" in msg


def test_format_llm_message_no_violations():
    from py_cq.localtypes import RawResult, ToolResult
    tr = ToolResult(metrics={"violations": 1.0}, raw=RawResult(), details={"count": 0, "matches": []})
    assert _parser(r"^ERROR").format_llm_message(tr) == "No violations found"
