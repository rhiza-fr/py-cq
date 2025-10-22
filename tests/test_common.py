import pytest
from cq.parsers.common import score_logistic_variant


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
