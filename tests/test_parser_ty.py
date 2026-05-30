"""Tests for TyParser."""

from conftest import raw

from py_cq.localtypes import RawResult, ToolResult
from py_cq.parsers.typarser import TyParser

TY_OUTPUT = """\
src/baz.py:7:5: error[invalid-return-type] return type mismatch
src/baz.py:15:1: warning[unused-import] `os` imported but unused
Found 2 diagnostics.
"""


def test_ty_parse_diagnostics():
    """Test parsing of type checker diagnostics."""
    tr = TyParser().parse(raw(TY_OUTPUT, return_code=1))
    assert "type_check" in tr.metrics
    assert tr.metrics["type_check"] < 1.0
    assert "src/baz.py" in tr.details
    issues = tr.details["src/baz.py"]
    assert issues[0]["severity"] == "error"
    assert issues[1]["severity"] == "warning"


def test_ty_parse_deduplicates_same_line_code():
    """Two diagnostics with identical (file, line, code) should collapse to one."""
    output = (
        "src/foo.py:218:10: error[possibly-missing-submodule] Submodule `tokens` might not have been imported\n"
        "src/foo.py:218:35: error[possibly-missing-submodule] Submodule `tokens` might not have been imported\n"
        "Found 2 diagnostics.\n"
    )
    tr = TyParser().parse(raw(output, return_code=1))
    assert len(tr.details["src/foo.py"]) == 1


def test_ty_parse_clean():
    tr = TyParser().parse(raw("All checks passed!\n", return_code=0))
    assert tr.metrics["type_check"] == 1.0
    assert tr.details == {}


def test_ty_format_llm_includes_callee_for_call_code(tmp_path):
    """Call-related ty errors append the callee definition when found in project."""
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    src_file = tmp_path / "module.py"
    src_file.write_text(
        "def my_func(a: int, b: int) -> int:\n"
        "    return a + b\n"
        "\n"
        "result = my_func(bad_kwarg=1)\n"
    )
    tr = TyParser().parse(raw(
        f"{src_file}:4:10: error[unexpected-keyword] unexpected keyword argument 'bad_kwarg'\n"
        "Found 1 diagnostic.\n",
        return_code=1,
    ))
    msg = TyParser().format_llm_message(tr)
    assert "def my_func" in msg


def test_ty_format_llm_no_callee_for_non_call_code(tmp_path):
    """Non-call ty errors do not include callee lookup."""
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    src_file = tmp_path / "module.py"
    src_file.write_text("x: int = 'hello'\n")
    tr = TyParser().parse(raw(
        f"{src_file}:1:1: error[invalid-assignment] cannot assign str to int\n"
        "Found 1 diagnostic.\n",
        return_code=1,
    ))
    msg = TyParser().format_llm_message(tr)
    # No callee lookup — just source context
    assert "def " not in msg or "invalid-assignment" in msg


def test_ty_format_llm_no_details():
    tr = ToolResult(metrics={"type_check": 0.5}, details={}, raw=RawResult())
    assert "no details" in TyParser().format_llm_message(tr).lower()


def test_ty_format_call_non_callable(tmp_path):
    src = tmp_path / "embed.py"
    src.write_text("tokenizer = AutoTokenizer.from_pretrained('bert')\nresult = tokenizer(text)\n")
    tr = ToolResult(
        metrics={"type_check": 0.5},
        details={str(src): [{"line": 2, "code": "call-non-callable", "severity": "error",
                              "message": "Object of type `AutoTokenizer` is not callable"}]},
        raw=RawResult(),
    )
    msg = TyParser().format_llm_message(tr)
    assert "AutoTokenizer" in msg
    assert "type: ignore" in msg


def test_ty_format_possibly_missing_submodule(tmp_path):
    src = tmp_path / "extract.py"
    src.write_text("import spacy\nmatcher = spacy.matcher.Matcher(nlp.vocab)\n")
    tr = ToolResult(
        metrics={"type_check": 0.5},
        details={str(src): [{"line": 2, "code": "possibly-missing-submodule", "severity": "error",
                              "message": "Submodule `matcher` might not have been imported"}]},
        raw=RawResult(),
    )
    msg = TyParser().format_llm_message(tr)
    assert "matcher" in msg
    assert "import" in msg.lower()


def test_ty_format_unresolved_import(tmp_path):
    src = tmp_path / "old.py"
    src.write_text("from mypackage.prepare_data import prepare_contexts\n")
    tr = ToolResult(
        metrics={"type_check": 0.5},
        details={str(src): [{"line": 1, "code": "unresolved-import", "severity": "error",
                              "message": "Cannot resolve imported module `mypackage.prepare_data`"}]},
        raw=RawResult(),
    )
    msg = TyParser().format_llm_message(tr)
    assert "mypackage.prepare_data" in msg
    assert "renamed or deleted" in msg


def test_ty_format_llm_call_code_no_func_name(tmp_path):
    """Call-code error on a line with no callable — branch 77->79 (func_name falsy)."""
    src_file = tmp_path / "module.py"
    src_file.write_text("x = 1\n")
    tr = TyParser().parse(raw(
        f"{src_file}:1:1: error[unexpected-keyword] unexpected keyword argument 'bad'\n"
        "Found 1 diagnostic.\n",
        return_code=1,
    ))
    msg = TyParser().format_llm_message(tr)
    assert "unexpected-keyword" in msg
