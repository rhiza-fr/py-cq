"""Tests for InterrogateParser."""

from conftest import raw

from py_cq.localtypes import RawResult, ToolResult
from py_cq.parsers.interrogateparser import InterrogateParser

INTERROGATE_OUTPUT = """\
------------ Interrogate Results -------------------
| Name                     |  Total |  Miss | Cover |
|---------------------------------------------------|
| src/foo.py               |      5 |     2 |   60% |
| src/bar.py               |      3 |     0 |  100% |
|---------------------------------------------------|
| TOTAL                    |      8 |     2 |   75% |
RESULT: your code scored 75.0% on the interrogate score.
Status: FAILED ☒
"""

INTERROGATE_CLEAN = """\
------------ Interrogate Results -------------------
| Name                     |  Total |  Miss | Cover |
|---------------------------------------------------|
| src/foo.py               |      5 |     0 |  100% |
|---------------------------------------------------|
| TOTAL                    |      5 |     0 |  100% |
RESULT: your code scored 100.0% on the interrogate score.
Status: PASSED ☑
"""


def test_interrogate_parse_violations():
    tr = InterrogateParser().parse(raw(INTERROGATE_OUTPUT, return_code=1))
    assert "doc_coverage" in tr.metrics
    assert tr.metrics["doc_coverage"] == 0.75
    assert "src/foo.py" in tr.details
    assert tr.details["src/foo.py"]["missing"] == 2
    assert tr.details["src/foo.py"]["coverage"] == 0.60


def test_interrogate_parse_skips_zero_total_files():
    tr = InterrogateParser().parse(raw(INTERROGATE_OUTPUT, return_code=1))
    # bar.py has total=3 so it should be included
    assert "src/bar.py" in tr.details


def test_interrogate_parse_clean():
    tr = InterrogateParser().parse(raw(INTERROGATE_CLEAN, return_code=0))
    assert tr.metrics["doc_coverage"] == 1.0
    assert tr.details["src/foo.py"]["missing"] == 0


def test_interrogate_parse_empty_output():
    tr = InterrogateParser().parse(raw("", return_code=0))
    assert tr.metrics["doc_coverage"] == 1.0
    assert tr.details == {}


def test_interrogate_format_llm_no_issues():
    tr = ToolResult(metrics={"doc_coverage": 1.0}, details={}, raw=RawResult())
    assert "1.000" in InterrogateParser().format_llm_message(tr)


def test_interrogate_format_llm_with_missing():
    tr = ToolResult(
        metrics={"doc_coverage": 0.75},
        details={"src/foo.py": {"total": 5, "missing": 2, "coverage": 0.60}},
        raw=RawResult(),
    )
    msg = InterrogateParser().format_llm_message(tr)
    assert "src/foo.py" in msg
    assert "2 undocumented" in msg
