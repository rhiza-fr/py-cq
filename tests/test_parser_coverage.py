"""Tests for CoverageParser."""

from cq.localtypes import RawResult, ToolResult
from cq.parsers.coverageparser import CoverageParser
from conftest import raw

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
