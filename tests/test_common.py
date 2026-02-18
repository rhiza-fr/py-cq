import pytest

from py_cq.parsers.common import (
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
