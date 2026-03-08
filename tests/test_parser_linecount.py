"""Tests for LineCountParser."""
from conftest import raw
from py_cq.parsers.linecountparser import LineCountParser


def test_no_output_scores_1():
    result = LineCountParser().parse(raw(stdout=""))
    assert result.metrics["violations"] == 1.0


def test_blank_lines_ignored():
    result = LineCountParser().parse(raw(stdout="\n\n\n"))
    assert result.metrics["violations"] == 1.0


def test_single_violation_scores_below_1():
    result = LineCountParser().parse(raw(stdout="error: something wrong"))
    assert 0.0 < result.metrics["violations"] < 1.0


def test_more_violations_score_lower():
    few = LineCountParser().parse(raw(stdout="e1\ne2"))
    many = LineCountParser().parse(raw(stdout="\n".join(f"e{i}" for i in range(20))))
    assert many.metrics["violations"] < few.metrics["violations"]


def test_custom_scale_factor():
    # With scale_factor=1, a single error should score much lower than default scale_factor=15
    strict = LineCountParser({"scale_factor": 1}).parse(raw(stdout="one error"))
    default = LineCountParser().parse(raw(stdout="one error"))
    assert strict.metrics["violations"] < default.metrics["violations"]


def test_llm_message_shows_first_line():
    from py_cq.localtypes import RawResult, ToolResult
    tr = ToolResult(
        metrics={"violations": 0.5},
        raw=RawResult(tool_name="t", command="c", stdout="first error\nsecond error"),
        details={"lines": ["first error", "second error"]},
    )
    msg = LineCountParser().format_llm_message(tr, context_lines=5)
    assert "first error" in msg
