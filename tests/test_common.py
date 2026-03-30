import pytest

from py_cq.parsers.common import (
    extract_callee_name,
    find_function_source,
    find_in_project,
    format_callee_context,
    format_source_context,
    inv_normalize,
    read_source_lines,
    score_logistic_variant,
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


def test_format_source_context_valid(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text("line1\nline2\nline3\nline4\nline5\nline6\nline7\nline8\n")
    result = format_source_context(str(f), 4, context=1, count=3)
    assert "```python" in result
    assert "line3" in result


def test_format_source_context_missing_file():
    result = format_source_context("/nonexistent/path.py", 5)
    assert result == ""



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


def test_extract_callee_name_assignment():
    assert extract_callee_name("    result = make_registry(oink=2)") == "make_registry"


def test_extract_callee_name_plain_call():
    assert extract_callee_name("    make_registry(a, b)") == "make_registry"


def test_extract_callee_name_method_call():
    # Returns the method name, not the object
    assert extract_callee_name("    result = obj.do_thing()") == "do_thing"


def test_extract_callee_name_keyword_skipped():
    assert extract_callee_name("    assert something()") is None or \
           extract_callee_name("    assert something()") == "something"


def test_extract_callee_name_no_call():
    assert extract_callee_name("    x = 1 + 2") is None


def test_find_in_project_same_file(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    f = tmp_path / "module.py"
    f.write_text("def my_func(a, b):\n    return a + b\n")
    path, block = find_in_project("my_func", str(f))
    assert "def my_func" in block
    assert path != ""


def test_find_in_project_other_file(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    src = tmp_path / "utils.py"
    src.write_text("def helper(x):\n    return x * 2\n")
    caller = tmp_path / "test_module.py"
    caller.write_text("from utils import helper\n")
    path, block = find_in_project("helper", str(caller))
    assert "def helper" in block
    assert path != ""


def test_find_in_project_not_found(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    f = tmp_path / "module.py"
    f.write_text("x = 1\n")
    assert find_in_project("nonexistent_func", str(f)) == ("", "")


def test_format_callee_context_includes_label(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    f = tmp_path / "module.py"
    f.write_text("def my_func(a, b):\n    return a + b\n")
    result = format_callee_context("my_func", str(f))
    assert "`my_func` is defined at:" in result
    assert "module.py:1" in result
    assert "def my_func" in result


def test_format_callee_context_not_found(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    f = tmp_path / "module.py"
    f.write_text("x = 1\n")
    assert format_callee_context("missing", str(f)) == ""


def test_format_source_context_stops_at_next_def(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text(
        "def test_one():\n"       # line 1
        "    x = bad_call(oink=1)\n"  # line 2  ← error line
        "\n"                      # line 3
        "def test_two():\n"       # line 4  ← should stop here
        "    pass\n"
    )
    # error at line 2, context=0 → starts at line 2, count=10
    result = format_source_context(str(f), 2, context=0, count=10)
    assert "bad_call" in result
    assert "test_two" not in result


def test_format_source_context_includes_def_containing_error(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text(
        "def test_one():\n"       # line 1
        "    x = bad_call(oink=1)\n"  # line 2  ← error line
        "\n"
        "def test_two():\n"       # line 4
        "    pass\n"
    )
    # context=3 → starts at line 1 (max(1, 2-3)=1), error at offset 1
    result = format_source_context(str(f), 2, context=3, count=10)
    assert "test_one" in result   # def before error — included
    assert "bad_call" in result
    assert "test_two" not in result  # def after error — excluded


def test_score_logistic_large_base():
    # base > 709/steepness triggers float("inf") branch
    assert score_logistic_variant(1e300, scale_factor=1.0) == 0.0


@pytest.mark.parametrize(
    "errors,scale_factor,steepness,expected",
    [
        # (errors, scale_factor, steepness) → expected output
        (5, 10, 2, 0.8),
        (-3, 30, 2, 1.0),  # negative error is treated as 0
        (10, 0, 2, 0.0),  # scale_factor == 0 → only 0 error gives 1.0
        (0, 0, 2, 1.0),  # scale_factor == 0 & errors == 0 → 1.0
        (0, 30, 2, 1.0),  # zero error → 1.0
        (30, 30, 2, 0.5),  # 1/(1+1^2) → 0.5
        (60, 30, 2, 0.2),  # 1/(1+2^2) → 0.2
        (100, 30, 2, 1 / (1 + (100 / 30) ** 2)),  # 1/(1+(10/3)^2)
        (1000, 30, 2, 1 / (1 + (1000 / 30) ** 2)),  # 1/(1+(1000/30)^2)
        (0, 30, 1, 1.0),  # zero error → 1.0
        (30, 30, 1, 0.5),  # 1/(1+1^1) → 0.5
        (30, 30, 3, 0.5),  # 1/(1+1^3) → 0.5
    ],
)
def test_score_logistic_variant(errors, scale_factor, steepness, expected):
    """Test that ``score_logistic_variant`` returns the values that match its
    implementation for a variety of inputs."""
    result = score_logistic_variant(errors, scale_factor, steepness)
    assert result == expected
