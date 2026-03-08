import pytest

from py_cq.parsers.common import (
    find_function_source,
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
