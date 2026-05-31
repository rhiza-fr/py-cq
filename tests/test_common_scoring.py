"""Module for testing common scoring functions."""
import pytest

from py_cq.parsers.common import (
    extract_callee_name,
    find_in_project,
    format_callee_context,
    score_logistic_variant,
)


def test_extract_callee_name_assignment():
    """Test extracting callee name from an assignment."""
    assert extract_callee_name("    result = make_registry(oink=2)") == "make_registry"


def test_extract_callee_name_plain_call():
    """Test extracting callee name from a plain function call."""
    assert extract_callee_name("    make_registry(a, b)") == "make_registry"


def test_extract_callee_name_method_call():
    """Test that extract_callee_name returns the method name for a method call."""
    # Returns the method name, not the object
    assert extract_callee_name("    result = obj.do_thing()") == "do_thing"


def test_extract_callee_name_assert_keyword_returns_none():
    """Test that extract_callee_name returns None when an assert keyword is found."""
    assert extract_callee_name("    assert True") is None


def test_extract_callee_name_plain_statement_call():
    """Test extracting callee name from a plain statement call."""
    assert extract_callee_name("    something()") == "something"


def test_extract_callee_name_no_call():
    """Test extract_callee_name when no function call is present."""
    assert extract_callee_name("    x = 1 + 2") is None


def test_find_in_project_same_file(tmp_path):
    """Test that find_in_project correctly finds a function in the same file."""
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    f = tmp_path / "module.py"
    f.write_text("def my_func(a, b):\n    return a + b\n")
    path, block = find_in_project("my_func", str(f))
    assert "def my_func" in block
    assert path != ""


def test_find_in_project_other_file(tmp_path):
    """Test finding a definition in a different file within the same project."""
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    src = tmp_path / "utils.py"
    src.write_text("def helper(x):\n    return x * 2\n")
    caller = tmp_path / "test_module.py"
    caller.write_text("from utils import helper\n")
    path, block = find_in_project("helper", str(caller))
    assert "def helper" in block
    assert path != ""


def test_find_in_project_not_found(tmp_path):
    """Test find_in_project when the function is not found in the project."""
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    f = tmp_path / "module.py"
    f.write_text("x = 1\n")
    assert find_in_project("nonexistent_func", str(f)) == ("", "")


def test_format_callee_context_includes_label(tmp_path):
    """Test that format_callee_context includes the label."""
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    f = tmp_path / "module.py"
    f.write_text("def my_func(a, b):\n    return a + b\n")
    result = format_callee_context("my_func", str(f))
    assert "`my_func` is defined at:" in result
    assert "module.py:1" in result
    assert "def my_func" in result


def test_format_callee_context_not_found(tmp_path):
    """Test format_callee_context when callee context is not found."""
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    f = tmp_path / "module.py"
    f.write_text("x = 1\n")
    assert format_callee_context("missing", str(f)) == ""


def test_score_logistic_large_base():
    # base > 709/steepness triggers float("inf") branch
    assert score_logistic_variant(1e300, scale_factor=1.0) == 0.0


def test_score_logistic_steepness_zero():
    """steepness=0 raises ZeroDivisionError due to 709/steepness; document the behavior."""
    import pytest
    with pytest.raises(ZeroDivisionError):
        score_logistic_variant(10, scale_factor=30, steepness=0)


def test_score_logistic_very_large_errors():
    """Very large error count approaches 0.0 without overflow."""
    result = score_logistic_variant(1_000_000_000, scale_factor=30)
    assert result == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize(
    "errors,scale_factor,steepness,expected",
    [
        (5, 10, 2, 0.8),
        (-3, 30, 2, 1.0),
        (10, 0, 2, 0.0),
        (0, 0, 2, 1.0),
        (0, 30, 2, 1.0),
        (30, 30, 2, 0.5),
        (60, 30, 2, 0.2),
        (100, 30, 2, 1 / (1 + (100 / 30) ** 2)),
        (1000, 30, 2, 1 / (1 + (1000 / 30) ** 2)),
        (0, 30, 1, 1.0),
        (30, 30, 1, 0.5),
        (30, 30, 3, 0.5),
    ],
)
def test_score_logistic_variant(errors, scale_factor, steepness, expected):
    result = score_logistic_variant(errors, scale_factor, steepness)
    assert result == expected


@pytest.mark.parametrize("errors,scale,steepness,lo,hi", [
    (0, 10, 1.0, 0.95, 1.0),
    (1, 10, 1.0, 0.85, 1.0),
    (10, 10, 1.0, 0.4, 0.6),
    (100, 10, 1.0, 0.0, 0.1),
    (0, 1, 0.1, 0.95, 1.0),
])
def test_score_logistic_variant_boundaries(errors, scale, steepness, lo, hi):
    result = score_logistic_variant(errors, scale, steepness)
    assert lo <= result <= hi


@pytest.mark.parametrize("value,max_value,expected", [
    (0.0, 100.0, 1.0),
    (100.0, 100.0, 0.0),
    (50.0, 100.0, 0.5),
])
def test_inv_normalize_parametrized(value, max_value, expected):
    from py_cq.parsers.common import inv_normalize
    assert inv_normalize(value, max_value) == pytest.approx(expected)


def test_inv_normalize_zero_max():
    """inv_normalize(v, 0) returns 1.0 - zero-sized reference means no deviation."""
    from py_cq.parsers.common import inv_normalize
    assert inv_normalize(0.0, 0.0) == 1.0
    assert inv_normalize(5.0, 0.0) == 1.0


@pytest.mark.parametrize("errors", [0, 5, 20, 100, 1000])
def test_score_logistic_monotone_decreasing(errors):
    """score_logistic_variant is non-increasing as errors increase."""
    prev = score_logistic_variant(errors, scale_factor=30, steepness=2)
    nxt = score_logistic_variant(errors + 1, scale_factor=30, steepness=2)
    assert nxt <= prev


@pytest.mark.parametrize("errors", [-1, -10, -100])
def test_score_logistic_negative_errors_returns_one(errors):
    """Negative error counts always return exactly 1.0."""
    assert score_logistic_variant(errors, scale_factor=30, steepness=2) == 1.0


@pytest.mark.parametrize("value,max_value,expected", [
    (0.0, 50.0, 1.0),
    (50.0, 50.0, 0.0),
    (150.0, 50.0, 0.0),
    (25.0, 50.0, 0.5),
    (1.0, 1.0, 0.0),
    (0.0, 1.0, 1.0),
])
def test_inv_normalize_extended(value, max_value, expected):
    from py_cq.parsers.common import inv_normalize
    assert inv_normalize(value, max_value) == pytest.approx(expected)
