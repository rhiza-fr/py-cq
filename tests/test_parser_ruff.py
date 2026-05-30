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
    """Test that Ruff output is correctly parsed into violations."""
    tr = RuffParser().parse(raw(RUFF_OUTPUT, return_code=1))
    tr = RuffParser().parse(raw(RUFF_OUTPUT, return_code=1))
    assert "lint" in tr.metrics
    assert tr.metrics["lint"] < 1.0
    assert "src/foo.py" in tr.details
    assert len(tr.details["src/foo.py"]) == 2
    issue = tr.details["src/foo.py"][0]
    assert issue["code"] == "E501"
    assert issue["col"] == 1


def test_ruff_parse_clean():
    """Test parsing of clean Ruff output."""
    tr = RuffParser().parse(raw("All checks passed!\n", return_code=0))
    assert tr.metrics["lint"] == 1.0
    assert tr.details == {}


def test_ruff_format_llm_no_details():
    """Test Ruff parser formatting when details are empty."""
    tr = ToolResult(metrics={"lint": 0.5}, details={}, raw=RawResult())
    assert "no details" in RuffParser().format_llm_message(tr).lower()


def test_ruff_format_E721(tmp_path):
    src = tmp_path / "example.py"
    src.write_text("def f(output_type):\n    if output_type == str:\n        pass\n")
    tr = ToolResult(
        metrics={"lint": 0.5},
        details={str(src): [{"line": 2, "col": 20, "code": "E721", "message": "Use `is` and `is not` for type comparisons, or `isinstance()` for isinstance checks"}]},
        raw=RawResult(),
    )
    msg = RuffParser().format_llm_message(tr)
    assert "output_type == str" in msg
    assert "isinstance" in msg


def test_ruff_format_E701(tmp_path):
    src = tmp_path / "example.py"
    src.write_text("x = 1\nif x: pass\n")
    tr = ToolResult(
        metrics={"lint": 0.5},
        details={str(src): [{"line": 2, "col": 5, "code": "E701", "message": "Multiple statements on one line (colon)"}]},
        raw=RawResult(),
    )
    msg = RuffParser().format_llm_message(tr)
    assert "if x: pass" in msg
    assert "split" in msg.lower()


def test_ruff_hint_F841_referenced_elsewhere(tmp_path):
    src = tmp_path / "example.py"
    src.write_text(
        "def foo():\n"
        "    n_pending = get_count()\n"  # line 2 — the violation
        "    return n_pending + 1\n"     # line 3 — other reference
    )
    tr = ToolResult(
        metrics={"lint": 0.5},
        details={str(src): [{"line": 2, "code": "F841", "message": "Local variable `n_pending` is assigned to but never used"}]},
        raw=RawResult(),
    )
    msg = RuffParser().format_llm_message(tr)
    assert "n_pending" in msg
    assert "referenced at line" in msg
    assert "3" in msg


def test_ruff_hint_F841_not_referenced(tmp_path):
    src = tmp_path / "example.py"
    src.write_text(
        "def foo():\n"
        "    unused_var = compute()\n"  # line 2 — only occurrence
        "    return 42\n"
    )
    tr = ToolResult(
        metrics={"lint": 0.5},
        details={str(src): [{"line": 2, "code": "F841", "message": "Local variable `unused_var` is assigned to but never used"}]},
        raw=RawResult(),
    )
    msg = RuffParser().format_llm_message(tr)
    assert "Delete line 2" in msg


def test_ruff_hint_F541(tmp_path):
    src = tmp_path / "example.py"
    src.write_text('x = f"no placeholders here"\n')
    tr = ToolResult(
        metrics={"lint": 0.5},
        details={str(src): [{"line": 1, "code": "F541", "message": "[*] f-string without any placeholders"}]},
        raw=RawResult(),
    )
    msg = RuffParser().format_llm_message(tr)
    assert "remove the `f` prefix" in msg


def test_ruff_hint_F401_safe_to_delete(tmp_path):
    src = tmp_path / "mod.py"
    src.write_text("import os\n\ndef foo():\n    return 42\n")
    tr = ToolResult(
        metrics={"lint": 0.5},
        details={str(src): [{"line": 1, "code": "F401", "message": "[*] `os` imported but unused"}]},
        raw=RawResult(),
    )
    msg = RuffParser().format_llm_message(tr)
    assert "Delete this import" in msg
    assert "ruff check --fix" in msg


def test_ruff_hint_F401_soft_uses(tmp_path):
    src = tmp_path / "mod.py"
    src.write_text(
        "from typing import Optional\n"
        "\n"
        'def foo(x: "Optional[int]") -> None:\n'
        "    pass\n"
    )
    tr = ToolResult(
        metrics={"lint": 0.5},
        details={str(src): [{"line": 1, "code": "F401", "message": "[*] `typing.Optional` imported but unused"}]},
        raw=RawResult(),
    )
    msg = RuffParser().format_llm_message(tr)
    assert "appears elsewhere" in msg
    assert "line 3" in msg


def test_ruff_hint_F821_with_conditional_import(tmp_path):
    src = tmp_path / "server.py"
    src.write_text(
        'def create_server() -> "FastMCP":\n'       # line 1 — violation
        "    from mcp.server.fastmcp import FastMCP\n"  # line 2 — ref
        '    return FastMCP("app")\n'               # line 3 — ref
    )
    tr = ToolResult(
        metrics={"lint": 0.5},
        details={str(src): [{"line": 1, "code": "F821", "message": "Undefined name `FastMCP`"}]},
        raw=RawResult(),
    )
    msg = RuffParser().format_llm_message(tr)
    assert "FastMCP" in msg
    assert "line 2" in msg
    assert "line 3" in msg


def test_ruff_hint_F821_not_found(tmp_path):
    src = tmp_path / "mod.py"
    src.write_text("def foo():\n    return Unknown()\n")
    tr = ToolResult(
        metrics={"lint": 0.5},
        details={str(src): [{"line": 2, "code": "F821", "message": "Undefined name `Unknown`"}]},
        raw=RawResult(),
    )
    msg = RuffParser().format_llm_message(tr)
    assert "not imported or defined" in msg
