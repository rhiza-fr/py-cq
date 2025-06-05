import math

import matplotlib.pyplot as plt
import numpy as np


# --- Smoothing Functions (from previous response) ---
def score_exponential_decay(errors, scale_factor=43.29):
    if errors < 0:
        errors = 0
    # Handle potential scale_factor of 0 if errors is also 0
    if scale_factor == 0:
        return 1.0 if errors == 0 else 0.0
    return math.exp(-errors / scale_factor)


def score_inverse_scaling(errors, characteristic_errors=30):
    if errors < 0:
        errors = 0
    # Avoid division by zero if characteristic_errors is 0 and errors is also 0
    if characteristic_errors == 0:
        return 1.0 if errors == 0 else 0.0
    return characteristic_errors / (characteristic_errors + errors)


def score_logistic_variant(errors, scale_factor: float = 30.0, steepness=2):
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
    scores_log = np.array([score_logistic_variant(e, S_log, P_log) for e in errors_range])
    scores_lin = np.array([score_linear_clamped(e, M_lin) for e in errors_range])

    # --- Plotting ---
    plt.figure(figsize=(12, 7))

    plt.plot(errors_range, scores_exp, label=f"Exponential Decay (S={S_exp:.2f})")
    plt.plot(errors_range, scores_inv, label=f"Inverse Scaling (S={S_inv})")
    plt.plot(errors_range, scores_log, label=f"Logistic Variant (S={S_log}, P={P_log})")
    plt.plot(errors_range, scores_lin, label=f"Linear Clamped (M={M_lin})")

    # Highlight the "typical errors = 30" point
    plt.axvline(x=30, color="gray", linestyle="--", linewidth=0.8, label="Typical Errors (e=30)")
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
