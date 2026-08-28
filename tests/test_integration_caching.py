"""Integration tests: cache speeds up repeated cq check invocations.

Runs ``cq check -o score`` twice on the project itself, measures elapsed
wall time, and verifies the second run is substantially faster because all
tool results are served from diskcache.
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent


def _find_cq() -> str:
    """Dodgy where am i"""
    if found := shutil.which("cq"):
        return found
    scripts = "Scripts" if os.name == "nt" else "bin"
    exe = "cq.exe" if os.name == "nt" else "cq"
    candidate = HERE / ".venv" / scripts / exe
    assert candidate.exists(), f"cq not found on PATH or at {candidate}"
    return str(candidate)


def _cq_invoke(args: list[str]) -> tuple[int, float]:
    """Run cq check via subprocess and return (exit_code, elapsed_seconds)."""
    cmd = [_find_cq(), "check", str(HERE)] + args
    t0 = time.perf_counter()
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    elapsed = time.perf_counter() - t0
    return result.returncode, elapsed


@pytest.mark.slow
def test_cache_speeds_up_repeated_invocation():
    """Second cq check on unchanged code is served from cache: < 0.5 s, < 35% time."""
    tools = "compile,ruff,radon-cc,radon-mi,radon-hal"

    # First run - cold cache.
    code1, t_first = _cq_invoke(
        ["--clear-cache", "-o", "score", "--only", tools, "--workers", "1"]
    )

    # Second run - should hit cache.
    code2, t_second = _cq_invoke(["-o", "score", "--only", tools, "--workers", "1"])

    # Both must produce the same exit code.
    assert code1 == code2, f"exit codes differ: {code1} vs {code2}"

    ratio = t_second / t_first if t_first > 0 else 999
    msg = (
        f"first={t_first:.3f}s  second={t_second:.3f}s  "
        f"ratio={ratio:.1%}  (expected <0.5s, <35%)"
    )
    print(f"\n  {msg}", file=sys.stderr)
    # The absolute bound is the property that matters: a warm run is dominated by
    # interpreter and CLI startup, which no cache can remove. The ratio is a loose
    # sanity check only - it tightens on its own every time the cold path gets
    # faster, so keep it well clear of the observed value rather than snug.
    assert t_second < 0.5, f"second run too slow: {t_second:.3f}s - {msg}"
    assert t_second < t_first * 0.35, f"second run not fast enough: {msg}"
