"""Tests for TyParser."""

from cq.localtypes import RawResult, ToolResult
from cq.parsers.typarser import TyParser
from conftest import raw

TY_OUTPUT = """\
src/baz.py:7:5: error[invalid-return-type] return type mismatch
src/baz.py:15:1: warning[unused-import] `os` imported but unused
Found 2 diagnostics.
"""


def test_ty_parse_diagnostics():
    tr = TyParser().parse(raw(TY_OUTPUT, return_code=1))
    assert "type_check" in tr.metrics
    assert tr.metrics["type_check"] < 1.0
    assert "src/baz.py" in tr.details
    issues = tr.details["src/baz.py"]
    assert issues[0]["severity"] == "error"
    assert issues[1]["severity"] == "warning"


def test_ty_parse_clean():
    tr = TyParser().parse(raw("All checks passed!\n", return_code=0))
    assert tr.metrics["type_check"] == 1.0
    assert tr.details == {}


def test_ty_format_llm_no_details():
    tr = ToolResult(metrics={"type_check": 0.5}, details={}, raw=RawResult())
    assert "no details" in TyParser().format_llm_message(tr).lower()
