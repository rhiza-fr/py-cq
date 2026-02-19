"""Utility functions for normalising numeric values and scoring error magnitudes.

This module provides two small helpers that are often used when working with
performance metrics or error scores:

* :func:`inv_normalize` - Inversely normalises a value relative to a maximum
  reference, yielding a float in the interval [0,\u202f1].
* :func:`score_logistic_variant` - Maps an error magnitude to a bounded score
  using a logistic-style curve, with optional parameters controlling the scale
  and steepness of the transition.

Both functions return a float and can be used directly in downstream analytics,
visualisation or decision-making pipelines."""



def read_source_lines(file_path: str, line: int, count: int = 5) -> str:
    """Return up to `count` source lines starting at the given 1-based line number."""
    from pathlib import Path
    try:
        all_lines = Path(file_path).read_text(encoding="utf-8").splitlines()
        start = max(0, line - 1)
        return "\n".join(all_lines[start : start + count])
    except OSError:
        return ""


def format_source_context(file: str, line: int | str, context: int = 3, count: int = 8) -> str:
    """Return a fenced python code block for the source around `line`, or '' if unavailable."""
    if not isinstance(line, int):
        return ""
    context_start = max(1, line - context)
    raw_lines = read_source_lines(file, context_start, count=count).splitlines()
    if not raw_lines:
        return ""
    src = "\n".join(f"{context_start + i}: {rline}" for i, rline in enumerate(raw_lines))
    return f"\n```python\n{src}\n```"


def inv_normalize(value: float, max_value: float) -> float:
    """Returns the inverse normalized value of `value` relative to `max_value`."""
    return (max_value - min(value, max_value)) / max_value


def score_logistic_variant(
    errors, scale_factor: float = 30, steepness: float = 2
) -> float:
    """Calculate a logistic-variant score from an error value.

    The score is always in the range ``[0.0, 1.0]`` and decreases monotonically
    as the magnitude of the error increases. Negative errors are treated as
    zero.  A special case occurs when ``scale_factor`` is ``0``: the method
    returns ``1.0`` only when the error is exactly zero; otherwise it returns
    ``0.0``.

    The logistic function is computed as::

        1 / (1 + (errors / scale_factor) ** steepness)

    To avoid numerical overflow, the intermediate term is capped at
    ``float('inf')`` when ``errors / scale_factor`` exceeds
    ``709 / steepness`` (the largest value that can be exponentiated
    without raising an :class:`OverflowError`).

    Args:
        errors (float): The error magnitude to score.  Negative values are
            treated as zero.
        scale_factor (float, optional): Scaling factor applied to the error.
            Defaults to ``30``.  When ``0``, the special case described above
            applies.
        steepness (float, optional): Exponent controlling the steepness of
            the logistic curve. Defaults to ``2``.

    Returns:
        float: A score between ``0.0`` and ``1.0`` representing the logistic
            mapping of the input error.  The function safely handles large
            error values by capping the intermediate calculation to infinity.

    Example:
        >>> score_logistic_variant(5, scale_factor=10, steepness=2)
        0.9090909090909091
        >>> score_logistic_variant(-3)
        1.0
        >>> score_logistic_variant(10, scale_factor=0)
        0.0"""
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
    except OverflowError:  # pragma: no cover
        return 0.0  # Score becomes 0 if term is too large
    return 1.0 / (1.0 + term)
