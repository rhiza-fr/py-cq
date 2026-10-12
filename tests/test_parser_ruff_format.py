"""Tests for RuffFormatParser."""

from conftest import raw

from py_cq.localtypes import RawResult, ToolResult
from py_cq.parsers.ruffformatparser import RuffFormatParser

UNFORMATTED_OUTPUT = """\
src\\pkg\\a.py:151:13: unformatted: File would be reformatted
src/pkg/b.py:3:1: unformatted: File would be reformatted
2 files would be reformatted, 6 files already formatted
"""


def test_ruff_format_parse_unformatted():
    """Unformatted files are collected with forward slashes and scored as a fraction."""
    tr = RuffFormatParser().parse(raw(UNFORMATTED_OUTPUT, return_code=1))
    assert tr.metrics["formatted"] == 0.75
    assert tr.details == {"src/pkg/a.py": [{}], "src/pkg/b.py": [{}]}


def test_ruff_format_parse_clean():
    """All files formatted scores 1.0 with no details."""
    tr = RuffFormatParser().parse(raw("8 files already formatted\n"))
    assert tr.metrics["formatted"] == 1.0
    assert tr.details == {}


def test_ruff_format_parse_single_file_clean():
    """The singular summary form is parsed."""
    tr = RuffFormatParser().parse(raw("1 file already formatted\n"))
    assert tr.metrics["formatted"] == 1.0


def test_ruff_format_parse_all_unformatted():
    """No 'already formatted' count means every checked file needs formatting."""
    output = (
        "a.py:1:1: unformatted: File would be reformatted\n1 file would be reformatted\n"
    )
    tr = RuffFormatParser().parse(raw(output, return_code=1))
    assert tr.metrics["formatted"] == 0.0


def test_ruff_format_parse_empty_output():
    """No files checked scores 1.0."""
    tr = RuffFormatParser().parse(raw(""))
    assert tr.metrics["formatted"] == 1.0


def test_ruff_format_llm_message_suggests_command():
    """The LLM message tells it to run the formatter on the file."""
    tr = ToolResult(
        metrics={"formatted": 0.5}, details={"src/a.py": [{}]}, raw=RawResult()
    )
    msg = RuffFormatParser().format_llm_message(tr)
    assert "ruff format src/a.py" in msg
    assert "do not edit by hand" in msg


def test_ruff_format_llm_message_no_details():
    """Missing details give a fallback message."""
    tr = ToolResult(metrics={"formatted": 0.5}, details={}, raw=RawResult())
    assert "no details" in RuffFormatParser().format_llm_message(tr).lower()
