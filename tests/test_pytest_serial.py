"""Tests for the pytest_serial runner used by the coverage tool."""

import runpy
import sys

import pytest

from py_cq.execution_engine import _PYTEST_SERIAL


def _run(monkeypatch, *, has_xdist: bool) -> list[str]:
    """Run the script as __main__ and return the args it passed to pytest.main."""
    calls: list[list[str]] = []
    monkeypatch.setattr(sys, "argv", [_PYTEST_SERIAL, "tests", "-q"])
    monkeypatch.setattr(sys, "path", ["runner-dir", *sys.path])
    monkeypatch.setattr(pytest, "main", lambda args: calls.append(args) or 3)
    monkeypatch.setattr(
        "importlib.util.find_spec",
        lambda name: object() if has_xdist and name == "xdist" else None,
    )
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(_PYTEST_SERIAL, run_name="__main__")
    assert exc.value.code == 3
    return calls[0]


def test_disables_xdist_when_installed(monkeypatch):
    assert _run(monkeypatch, has_xdist=True) == ["tests", "-q", "-n", "0"]


def test_passes_args_through_without_xdist(monkeypatch):
    assert _run(monkeypatch, has_xdist=False) == ["tests", "-q"]


def test_replaces_script_dir_with_cwd_on_sys_path(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _run(monkeypatch, has_xdist=False)
    assert sys.path[0] == str(tmp_path)
    assert "runner-dir" not in sys.path
