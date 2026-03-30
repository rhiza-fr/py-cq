"""Tests for execution_engine."""

from unittest.mock import MagicMock, patch

from py_cq.execution_engine import _find_project_root, run_tools
from py_cq.localtypes import RawResult, ToolConfig, ToolResult


def _fake_config(name="fake", order=1):
    class FakeParser:
        def __init__(self, parser_config=None):
            pass
        def parse(self, raw):
            return ToolResult(metrics={"score": 1.0}, raw=raw)
    return ToolConfig(
        name=name, command="echo hi", parser_class=FakeParser,
        order=order, warning_threshold=0.7, error_threshold=0.5,
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


def test_run_tools_sorted_by_order():
    cfg_low = _fake_config("low", order=10)
    cfg_high = _fake_config("high", order=1)
    fake_raw_low = RawResult(tool_name="low", stdout="")
    fake_raw_high = RawResult(tool_name="high", stdout="")

    def fake_run_tool(config, path, excludes=None):
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


# --- run_tools early_exit ---

def _fake_config_with_score(name, order, score, error_threshold=0.5):
    class FakeParser:
        def __init__(self, parser_config=None, _score=score):
            self._score = _score
        def parse(self, raw):
            return ToolResult(metrics={"score": self._score}, raw=raw)
    return ToolConfig(
        name=name, command="echo hi", parser_class=FakeParser,
        order=order, warning_threshold=0.7, error_threshold=error_threshold,
    )


def test_run_tools_early_exit_stops_on_error():
    """When a tool returns an error-level score, subsequent tools must not run."""
    cfg1 = _fake_config_with_score("first", order=1, score=0.0)   # error
    cfg2 = _fake_config_with_score("second", order=2, score=1.0)  # ok
    cfg3 = _fake_config_with_score("third", order=3, score=1.0)   # ok

    called = []
    def fake_run_tool(config, path, excludes=None):
        called.append(config.name)
        return RawResult(tool_name=config.name, stdout="")

    with patch("py_cq.execution_engine.run_tool", side_effect=fake_run_tool):
        results = run_tools([cfg1, cfg2, cfg3], ".", early_exit=True)

    assert called == ["first"]
    assert len(results) == 1
    assert results[0].raw.tool_name == "first"


def test_run_tools_early_exit_continues_past_warning():
    """A warning-level result should not trigger early exit."""
    cfg1 = _fake_config_with_score("first", order=1, score=0.6)   # warning (0.5 < 0.6 < 0.7)
    cfg2 = _fake_config_with_score("second", order=2, score=1.0)  # ok

    called = []
    def fake_run_tool(config, path, excludes=None):
        called.append(config.name)
        return RawResult(tool_name=config.name, stdout="")

    with patch("py_cq.execution_engine.run_tool", side_effect=fake_run_tool):
        results = run_tools([cfg1, cfg2], ".", early_exit=True)

    assert called == ["first", "second"]
    assert len(results) == 2


def test_run_tools_early_exit_false_runs_all_despite_error():
    """Without early_exit, all tools run even when one errors."""
    cfg1 = _fake_config_with_score("first", order=1, score=0.0)   # error
    cfg2 = _fake_config_with_score("second", order=2, score=1.0)  # ok

    called = []
    def fake_run_tool(config, path, excludes=None):
        called.append(config.name)
        return RawResult(tool_name=config.name, stdout="")

    with patch("py_cq.execution_engine.run_tool", side_effect=fake_run_tool):
        results = run_tools([cfg1, cfg2], ".", early_exit=False)

    assert set(called) == {"first", "second"}
    assert len(results) == 2


# --- run_tool (cache miss path) ---

def test_run_tool_cache_miss_calls_subprocess(tmp_path):
    from py_cq.execution_engine import run_tool
    cfg = ToolConfig(
        name="echo", command="echo {context_path}",
        parser_class=MagicMock, order=1,
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
        parser_class=MagicMock, order=1,
        warning_threshold=0.7, error_threshold=0.5,
    )
    cached = RawResult(tool_name="echo", stdout="cached!")
    # Build the cache key the same way run_tool does
    import sys
    from pathlib import Path

    from py_cq.context_hash import get_context_hash
    input_path_posix = Path(str(tmp_path)).as_posix().rstrip("/")
    command = cfg.command.format(context_path=str(tmp_path), abs_context_path=str(tmp_path), input_path_posix=input_path_posix, python=sys.executable, exclude="")
    cache_key = f"{command}:{get_context_hash(str(tmp_path))}"
    fake_cache = {cache_key: cached.to_dict()}

    with patch("py_cq.execution_engine._cache", fake_cache):
        with patch("py_cq.execution_engine.subprocess.run") as mock_sub:
            result = run_tool(cfg, str(tmp_path))
    mock_sub.assert_not_called()
    assert result.stdout == "cached!"


# --- run_tool: run_in_target_env ---

def test_run_tool_target_env_uv_not_found(tmp_path):
    """When uv is not on PATH, python stays as sys.executable."""
    from py_cq.execution_engine import run_tool
    cfg = ToolConfig(
        name="check", command="{python} -m check {context_path}",
        parser_class=MagicMock, order=1,
        warning_threshold=0.7, error_threshold=0.5,
        run_in_target_env=True,
    )
    mock_result = MagicMock(stdout="ok", stderr="", returncode=0)
    mock_cache = MagicMock()
    mock_cache.__contains__ = MagicMock(return_value=False)
    with patch("py_cq.execution_engine._cache", mock_cache), \
         patch("py_cq.execution_engine.shutil.which", return_value=None), \
         patch("py_cq.execution_engine.subprocess.run", return_value=mock_result) as mock_sub:
        run_tool(cfg, str(tmp_path))
    # uv not found → python stays as sys.executable
    import sys
    called_cmd = mock_sub.call_args[0][0]
    assert sys.executable in called_cmd


def test_run_tool_target_env_uv_found_directory(tmp_path):
    """When uv is found and path is a directory, python becomes uv run."""
    from py_cq.execution_engine import run_tool
    cfg = ToolConfig(
        name="check", command="{python} -m check {context_path}",
        parser_class=MagicMock, order=1,
        warning_threshold=0.7, error_threshold=0.5,
        run_in_target_env=True,
    )
    mock_result = MagicMock(stdout="ok", stderr="", returncode=0)
    mock_cache = MagicMock()
    mock_cache.__contains__ = MagicMock(return_value=False)
    fake_uv = "/usr/bin/uv"
    with patch("py_cq.execution_engine._cache", mock_cache), \
         patch("py_cq.execution_engine.shutil.which", return_value=fake_uv), \
         patch("py_cq.execution_engine.subprocess.run", return_value=mock_result) as mock_sub:
        run_tool(cfg, str(tmp_path))
    called_cmd = mock_sub.call_args[0][0]
    assert "uv" in called_cmd
    assert "run" in called_cmd


def test_run_tool_target_env_uv_found_file(tmp_path):
    """When uv is found and path is a file, project root is found."""
    from py_cq.execution_engine import run_tool
    (tmp_path / "pyproject.toml").write_text("")
    py_file = tmp_path / "foo.py"
    py_file.write_text("x = 1")
    cfg = ToolConfig(
        name="check", command="{python} -m check {context_path}",
        parser_class=MagicMock, order=1,
        warning_threshold=0.7, error_threshold=0.5,
        run_in_target_env=True,
    )
    mock_result = MagicMock(stdout="ok", stderr="", returncode=0)
    mock_cache = MagicMock()
    mock_cache.__contains__ = MagicMock(return_value=False)
    fake_uv = "/usr/bin/uv"
    with patch("py_cq.execution_engine._cache", mock_cache), \
         patch("py_cq.execution_engine.shutil.which", return_value=fake_uv), \
         patch("py_cq.execution_engine.subprocess.run", return_value=mock_result) as mock_sub:
        run_tool(cfg, str(py_file))
    called_cmd = mock_sub.call_args[0][0]
    assert "uv" in called_cmd


def test_run_tool_target_env_with_extra_deps(tmp_path):
    """Extra deps are included in the uv command as --with flags."""
    from py_cq.execution_engine import run_tool
    cfg = ToolConfig(
        name="check", command="{python} -m check {context_path}",
        parser_class=MagicMock, order=1,
        warning_threshold=0.7, error_threshold=0.5,
        run_in_target_env=True,
        extra_deps=["pytest", "coverage"],
    )
    mock_result = MagicMock(stdout="ok", stderr="", returncode=0)
    mock_cache = MagicMock()
    mock_cache.__contains__ = MagicMock(return_value=False)
    fake_uv = "/usr/bin/uv"
    with patch("py_cq.execution_engine._cache", mock_cache), \
         patch("py_cq.execution_engine.shutil.which", return_value=fake_uv), \
         patch("py_cq.execution_engine.subprocess.run", return_value=mock_result) as mock_sub:
        run_tool(cfg, str(tmp_path))
    called_cmd = mock_sub.call_args[0][0]
    assert "--with pytest" in called_cmd
    assert "--with coverage" in called_cmd
