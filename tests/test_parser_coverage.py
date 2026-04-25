"""Tests for CoverageParser."""

import pytest
from conftest import raw

from py_cq.localtypes import RawResult, ToolResult
from py_cq.parsers.coverageparser import CoverageParser

COVERAGE_OUTPUT = """\
Name               Stmts   Miss  Cover
--------------------------------------
src/foo.py            20      2    90%
src/bar.py            10      0   100%
TOTAL                 30      2    93%
"""


def test_coverage_parse():
    tr = CoverageParser().parse(raw(COVERAGE_OUTPUT))
    assert abs(tr.metrics["coverage"] - 0.93) < 0.01
    assert "src/foo.py" in tr.details
    assert abs(tr.details["src/foo.py"]["coverage"] - 0.90) < 0.01
    assert tr.details["src/foo.py"]["missing"] == 2


def test_coverage_parse_empty():
    tr = CoverageParser().parse(raw(""))
    assert tr.metrics == {}


def test_coverage_parse_malformed_miss_count():
    # Non-integer Miss column falls through to missing=None
    output = "src/foo.py  10  bad  90%\nTOTAL  10  bad  90%\n"
    tr = CoverageParser().parse(raw(output))
    assert tr.details["src/foo.py"]["missing"] is None
    assert abs(tr.details["src/foo.py"]["coverage"] - 0.90) < 0.01


def test_coverage_parse_malformed_percentage():
    # Line with invalid percentage is skipped (ValueError branch)
    output = "src/foo.py  10  5  bad%\nTOTAL  10  5  90%\n"
    tr = CoverageParser().parse(raw(output))
    assert abs(tr.metrics["coverage"] - 0.90) < 0.01
    assert "src/foo.py" not in tr.details


def test_coverage_format_llm_message():
    tr = CoverageParser().parse(raw(COVERAGE_OUTPUT))
    msg = CoverageParser().format_llm_message(tr)
    assert "0.930" in msg
    assert "src/foo.py" in msg
    assert "90%" in msg
    assert "2 uncovered" in msg
    assert "src/bar.py" not in msg


def test_coverage_format_llm_message_no_details():
    tr = ToolResult(metrics={"coverage": 0.95}, details={}, raw=RawResult())
    msg = CoverageParser().format_llm_message(tr)
    assert "0.950" in msg


def test_coverage_total_100_with_partial_files():
    """TOTAL 100% wins even when individual files are below 100%."""
    output = (
        "src/foo.py            20      5    75%\n"
        "src/bar.py            10      0   100%\n"
        "TOTAL                 30      0   100%\n"
    )
    tr = CoverageParser().parse(raw(output))
    assert tr.metrics["coverage"] == 1.0
    assert tr.details["src/foo.py"]["coverage"] == pytest.approx(0.75)


def test_coverage_non_numeric_miss_count_scores_zero_does_not_crash():
    """Non-numeric miss count does not crash; coverage still parsed from percentage."""
    output = "src/foo.py  10  bad  0%\nTOTAL  10  bad  0%\n"
    tr = CoverageParser().parse(raw(output))
    assert tr.metrics["coverage"] == pytest.approx(0.0)


def test_coverage_format_llm_message_at_warning_threshold():
    """format_llm_message with file at exactly the warning threshold still reports the file."""
    output = (
        "src/threshold.py          10      1    90%\n"
        "TOTAL                     10      1    90%\n"
    )
    tr = CoverageParser().parse(raw(output))
    msg = CoverageParser().format_llm_message(tr)
    assert "src/threshold.py" in msg
    assert "90%" in msg
    assert "1 uncovered" in msg


def test_coverage_parse_single_token_percent_line():
    """A line with only one token ending in % is skipped — branch 53->51 (len(parts) < 2)."""
    output = "80%\nTOTAL  30  2  93%\n"
    tr = CoverageParser().parse(raw(output))
    assert abs(tr.metrics["coverage"] - 0.93) < 0.01
