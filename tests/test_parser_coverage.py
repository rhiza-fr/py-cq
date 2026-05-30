"""Tests for CoverageParser."""

import ast
from typing import cast

import pytest
from conftest import raw

from py_cq.localtypes import RawResult, ToolResult
from py_cq.parsers.coverageparser import (
    CoverageParser,
    _extract_functions,
    _find_test_file,
    _get_signature,
    _parse_line_ranges,
)

COVERAGE_OUTPUT = """\
Name               Stmts   Miss  Cover
--------------------------------------
src/foo.py            20      2    90%
src/bar.py            10      0   100%
TOTAL                 30      2    93%
"""

COVERAGE_OUTPUT_WITH_MISSING = """\
Name               Stmts   Miss  Cover   Missing
-------------------------------------------------
src/foo.py            20      2    90%   5-6
src/bar.py            10      0   100%
TOTAL                 30      2    93%
"""


# --- parse() ---

def test_coverage_parse_metrics():
    """Test parsing of coverage metrics."""
    tr = CoverageParser().parse(raw(COVERAGE_OUTPUT))
    assert abs(tr.metrics["coverage"] - 0.93) < 0.01


def test_coverage_parse_fallback_entry():
    """Test parsing of fallback entry when no missing lines string is available."""
    # No --show-missing: no missing_lines string, gets fallback entry
    tr = CoverageParser().parse(raw(COVERAGE_OUTPUT))
    assert "src/foo.py" in tr.details
    issues = tr.details["src/foo.py"]
    assert isinstance(issues, list)
    assert issues[0]["code"] is None
    assert issues[0]["missing"] == 2
    assert "src/bar.py" not in tr.details  # 100% excluded


def test_coverage_parse_empty():
    """Test coverage parsing with empty input."""
    tr = CoverageParser().parse(raw(""))
    assert tr.metrics == {}
    assert tr.details == {}


def test_coverage_parse_malformed_miss_count():
    """Test parsing of malformed missing count in coverage output."""
    output = "src/foo.py  10  bad  90%\nTOTAL  10  bad  90%\n"
    tr = CoverageParser().parse(raw(output))
    assert "src/foo.py" in tr.details
    assert tr.details["src/foo.py"][0]["missing"] is None


def test_coverage_parse_malformed_percentage():
    """Test parsing coverage with malformed percentage values."""
    output = "src/foo.py  10  5  bad%\nTOTAL  10  5  90%\n"
    tr = CoverageParser().parse(raw(output))
    assert abs(tr.metrics["coverage"] - 0.90) < 0.01
    assert "src/foo.py" not in tr.details


def test_coverage_parse_with_functions(tmp_path):
    """Test coverage parsing with functions."""
    src_file = tmp_path / "foo.py"
    src_file.write_text("def first():\n    pass\n\ndef second():\n    pass\n")
    # lines 1-2: first, lines 4-5: second; missing lines 4-5
    output = f"{src_file}   4   2   50%   4-5\nTOTAL   4   2   50%\n"
    tr = CoverageParser().parse(raw(output))
    file_key = next(k for k in tr.details if "foo.py" in k)
    issues = tr.details[file_key]
    assert len(issues) == 1
    assert issues[0]["code"] == "second"
    assert issues[0]["line"] == 4
    assert "second" in issues[0]["signature"]


def test_coverage_parse_sorted_worst_first():
    """Test that coverage parsing sorts issues from worst to best."""
    output = (
        "src/good.py   10   1   90%   5\n"
        "src/bad.py    10   7   30%   1-7\n"
        "TOTAL         20   8   60%\n"
    )
    tr = CoverageParser().parse(raw(output))
    assert list(tr.details.keys())[0] == "src/bad.py"


def test_coverage_parse_single_token_percent_line():
    """Test coverage parsing for a single token with percentage line."""
    output = "80%\nTOTAL  30  2  93%\n"
    tr = CoverageParser().parse(raw(output))
    assert abs(tr.metrics["coverage"] - 0.93) < 0.01


def test_coverage_total_100_with_partial_files():
    """Test coverage total calculation with partial files."""
    output = (
        "src/foo.py            20      5    75%\n"
        "src/bar.py            10      0   100%\n"
        "TOTAL                 30      0   100%\n"
    )
    tr = CoverageParser().parse(raw(output))
    assert tr.metrics["coverage"] == 1.0
    assert "src/foo.py" in tr.details


def test_coverage_non_numeric_miss_count_scores_zero_does_not_crash():
    """Test that non-numeric miss count does not crash coverage calculation."""
    output = "src/foo.py  10  bad  0%\nTOTAL  10  bad  0%\n"
    tr = CoverageParser().parse(raw(output))
    assert tr.metrics["coverage"] == pytest.approx(0.0)


# --- format_llm_message() ---

def test_coverage_format_llm_fallback():
    """Test fallback behavior of format_llm_message when no missing lines are present."""
    # No missing_lines → fallback shows file + count
    tr = CoverageParser().parse(raw(COVERAGE_OUTPUT))
    msg = CoverageParser().format_llm_message(tr)
    assert "src/foo.py" in msg
    assert "2 uncovered lines" in msg
    assert "src/bar.py" not in msg


def test_coverage_format_llm_fallback_with_missing_lines():
    """Test coverage formatting when missing lines are present but file doesn't exist."""
    # Has missing lines string but file doesn't exist → fallback shows line numbers
    tr = CoverageParser().parse(raw(COVERAGE_OUTPUT_WITH_MISSING))
    msg = CoverageParser().format_llm_message(tr)
    assert "src/foo.py" in msg
    assert "missing lines: 5-6" in msg


def test_coverage_format_llm_with_function(tmp_path):
    """Test coverage format for LLM with function."""
    src_file = tmp_path / "foo.py"
    src_file.write_text("def my_func(x: int) -> str:\n    return str(x)\n")
    output = f"{src_file}   2   2   0%   1-2\nTOTAL   2   2   0%\n"
    tr = CoverageParser().parse(raw(output))
    msg = CoverageParser().format_llm_message(tr)
    assert "my_func" in msg
    assert "is missing tests" in msg
    assert "def my_func" in msg


def test_coverage_format_llm_with_test_file(tmp_path):
    """Test that the LLM message format includes test files from coverage report."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_foo.py").write_text("")
    src_file = tmp_path / "src" / "foo.py"
    src_file.parent.mkdir(parents=True)
    src_file.write_text("def bar():\n    pass\n")
    output = f"{src_file}   1   1   0%   1-2\nTOTAL   1   1   0%\n"
    tr = CoverageParser().parse(raw(output))
    msg = CoverageParser().format_llm_message(tr)
    assert "Add tests to:" in msg
    assert "test_foo.py" in msg


def test_coverage_format_llm_no_details():
    """Test coverage format LLM with no details."""
    tr = ToolResult(metrics={"coverage": 0.95}, details={}, raw=RawResult())
    assert CoverageParser().format_llm_message(tr) == ""


def test_coverage_format_llm_at_warning_threshold():
    """Test that LLM message is formatted correctly when coverage is at the warning threshold."""
    output = "src/threshold.py   10   1   90%\nTOTAL   10   1   90%\n"
    tr = CoverageParser().parse(raw(output))
    msg = CoverageParser().format_llm_message(tr)
    assert "src/threshold.py" in msg


# --- helpers ---

def test_parse_line_ranges():
    """Test the parsing of line ranges."""
    assert _parse_line_ranges("1-3, 5") == {1, 2, 3, 5}
    assert _parse_line_ranges("10") == {10}
    assert _parse_line_ranges("") == set()
    assert _parse_line_ranges("bad") == set()


def test_get_signature():
    """Test the _get_signature function."""
    node = cast(ast.FunctionDef, ast.parse("def foo(x: int, y: str = 'hi') -> bool:\n    pass\n").body[0])
    sig = _get_signature(node)
    assert sig.startswith("def foo(")
    assert "-> bool" in sig


def test_get_signature_async():
    node = cast(ast.AsyncFunctionDef, ast.parse("async def bar() -> None:\n    pass\n").body[0])
    sig = _get_signature(node)
    assert sig.startswith("async def bar()")


def test_extract_functions(tmp_path):
    src = tmp_path / "mod.py"
    src.write_text("def foo():\n    pass\n\ndef bar():\n    pass\n")
    results = _extract_functions(str(src), "1-2")
    assert len(results) == 1
    assert results[0][0] == "foo"
    assert results[0][1] == 1
    assert results[0][2] == "def foo()"

    results2 = _extract_functions(str(src), "1-2, 4-5")
    assert [r[0] for r in results2] == ["foo", "bar"]


def test_extract_functions_nonexistent():
    assert _extract_functions("/no/such/file.py", "1-10") == []


def test_find_test_file(tmp_path):
    (tmp_path / "tests").mkdir()
    src = tmp_path / "src" / "pkg" / "utils.py"
    src.parent.mkdir(parents=True)
    result = _find_test_file(str(src))
    assert result is not None
    assert result.endswith("test_utils.py")


def test_find_test_file_no_tests_dir(tmp_path):
    src = tmp_path / "utils.py"
    assert _find_test_file(str(src)) is None


def test_find_test_file_null_byte():
    # Should not raise regardless of environment
    result = _find_test_file("\x00")
    assert result is None or isinstance(result, str)
