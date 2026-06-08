"""Tests for the shared SourceFile cache."""

import ast

from py_cq.source_file import SourceFile, get_source


def test_text_decodes_utf8(tmp_path):
    """text returns the decoded file contents."""
    f = tmp_path / "m.py"
    f.write_bytes(b"x = 1\n")
    assert get_source(str(f)).text == "x = 1\n"


def test_tree_parses_once(tmp_path):
    """tree returns a parsed AST and caches the same object."""
    f = tmp_path / "m.py"
    f.write_text("def f():\n    return 1\n")
    sf = get_source(str(f))
    assert isinstance(sf.tree, ast.Module)
    assert sf.tree is sf.tree


def test_tree_none_on_syntax_error(tmp_path):
    """tree is None when the file can't be parsed."""
    f = tmp_path / "broken.py"
    f.write_text("def f(:\n")
    assert get_source(str(f)).tree is None


def test_norm_digest_invariant_to_docstrings_comments_format(tmp_path):
    """norm_digest ignores docstrings, comments, and formatting."""
    f = tmp_path / "m.py"
    f.write_text("def f(x):\n    return x + 1\n")
    d1 = SourceFile(str(f)).norm_digest
    f.write_text('def f(x):\n    """Add one."""  # comment\n    return  x + 1\n')
    d2 = SourceFile(str(f)).norm_digest
    assert d1 == d2


def test_norm_digest_detects_logic_change(tmp_path):
    """norm_digest changes when executable code changes."""
    f = tmp_path / "m.py"
    f.write_text("def f(x):\n    return x + 1\n")
    d1 = SourceFile(str(f)).norm_digest
    f.write_text("def f(x):\n    return x + 2\n")
    assert SourceFile(str(f)).norm_digest != d1


def test_norm_digest_byte_fallback_on_syntax_error(tmp_path):
    """norm_digest falls back to a byte digest for unparseable files."""
    f = tmp_path / "broken.py"
    f.write_text("def f(:\n")
    d1 = SourceFile(str(f)).norm_digest
    assert isinstance(d1, str) and len(d1) == 32
    f.write_text("def f(::\n")
    assert SourceFile(str(f)).norm_digest != d1


def test_norm_digest_keeps_tree_pristine(tmp_path):
    """Computing norm_digest must not strip docstrings from the shared tree."""
    f = tmp_path / "m.py"
    f.write_text('def f():\n    """Doc."""\n    return 1\n')
    sf = get_source(str(f))
    _ = sf.norm_digest
    assert sf.functions[0].has_docstring is True


def test_functions_reports_signature_and_docstring(tmp_path):
    """functions exposes name, span, signature, and docstring presence."""
    f = tmp_path / "m.py"
    f.write_text(
        "def a(x: int) -> int:\n"
        '    """Doc."""\n'
        "    return x\n"
        "\n"
        "async def b(y):\n"
        "    return y\n"
    )
    funcs = {fn.name: fn for fn in get_source(str(f)).functions}
    assert funcs["a"].signature == "def a(x: int) -> int"
    assert funcs["a"].has_docstring is True
    assert funcs["b"].signature == "async def b(y)"
    assert funcs["b"].has_docstring is False
    assert funcs["a"].lineno == 1
    assert funcs["a"].end_lineno == 3


def test_definitions_includes_classes(tmp_path):
    """definitions reports classes alongside functions, in source order."""
    f = tmp_path / "m.py"
    f.write_text("class C:\n    def m(self):\n        return 1\n")
    defs = get_source(str(f)).definitions
    kinds = {d.name: d.kind for d in defs}
    assert kinds == {"C": "class", "m": "function"}
    assert [d.lineno for d in defs] == sorted(d.lineno for d in defs)


def test_module_has_docstring(tmp_path):
    """module_has_docstring reflects the presence of a module docstring."""
    with_doc = tmp_path / "a.py"
    with_doc.write_text('"""Module doc."""\nx = 1\n')
    without_doc = tmp_path / "b.py"
    without_doc.write_text("x = 1\n")
    assert get_source(str(with_doc)).module_has_docstring is True
    assert get_source(str(without_doc)).module_has_docstring is False


def test_get_source_memoizes_same_key(tmp_path):
    """get_source returns the same instance for an unchanged file."""
    f = tmp_path / "m.py"
    f.write_text("x = 1\n")
    assert get_source(str(f)) is get_source(str(f))


def test_get_source_misses_after_content_change(tmp_path):
    """A content change (new mtime) yields a fresh SourceFile."""
    import os

    f = tmp_path / "m.py"
    f.write_text("x = 1\n")
    first = get_source(str(f))
    f.write_text("x = 2\n")
    st = f.stat()
    os.utime(f, (st.st_mtime + 100, st.st_mtime + 100))
    assert get_source(str(f)) is not first
