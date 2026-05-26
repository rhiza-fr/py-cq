
from py_cq.parsers.common import (
    _find_project_root,
    find_enclosing_function,
    find_function_source,
    format_source_context,
    inv_normalize,
    read_source_lines,
)


def test_inv_normalize():
    assert inv_normalize(0, 100) == 1.0
    assert inv_normalize(100, 100) == 0.0
    assert inv_normalize(50, 100) == 0.5
    assert inv_normalize(150, 100) == 0.0  # clamped


def test_read_source_lines_valid(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text("line one\nline two\nline three\nline four")
    assert read_source_lines(str(f), 2, count=2) == "line two\nline three"


def test_read_source_lines_missing_file():
    assert read_source_lines("/nonexistent/path.py", 1) == ""


def test_format_source_context_non_int_line():
    assert format_source_context("any_file.py", "not-an-int") == ""


def test_format_source_context_non_int_line_with_context():
    assert format_source_context("any_file.py", "not-an-int", context=2) == ""


def test_format_source_context_valid(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text("line1\nline2\nline3\nline4\nline5\nline6\nline7\nline8\n")
    result = format_source_context(str(f), 4, context=1, count=3)
    assert "```python" in result
    assert "line3" in result


def test_format_source_context_missing_file():
    result = format_source_context("/nonexistent/path.py", 5)
    assert result == ""


def test_format_source_context_stops_at_next_def(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text(
        "def test_one():\n"
        "    x = bad_call(oink=1)\n"
        "\n"
        "def test_two():\n"
        "    pass\n"
    )
    result = format_source_context(str(f), 2, context=0, count=10)
    assert "bad_call" in result
    assert "test_two" not in result


def test_format_source_context_includes_def_containing_error(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text(
        "def test_one():\n"
        "    x = bad_call(oink=1)\n"
        "\n"
        "def test_two():\n"
        "    pass\n"
    )
    result = format_source_context(str(f), 2, context=3, count=10)
    assert "test_one" in result
    assert "bad_call" in result
    assert "test_two" not in result


def test_find_function_source_basic(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text(
        "def unrelated():\n"
        "    pass\n"
        "\n"
        "def test_bar():\n"
        "    x = 1\n"
        "    assert x == 1\n"
        "\n"
        "def after():\n"
        "    pass\n"
    )
    result = find_function_source(str(f), "test_bar", max_lines=10)
    assert "def test_bar" in result
    assert "assert x == 1" in result
    assert "def after" not in result
    assert "```python" in result


def test_find_function_source_truncates(tmp_path):
    f = tmp_path / "foo.py"
    lines = ["def test_long():\n"] + [f"    x = {i}\n" for i in range(20)]
    f.write_text("".join(lines))
    result = find_function_source(str(f), "test_long", max_lines=5)
    assert result.count("\n") <= 7  # fences + 5 lines


def test_find_function_source_not_found(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text("def other(): pass\n")
    assert find_function_source(str(f), "missing", max_lines=10) == ""


def test_find_function_source_missing_file():
    assert find_function_source("/nonexistent/foo.py", "test_x", max_lines=10) == ""


def test_find_function_source_async(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text("async def test_async():\n    await something()\n")
    result = find_function_source(str(f), "test_async", max_lines=10)
    assert "async def test_async" in result


def test_find_project_root_no_pyproject_returns_hint_root(tmp_path):
    """_find_project_root returns the hint file's parent when no pyproject.toml is found."""
    # Use a deeply isolated tmp_path; no pyproject.toml anywhere near it
    isolated = tmp_path / "isolated_subdir"
    isolated.mkdir()
    hint_file = str(isolated / "dummy.py")
    root = _find_project_root(hint_file)
    # Should return the hint file's parent (isolated) without crashing
    assert root is not None
    assert root == isolated


def test_find_project_root_reaches_filesystem_root(tmp_path, monkeypatch):
    """_find_project_root breaks at the filesystem root (parent == current)."""
    from pathlib import Path
    import py_cq.parsers.common as common_mod

    fake_file = tmp_path / "orphan.py"
    fake_file.write_text("")

    # Monkeypatch Path.parent to return the same path after the first call,
    # simulating a filesystem root within 1 traversal step.
    _original_parent = Path.parent.fget  # type: ignore[attr-defined]
    call_count = {"n": 0}

    def _fake_parent(self):
        call_count["n"] += 1
        if call_count["n"] > 1:
            return self  # simulate filesystem root: parent == self
        return _original_parent(self)

    monkeypatch.setattr(Path, "parent", property(_fake_parent))
    root = common_mod._find_project_root(str(fake_file))
    assert root is not None


def test_find_enclosing_function_basic(tmp_path):
    src = tmp_path / "ex.py"
    src.write_text(
        "def outer():\n"
        "    x = 1\n"
        "    y = x + 1\n"
        "    return y\n"
    )
    result = find_enclosing_function(str(src), 3)
    assert "def outer" in result
    assert "y = x + 1" in result


def test_find_enclosing_function_nested(tmp_path):
    src = tmp_path / "ex.py"
    src.write_text(
        "def outer():\n"
        "    def inner():\n"
        "        z = 42\n"
        "    inner()\n"
    )
    result = find_enclosing_function(str(src), 3)
    assert "def inner" in result
    assert "def outer" not in result


def test_find_enclosing_function_module_level(tmp_path):
    src = tmp_path / "ex.py"
    src.write_text("x = 1\ny = 2\n")
    assert find_enclosing_function(str(src), 1) == ""


def test_find_enclosing_function_out_of_range(tmp_path):
    src = tmp_path / "ex.py"
    src.write_text("def foo():\n    pass\n")
    assert find_enclosing_function(str(src), 99) == ""


def test_find_in_project_not_found_multiple_files(tmp_path):
    """Loop visits other project files but find_function_source returns '' — branch 105->101."""
    from py_cq.parsers.common import find_in_project
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    hint = tmp_path / "module.py"
    hint.write_text("def known(): pass\n")
    other = tmp_path / "other.py"
    other.write_text("def also_known(): pass\n")
    result = find_in_project("nonexistent_func", str(hint))
    assert result == ("", "")
