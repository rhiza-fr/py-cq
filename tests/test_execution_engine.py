"""Tests for execution_engine."""

from unittest.mock import MagicMock, patch

from py_cq.execution_engine import _find_project_root, run_tools
from py_cq.localtypes import RawResult, ToolConfig, ToolResult


def _fake_config(name="fake", priority=1):
    class FakeParser:
        def parse(self, raw):
            return ToolResult(metrics={"score": 1.0}, raw=raw)
    return ToolConfig(
        name=name, command="echo hi", parser_class=FakeParser,
        priority=priority, warning_threshold=0.7, error_threshold=0.5,
    )


# --- _find_project_root ---

def test_find_project_root_direct(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    py_file = tmp_path / "foo.py"
    py_file.write_text("")
    assert _find_project_root(py_file) == tmp_path


def test_find_project_root_nested(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    sub = tmp_path / "src" / "pkg"
    sub.mkdir(parents=True)
    py_file = sub / "mod.py"
    py_file.write_text("")
    assert _find_project_root(py_file) == tmp_path


def test_find_project_root_not_found(tmp_path):
    py_file = tmp_path / "foo.py"
    py_file.write_text("")
    # tmp_path has no pyproject.toml; parents likely don't either
    result = _find_project_root(py_file)
    assert result is None or (result / "pyproject.toml").exists()


# --- run_tools ---

def test_run_tools_returns_results():
    cfg = _fake_config()
    fake_raw = RawResult(tool_name="fake", stdout="hi")
    with patch("py_cq.execution_engine.run_tool", return_value=fake_raw):
        results = run_tools([cfg], ".")
    assert len(results) == 1
    assert results[0].metrics["score"] == 1.0


def test_run_tools_sorted_by_priority():
    cfg_low = _fake_config("low", priority=10)
    cfg_high = _fake_config("high", priority=1)
    fake_raw_low = RawResult(tool_name="low", stdout="")
    fake_raw_high = RawResult(tool_name="high", stdout="")

    def fake_run_tool(config, path):
        return fake_raw_low if config.name == "low" else fake_raw_high

    with patch("py_cq.execution_engine.run_tool", side_effect=fake_run_tool):
        results = run_tools([cfg_low, cfg_high], ".")
    assert results[0].raw.tool_name == "high"
    assert results[1].raw.tool_name == "low"


def test_run_tools_exception_is_logged():
    cfg = _fake_config()
    with patch("py_cq.execution_engine.run_tool", side_effect=RuntimeError("boom")):
        with patch("py_cq.execution_engine.log") as mock_log:
            results = run_tools([cfg], ".")
    assert results == []
    mock_log.error.assert_called_once()


def test_run_tools_empty():
    results = run_tools([], ".")
    assert results == []


# --- run_tool (cache miss path) ---

def test_run_tool_cache_miss_calls_subprocess(tmp_path):
    from py_cq.execution_engine import run_tool
    cfg = ToolConfig(
        name="echo", command="echo {context_path}",
        parser_class=MagicMock, priority=1,
        warning_threshold=0.7, error_threshold=0.5,
    )
    mock_result = MagicMock()
    mock_result.stdout = "hello"
    mock_result.stderr = ""
    mock_result.returncode = 0

    mock_cache = MagicMock()
    mock_cache.__contains__ = MagicMock(return_value=False)
    with patch("py_cq.execution_engine._cache", mock_cache):
        with patch("py_cq.execution_engine.subprocess.run", return_value=mock_result) as mock_sub:
            result = run_tool(cfg, str(tmp_path))
    mock_sub.assert_called_once()
    assert result.tool_name == "echo"
    assert result.stdout == "hello"


def test_run_tool_cache_hit_skips_subprocess(tmp_path):
    from py_cq.execution_engine import run_tool
    cfg = ToolConfig(
        name="echo", command="echo {context_path}",
        parser_class=MagicMock, priority=1,
        warning_threshold=0.7, error_threshold=0.5,
    )
    cached = RawResult(tool_name="echo", stdout="cached!")
    # Build the cache key the same way run_tool does
    import sys
    from pathlib import Path

    from py_cq.context_hash import get_context_hash
    input_path_posix = Path(str(tmp_path)).as_posix().rstrip("/")
    command = cfg.command.format(context_path=str(tmp_path), abs_context_path=str(tmp_path), input_path_posix=input_path_posix, python=sys.executable)
    cache_key = f"{command}:{get_context_hash(str(tmp_path))}"
    fake_cache = {cache_key: cached.to_dict()}

    with patch("py_cq.execution_engine._cache", fake_cache):
        with patch("py_cq.execution_engine.subprocess.run") as mock_sub:
            result = run_tool(cfg, str(tmp_path))
    mock_sub.assert_not_called()
    assert result.stdout == "cached!"
