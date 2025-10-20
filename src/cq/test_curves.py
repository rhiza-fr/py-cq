"""Utilities for converting error counts into normalized scores in the interval\u202f[0,\u202f1].

This module provides four helper functions that transform a list of error metrics
into a single score bounded between 0 and 1.  The returned score can be used for
thresholding, ranking, or visualising error-based metrics across a dataset.

Functions
---------

``score_exponential_decay(errors, scale_factor=43.29)``
    Uses an exponential decay curve to heavily penalise larger error values.

``score_inverse_scaling(errors, characteristic_errors=30)``
    Applies an inverse-scaling (hyperbolic) function that asymptotically approaches zero.

``score_logistic_variant(errors, scale_factor=30.0, steepness=2)``
    Computes a logistic-style sigmoid with configurable steepness and scale factor.
    Handles edge cases such as negative error values, zero scale factor, and floating-point overflow.

``score_linear_clamped(errors, max_errors_for_nonzero_score=100)``
    Maps errors linearly to a score, clamping the result to zero once the error count
    exceeds a user-specified threshold.

Typical usage
-------------

>>> errors = [5, 12, 20]
>>> score_exponential_decay(errors)
0.123
>>> score_inverse_scaling(errors, characteristic_errors=30)
0.78"""

import math
import matplotlib.pyplot as plt
import numpy as np


def score_exponential_decay(errors, scale_factor=43.29):
    """Calculates an exponential decay score based on errors and a scale factor."""
    if errors < 0:
        errors = 0
    # Handle potential scale_factor of 0 if errors is also 0
    if scale_factor == 0:
        return 1.0 if errors == 0 else 0.0
    return math.exp(-errors / scale_factor)


def score_inverse_scaling(errors, characteristic_errors=30):
    """Calculates an inverse-scaling score that decreases as the number of errors increases.

    Args:
        errors (int): The observed number of errors. Negative values are treated as zero.
        characteristic_errors (int, optional): A threshold representing a characteristic error count. Defaults to 30.

    Returns:
        float: A value in the range [0.0, 1.0].
        • If `errors` is 0, the score is 1.0.
        • Otherwise the score is `characteristic_errors / (characteristic_errors + errors)`.
        • If `characteristic_errors` is 0, the function returns 1.0 only when `errors` is 0; otherwise it returns 0.0.

    Note:
        The function never raises an exception; it normalizes negative error counts to zero and handles a zero characteristic error threshold gracefully."""
    if errors < 0:
        errors = 0
    # Avoid division by zero if characteristic_errors is 0 and errors is also 0
    if characteristic_errors == 0:
        return 1.0 if errors == 0 else 0.0
    return characteristic_errors / (characteristic_errors + errors)


def score_logistic_variant(errors, scale_factor: float = 30.0, steepness=2):
    """Calculates a logistic-like score from a number of errors with optional scaling and steepness.

    The score is defined as
    ``1 / (1 + (errors / scale_factor) ** steepness)``.
    Negative error values are clamped to zero. When ``scale_factor`` is zero the function returns ``1.0`` for zero errors and ``0.0`` otherwise. If the intermediate term would overflow the floating-point range, the function returns ``0.0``.

    Args:
        errors (float | int): The number of errors.  Values less than zero are treated as zero.
        scale_factor (float, optional): The divisor used to scale the error count.  Defaults to 30.0.
        steepness (float | int, optional): The exponent that controls the steepness of the curve.  Defaults to 2.

    Returns:
        float: A score between 0.0 and 1.0, inclusive, where 1.0 indicates no errors and values closer to 0.0 indicate many errors.

    Examples:
        >>> score_logistic_variant(0)
        1.0
        >>> score_logistic_variant(15)
        0.3333333333333333
        >>> score_logistic_variant(-5)
        1.0"""
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


def score_linear_clamped(errors, max_errors_for_nonzero_score=100):
    """Computes a linear score from `errors`, clamped to the range [0.0, 1.0].

    Args:
        errors (int | float): The number of errors.  Negative values are treated as zero.
        max_errors_for_nonzero_score (int | float, optional): The error count at which the score becomes zero.  If this value is non-positive, the function returns 1.0 when there are no errors and 0.0 otherwise.  Defaults to 100.

    Returns:
        float: A score between 0.0 and 1.0.  A score of 1.0 indicates no errors, while a score of 0.0 indicates that the number of errors meets or exceeds the threshold.

    Example:
        >>> score_linear_clamped(10)
        0.9
        >>> score_linear_clamped(150)
        0.0
        >>> score_linear_clamped(-5)
        1.0
        >>> score_linear_clamped(5, max_errors_for_nonzero_score=0)
        0.0"""
    if errors < 0:
        errors = 0
    if max_errors_for_nonzero_score <= 0:
        return 1.0 if errors == 0 else 0.0
    return max(0.0, 1.0 - errors / max_errors_for_nonzero_score)


if __name__ == "__main__":
    # --- Parameters for Plotting ---
    S_exp = 43.29  # For exponential decay, score(30) ~ 0.5
    S_inv = 30  # For inverse scaling, score(30) = 0.5
    S_log = 0.25  # For logistic scale
    P_log = 2  # For logistic steepness
    M_lin = 100  # For linear, score is 0 at 100 errors
    # --- Generate Sample Error Data ---
    # Let's go up to 150 errors to see the tail behavior
    errors_range = np.linspace(0, 1, 300)  # 300 points for smooth curves
    # --- Calculate Scores for each function ---
    scores_exp = np.array([score_exponential_decay(e, S_exp) for e in errors_range])
    scores_inv = np.array([score_inverse_scaling(e, S_inv) for e in errors_range])
    scores_log = np.array(
        [score_logistic_variant(e, S_log, P_log) for e in errors_range]
    )
    scores_lin = np.array([score_linear_clamped(e, M_lin) for e in errors_range])
    # --- Plotting ---
    plt.figure(figsize=(12, 7))
    plt.plot(errors_range, scores_exp, label=f"Exponential Decay (S={S_exp:.2f})")
    plt.plot(errors_range, scores_inv, label=f"Inverse Scaling (S={S_inv})")
    plt.plot(errors_range, scores_log, label=f"Logistic Variant (S={S_log}, P={P_log})")
    plt.plot(errors_range, scores_lin, label=f"Linear Clamped (M={M_lin})")
    # Highlight the "typical errors = 30" point
    plt.axvline(
        x=30, color="gray", linestyle="--", linewidth=0.8, label="Typical Errors (e=30)"
    )
    plt.scatter(
        [30, 30, 30, 30],
        [
            score_exponential_decay(30, S_exp),
            score_inverse_scaling(30, S_inv),
            score_logistic_variant(30, S_log, P_log),
            score_linear_clamped(30, M_lin),
        ],
        color=["blue", "orange", "green", "red"],
    )  # Match line colors
    plt.title("Comparison of Smoothing Functions for Error Scoring")
    plt.xlabel("Number of Errors")
    plt.ylabel("Score (0.0 to 1.0)")
    plt.ylim(-0.05, 1.05)  # Give a little padding for y-axis
    plt.xlim(-0.1, 1.1)  # Give a little padding for x-axis
    plt.legend()
    plt.grid(True, linestyle=":", alpha=0.7)
    plt.show()
    # --- Print scores at key points for verification ---
    print(f"{'Function':<25} | Score at 0 | Score at 30 | Score at 100")
    print("-" * 60)
    print(
        f"{'Exponential Decay':<25} | {score_exponential_decay(0, S_exp):<10.3f} | {score_exponential_decay(30, S_exp):<11.3f} | {score_exponential_decay(100, S_exp):<12.3f}"
    )
    print(
        f"{'Inverse Scaling':<25} | {score_inverse_scaling(0, S_inv):<10.3f} | {score_inverse_scaling(30, S_inv):<11.3f} | {score_inverse_scaling(100, S_inv):<12.3f}"
    )
    print(
        f"{'Logistic Variant':<25} | {score_logistic_variant(0, S_log, P_log):<10.3f} | {score_logistic_variant(30, S_log, P_log):<11.3f} | {score_logistic_variant(100, S_log, P_log):<12.3f}"
    )
    print(
        f"{'Linear Clamped':<25} | {score_linear_clamped(0, M_lin):<10.3f} | {score_linear_clamped(30, M_lin):<11.3f} | {score_linear_clamped(100, M_lin):<12.3f}"
    )
