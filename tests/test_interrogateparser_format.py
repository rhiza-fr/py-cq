"""Tests for _format_missing_docstring in InterrogateParser."""

from py_cq.parsers.interrogateparser import _format_missing_docstring


def test_d100_module_docstring(tmp_path):
    """Test D100 by checking if the formatted message is correct for a module without a docstring."""
    f = tmp_path / "mod.py"
    f.write_text("x = 1\n")
    msg = _format_missing_docstring(str(f), 1, "D100", "missing module docstring")
    assert "Insert a module-level docstring as the very first statement" in msg


def test_d103_function_insertion_line(tmp_path):
    """Verify that D103 suggests inserting a docstring on the first line of the function body.

    Args:
        tmp_path: A pytest fixture providing a temporary directory.
    """
    f = tmp_path / "funcs.py"
    f.write_text("def greet(name: str) -> str:\n    return 'hi'\n")
    msg = _format_missing_docstring(str(f), 1, "D103", "missing docstring in function `greet`")
    assert "Insert a docstring on line 2" in msg


def test_d103_return_annotation_hint(tmp_path):
    f = tmp_path / "funcs.py"
    f.write_text("def count() -> int:\n    return 42\n")
    msg = _format_missing_docstring(str(f), 1, "D103", "missing docstring in function `count`")
    assert "Return" in msg
    assert "`int`" in msg


def test_d103_no_return_annotation(tmp_path):
    f = tmp_path / "funcs.py"
    f.write_text("def setup(config):\n    pass\n")
    msg = _format_missing_docstring(str(f), 1, "D103", "missing docstring in function `setup`")
    assert "Do <action>" in msg


def test_d103_params_listed(tmp_path):
    f = tmp_path / "funcs.py"
    f.write_text("def process(data, timeout):\n    pass\n")
    msg = _format_missing_docstring(str(f), 1, "D103", "missing docstring in function `process`")
    assert "`data`" in msg
    assert "`timeout`" in msg


def test_d103_self_param_excluded(tmp_path):
    f = tmp_path / "cls.py"
    f.write_text("class Foo:\n    def run(self, x):\n        pass\n")
    msg = _format_missing_docstring(str(f), 2, "D103", "missing docstring in function `run`")
    assert "`self`" not in msg
    assert "`x`" in msg


def test_d101_class_insertion_line(tmp_path):
    f = tmp_path / "cls.py"
    f.write_text("class MyClass:\n    x = 1\n")
    msg = _format_missing_docstring(str(f), 1, "D101", "missing docstring in class `MyClass`")
    assert "Insert a docstring on line 2" in msg
    assert "class body" in msg


def test_file_not_found_fallback():
    msg = _format_missing_docstring("/nonexistent/file.py", 5, "D103", "missing docstring in function `foo`")
    assert "Insert a docstring as the first statement in the body" in msg


def test_line_not_matched_fallback(tmp_path):
    f = tmp_path / "funcs.py"
    f.write_text("def real_func():\n    pass\n")
    # Line 99 doesn't exist in the file
    msg = _format_missing_docstring(str(f), 99, "D103", "missing docstring in function `foo`")
    assert "Insert a docstring as the first statement in the body" in msg
