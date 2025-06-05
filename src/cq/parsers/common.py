def inv_normalize(value: float, max_value: float) -> float:
    return (max_value - min(value, max_value)) / max_value


def score_logistic_variant(errors, scale_factor: float = 30, steepness: float = 2) -> float:
    if errors < 0:
        errors = 0
    if scale_factor == 0:
        return 1.0 if errors == 0 else 0.0
    try:
        # Handle case where errors/scale_factor is very large, to avoid overflow
        base = errors / scale_factor
        if base > 709 / steepness:  # exp(709) is near max float
            term = float("inf")
        else:
            term = base**steepness
    except OverflowError:
        return 0.0  # Score becomes 0 if term is too large
    return 1.0 / (1.0 + term)
