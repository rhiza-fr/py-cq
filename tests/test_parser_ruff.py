"""Tests for RuffParser."""

from conftest import raw

from py_cq.localtypes import RawResult, ToolResult
from py_cq.parsers.ruffparser import RuffParser

RUFF_OUTPUT = """\
src/foo.py:10:1: E501 line too long (100 > 79 characters)
src/foo.py:20:5: F841 local variable 'x' is assigned but never used
src/bar.py:5:1: F401 `os` imported but unused
Found 3 errors.
"""


def test_ruff_parse_violations():
    tr = RuffParser().parse(raw(RUFF_OUTPUT, return_code=1))
    assert "lint" in tr.metrics
    assert tr.metrics["lint"] < 1.0
    assert "src/foo.py" in tr.details
    assert len(tr.details["src/foo.py"]) == 2
    assert tr.details["src/foo.py"][0]["code"] == "E501"


def test_ruff_parse_clean():
    tr = RuffParser().parse(raw("All checks passed!\n", return_code=0))
    assert tr.metrics["lint"] == 1.0
    assert tr.details == {}


def test_ruff_format_llm_no_details():
    tr = ToolResult(metrics={"lint": 0.5}, details={}, raw=RawResult())
    assert "no details" in RuffParser().format_llm_message(tr).lower()
