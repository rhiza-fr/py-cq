"""Tests for ExitCodeParser."""
from conftest import raw
from py_cq.parsers.exitcodeparser import ExitCodeParser


def test_exit_code_zero_scores_1():
    """Test that exit code 0 scores 1.0."""
    result = ExitCodeParser().parse(raw(stdout="all good", return_code=0))
    assert result.metrics == {"exit_code": 1.0}


def test_exit_code_nonzero_scores_0():
    """Test that exit code 0 is not captured when return code is non-zero."""
    result = ExitCodeParser().parse(raw(stdout="error here", return_code=1))
    assert result.metrics == {"exit_code": 0.0}


def test_exit_code_2_scores_0():
    """Test that exit code 2 results in a score of 0.0."""
    result = ExitCodeParser().parse(raw(stdout="", return_code=2))
    assert result.metrics == {"exit_code": 0.0}


def test_llm_message_shows_stdout():
    """Test that the LLM message shows stdout."""
    from py_cq.localtypes import RawResult, ToolResult
    tr = ToolResult(
        metrics={"exit_code": 0.0},
        raw=RawResult(tool_name="t", command="c", stdout="line1\nline2\nline3", return_code=1),
    )
    msg = ExitCodeParser().format_llm_message(tr, context_lines=2)
    assert "line1" in msg
    assert "line2" in msg


def test_llm_message_falls_back_to_stderr():
    from py_cq.localtypes import RawResult, ToolResult
    tr = ToolResult(
        metrics={"exit_code": 0.0},
        raw=RawResult(tool_name="t", command="c", stdout="", stderr="fatal error", return_code=1),
    )
    msg = ExitCodeParser().format_llm_message(tr, context_lines=5)
    assert "fatal error" in msg
