"""Integration tests: cache speeds up repeated cq check invocations.

Runs ``cq check -o score`` twice on the project itself, measures elapsed
wall time, and verifies the second run is substantially faster because all
tool results are served from diskcache.
"""

import subprocess
import sys
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent.parent


def _cq_invoke(args: list[str]) -> tuple[int, float]:
    """Run cq check via subprocess and return (exit_code, elapsed_seconds)."""
    cq = HERE / ".venv" / "Scripts" / "cq.exe"
    assert cq.exists(), f"cq not found at {cq}"
    cmd = [str(cq), "check", str(HERE)] + args
    t0 = time.perf_counter()
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
    )
    elapsed = time.perf_counter() - t0
    return result.returncode, elapsed


def test_cache_speeds_up_repeated_invocation():
    """Second cq check on unchanged code is served from cache: < 25% time, < 0.5 s."""
    tools = "compile,ruff,radon-cc,radon-mi,radon-hal"

    # First run — cold cache.
    code1, t_first = _cq_invoke(["--clear-cache", "-o", "score", "--only", tools, "--workers", "1"])

    # Second run — should hit cache.
    code2, t_second = _cq_invoke(["-o", "score", "--only", tools, "--workers", "1"])

    # Both must produce the same exit code.
    assert code1 == code2, f"exit codes differ: {code1} vs {code2}"

    ratio = t_second / t_first if t_first > 0 else 999
    msg = (
        f"first={t_first:.3f}s  second={t_second:.3f}s  "
        f"ratio={ratio:.1%}  (expected <25%, <0.5s)"
    )
    print(f"\n  {msg}", file=sys.stderr)
    assert t_second < 0.5, f"second run too slow: {t_second:.3f}s — {msg}"
    assert t_second < t_first * 0.25, f"second run not fast enough: {msg}"
