"""Tests for RuffFormatParser."""

import json

from conftest import raw
from typer.testing import CliRunner

from py_cq.cli import app
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


def test_ruff_format_parse_ruff_015_output():
    """ruff < 0.16 ignores --output-format for format and prints 'Would reformat:' lines."""
    output = (
        "Would reformat: D:\\proj\\src\\a.py\n"
        "Would reformat: D:\\proj\\tests\\test_a.py\n"
        "2 files would be reformatted, 6 files already formatted\n"
    )
    tr = RuffFormatParser().parse(raw(output, return_code=1))
    assert tr.metrics["formatted"] == 0.75
    assert tr.details == {"D:/proj/src/a.py": [{}], "D:/proj/tests/test_a.py": [{}]}


def test_ruff_format_score_uses_summary_count():
    """An unrecognised per-file line format still lowers the score via the summary."""
    output = "something new\n2 files would be reformatted, 6 files already formatted\n"
    tr = RuffFormatParser().parse(raw(output, return_code=1))
    assert tr.metrics["formatted"] == 0.75


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
    output = "a.py:1:1: unformatted: File would be reformatted\n1 file would be reformatted\n"
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


def test_ruff_format_ignores_markdown(tmp_path):
    """Python code blocks in Markdown are not counted, even though ruff formats them.

    ruff's ``--exclude *.md`` does not reliably drop Markdown files, so the
    built-in command overrides ``include`` instead; this guards that override.
    """
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "README.md").write_text("```python\nx  =  1   # aligned\n```\n")
    result = CliRunner().invoke(
        app, ["check", str(tmp_path), "--only", "ruff-format", "-o", "json"]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data[0]["metrics"]["formatted"] == 1.0
