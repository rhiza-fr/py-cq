"""Tests for PydocstyleParser."""

from cq.localtypes import RawResult, ToolResult
from cq.parsers.pydocstyleparser import PydocstyleParser
from conftest import raw

PYDOC_OUTPUT = """\
./src/foo.py:1 at module level:
        D100: Missing docstring in public module
./src/foo.py:10 in public function `bar`:
        D103: Missing docstring in public function
"""

PYDOC_WITH_NOISE = """\
some irrelevant header line
./src/foo.py:1 at module level:
        D100: Missing docstring in public module
another noise line
"""


def test_pydocstyle_parse_violations():
    tr = PydocstyleParser().parse(raw(PYDOC_OUTPUT, return_code=1))
    assert "docstyle" in tr.metrics
    assert tr.metrics["docstyle"] < 1.0
    assert "src/foo.py" in tr.details
    assert len(tr.details["src/foo.py"]) == 2
    assert tr.details["src/foo.py"][0]["code"] == "D100"


def test_pydocstyle_parse_clean():
    tr = PydocstyleParser().parse(raw("", return_code=0))
    assert tr.metrics["docstyle"] == 1.0
    assert tr.details == {}


def test_pydocstyle_parse_with_noise():
    tr = PydocstyleParser().parse(raw(PYDOC_WITH_NOISE))
    assert "src/foo.py" in tr.details
    assert len(tr.details["src/foo.py"]) == 1


def test_pydocstyle_format_llm_no_details():
    tr = ToolResult(metrics={"docstyle": 0.5}, details={}, raw=RawResult())
    assert "no details" in PydocstyleParser().format_llm_message(tr).lower()
