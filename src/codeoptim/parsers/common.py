def inv_normalize(value: float, max_value: float) -> float:
    return (max_value - min(value, max_value)) / max_value
