"""Tests for InterrogateParser."""

from conftest import raw

from py_cq.localtypes import RawResult, ToolResult
from py_cq.parsers.interrogateparser import InterrogateParser

INTERROGATE_OUTPUT = """\
| Name         |  Total |  Miss |  Cover |  Cover% |
|--------------|--------|-------|--------|---------|
| src/foo.py   |      5 |     2 |      3 |     60% |
| src/bar.py   |      3 |     0 |      3 |    100% |
|--------------|--------|-------|--------|---------|
| TOTAL        |      8 |     2 |      6 |   75.0% |
RESULT: your code scored 75.0% on the interrogate score.
Status: FAILED ☒
"""

INTERROGATE_CLEAN = """\
| Name         |  Total |  Miss |  Cover |  Cover% |
|--------------|--------|-------|--------|---------|
| src/foo.py   |      5 |     0 |      5 |    100% |
|--------------|--------|-------|--------|---------|
| TOTAL        |      5 |     0 |      5 |  100.0% |
RESULT: your code scored 100.0% on the interrogate score.
Status: PASSED ☑
"""


def test_interrogate_parse_violations():
    """Test that parse violations are correctly identified."""
    tr = InterrogateParser().parse(raw(INTERROGATE_OUTPUT, return_code=1))
    tr = InterrogateParser().parse(raw(INTERROGATE_OUTPUT, return_code=1))
    assert "doc_coverage" in tr.metrics
    assert tr.metrics["doc_coverage"] == 0.75
    # details contains list-format issues for files where AST parse succeeds;
    # test files don't exist on disk so details is empty, but metrics are always computed


def test_interrogate_parse_skips_zero_missing_files():
    tr = InterrogateParser().parse(raw(INTERROGATE_OUTPUT, return_code=1))
    # bar.py has missing=0, so it is excluded from details
    assert "src/bar.py" not in tr.details


def test_interrogate_parse_clean():
    tr = InterrogateParser().parse(raw(INTERROGATE_CLEAN, return_code=0))
    assert tr.metrics["doc_coverage"] == 1.0
    assert tr.details == {}


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
        details={"src/foo.py": [{"line": 17, "code": "D101", "message": "missing docstring in class `Foo`"}]},
        raw=RawResult(),
    )
    msg = InterrogateParser().format_llm_message(tr)
    assert "src/foo.py" in msg
    assert "D101" in msg


def test_interrogate_parse_zero_total_file():
    """File rows with total=0 are skipped — branch 36->26 (elif total > 0 False)."""
    output = """\
| Name         |  Total |  Miss |  Cover |  Cover% |
|--------------|--------|-------|--------|---------|
| src/empty.py |      0 |     0 |      0 |     0% |
| src/foo.py   |      5 |     1 |      4 |     80% |
|--------------|--------|-------|--------|---------|
| TOTAL        |      5 |     1 |      4 |   80.0% |
RESULT: your code scored 80.0% on the interrogate score.
Status: FAILED ☒
"""
    tr = InterrogateParser().parse(raw(output, return_code=1))
    assert "src/empty.py" not in tr.details
