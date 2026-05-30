"""Tests for execution_engine."""

import sys
from unittest.mock import MagicMock, patch

from py_cq.execution_engine import _build_exclude_str, _dep_in_venv, _find_project_root, run_tools
from py_cq.localtypes import RawResult, ToolConfig, ToolResult


def _fake_config(name="fake", order=1):
    """Create a fake ToolConfig for testing purposes."""
    class FakeParser:
        """Fake parser for testing."""
        def __init__(self, parser_config=None):
            """Initialize FakeParser."""
            pass
        def parse(self, raw):
            """Parse the raw output."""
            return ToolResult(metrics={"score": 1.0}, raw=raw)
    return ToolConfig(
        name=name, command="echo hi", parser_class=FakeParser,
        order=order, warning_threshold=0.7, error_threshold=0.5,
    )


# --- _find_project_root ---

def test_find_project_root_direct(tmp_path):
    """Test that _find_project_root returns the tmp_path when pyproject.toml is present."""
    (tmp_path / "pyproject.toml").write_text("")
    py_file = tmp_path / "foo.py"
    py_file.write_text("")
    assert _find_project_root(py_file) == tmp_path


def test_find_project_root_nested(tmp_path):
    """Test finding project root when nested inside directories."""
    (tmp_path / "pyproject.toml").write_text("")
    sub = tmp_path / "src" / "pkg"
    sub.mkdir(parents=True)
    py_file = sub / "mod.py"
    py_file.write_text("")
    assert _find_project_root(py_file) == tmp_path


def test_find_project_root_not_found(tmp_path, monkeypatch):
    """Test that _find_project_root returns tmp_path when no project root is found in parents."""
    sub = tmp_path / "orphan"
    sub.mkdir()
    py_file = sub / "foo.py"
    py_file.write_text("")
    # Patch Path.parents so the walk never escapes tmp_path into the real project tree
    from pathlib import Path
    real_parents = Path.parents.fget
    monkeypatch.setattr(
        Path, "parents",
        property(lambda self: [p for p in real_parents(self) if str(p).startswith(str(tmp_path))]),
    )
    result = _find_project_root(py_file)
    assert result is None


# --- run_tools ---

def test_run_tools_returns_results():
    """Test that run_tools returns the expected results."""
    cfg = _fake_config()
    fake_raw = RawResult(tool_name="fake", stdout="hi")
    with patch("py_cq.execution_engine.run_tool", return_value=fake_raw):
        results = run_tools([cfg], ".")
    assert len(results) == 1
    assert results[0].metrics["score"] == 1.0


def test_run_tools_sorted_by_order():
    """Test that tools are executed in the order specified by their config."""
    cfg_low = _fake_config("low", order=10)
    cfg_high = _fake_config("high", order=1)
    fake_raw_low = RawResult(tool_name="low", stdout="")
    fake_raw_high = RawResult(tool_name="high", stdout="")

    def fake_run_tool(config, path, excludes=None, *, precomputed_hash=None):
        """Mock implementation of run_tool."""
        return fake_raw_low if config.name == "low" else fake_raw_high

    with patch("py_cq.execution_engine.run_tool", side_effect=fake_run_tool):
        results = run_tools([cfg_low, cfg_high], ".")
    assert results[0].raw.tool_name == "high"
    assert results[1].raw.tool_name == "low"


def test_run_tools_exception_is_logged():
    """Test that exceptions during tool execution are logged."""
    cfg = _fake_config()
    with patch("py_cq.execution_engine.run_tool", side_effect=RuntimeError("boom")):
        with patch("py_cq.execution_engine.log") as mock_log:
            results = run_tools([cfg], ".")
    assert results == []
    mock_log.error.assert_called_once()


def test_run_tools_empty():
    """Test that run_tools returns an empty list when no tools are provided."""
    results = run_tools([], ".")
    assert results == []


# --- run_tools early_exit ---

def _fake_config_with_score(name, order, score, error_threshold=0.5):
    """Create a fake ToolConfig with a custom parser that returns a specific score."""
    class FakeParser:
        """A fake parser for testing purposes."""
        def __init__(self, parser_config=None, _score=score):
            """Initialize the fake parser."""
            self._score = _score
        def parse(self, raw):
            """Parse the raw output."""
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
    def fake_run_tool(config, path, excludes=None, *, precomputed_hash=None):
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
    def fake_run_tool(config, path, excludes=None, *, precomputed_hash=None):
        called.append(config.name)
        return RawResult(tool_name=config.name, stdout="")

    with patch("py_cq.execution_engine.run_tool", side_effect=fake_run_tool):
        results = run_tools([cfg1, cfg2], ".", early_exit=True)

    assert called == ["first", "second"]
    assert len(results) == 2


def test_run_tools_early_exit_exception_breaks_loop():
    """An exception from _run_and_parse during early_exit stops the loop."""
    cfg1 = _fake_config_with_score("first", order=1, score=1.0)
    cfg2 = _fake_config_with_score("second", order=2, score=1.0)

    call_count = [0]
    def fake_run_tool(config, path, excludes=None, *, precomputed_hash=None):
        call_count[0] += 1
        if call_count[0] == 2:
            raise RuntimeError("parser exploded")
        return RawResult(tool_name=config.name, stdout="")

    with patch("py_cq.execution_engine.run_tool", side_effect=fake_run_tool):
        with patch("py_cq.execution_engine.log"):
            results = run_tools([cfg1, cfg2], ".", early_exit=True)

    assert len(results) == 1
    assert results[0].raw.tool_name == "first"


def test_run_tools_early_exit_false_runs_all_despite_error():
    """Without early_exit, all tools run even when one errors."""
    cfg1 = _fake_config_with_score("first", order=1, score=0.0)   # error
    cfg2 = _fake_config_with_score("second", order=2, score=1.0)  # ok

    called = []
    def fake_run_tool(config, path, excludes=None, *, precomputed_hash=None):
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
    mock_cache.get = MagicMock(return_value=None)
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
    mock_cache.get = MagicMock(return_value=None)
    with patch("py_cq.execution_engine._cache", mock_cache), \
         patch("py_cq.execution_engine.shutil.which", return_value=None), \
         patch("py_cq.execution_engine.subprocess.run", return_value=mock_result) as mock_sub:
        run_tool(cfg, str(tmp_path))
    # uv not found → python stays as sys.executable
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
    mock_cache.get = MagicMock(return_value=None)
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
    mock_cache.get = MagicMock(return_value=None)
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
    mock_cache.get = MagicMock(return_value=None)
    fake_uv = "/usr/bin/uv"
    with patch("py_cq.execution_engine._cache", mock_cache), \
         patch("py_cq.execution_engine.shutil.which", return_value=fake_uv), \
         patch("py_cq.execution_engine.subprocess.run", return_value=mock_result) as mock_sub:
        run_tool(cfg, str(tmp_path))
    called_cmd = mock_sub.call_args[0][0]
    assert "--with pytest" in called_cmd
    assert "--with coverage" in called_cmd


# --- parallel execution ---

def test_run_tools_parallel_returns_all_results_sorted():
    """Parallel execution returns all results sorted by .order."""
    configs = [_fake_config(f"t{i}", order=i) for i in range(4, 0, -1)]  # order 4,3,2,1

    def fake_run_tool(config, path, excludes=None, *, precomputed_hash=None):
        return RawResult(tool_name=config.name, stdout="")

    with patch("py_cq.execution_engine.run_tool", side_effect=fake_run_tool):
        results = run_tools(configs, ".", max_workers=4)

    assert len(results) == 4
    orders = [r.raw.tool_name for r in results]
    assert orders == ["t1", "t2", "t3", "t4"]


# --- _dep_in_venv Windows/Unix path ---


def test_dep_in_venv_scripts_dir(tmp_path):
    """On Windows, Scripts/ subdir is checked."""
    venv = tmp_path / ".venv"
    scripts = venv / "Scripts"
    scripts.mkdir(parents=True)
    (scripts / "ruff.exe").write_text("")
    assert _dep_in_venv("ruff", tmp_path)


def test_dep_in_venv_bin_dir(tmp_path):
    """On Unix, bin/ subdir is checked."""
    venv = tmp_path / ".venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "ruff").write_text("")
    assert _dep_in_venv("ruff", tmp_path)


def test_dep_in_venv_not_present(tmp_path):
    """Returns False when venv does not exist."""
    assert not _dep_in_venv("ruff", tmp_path)


def test_dep_in_venv_venv_exists_but_dep_absent(tmp_path):
    """Returns False when .venv exists but the executable is not inside it."""
    venv = tmp_path / ".venv" / "Scripts"
    venv.mkdir(parents=True)
    assert not _dep_in_venv("notreal", tmp_path)


# --- _build_exclude_str ---

def test_build_exclude_str_single_entry():
    result = _build_exclude_str(" --exclude {path}", ["src/bad.py"])
    assert "--exclude src/bad.py" in result


def test_build_exclude_str_multiple_entries():
    result = _build_exclude_str(" --exclude {path}", ["a.py", "b.py"])
    assert "--exclude a.py" in result
    assert "--exclude b.py" in result


def test_build_exclude_str_empty_excludes():
    assert _build_exclude_str(" --exclude {path}", []) == ""


def test_build_exclude_str_no_format():
    assert _build_exclude_str("", ["a.py"]) == ""


def test_run_tool_exclude_appears_in_command(tmp_path):
    """Excludes passed to run_tool are injected into the subprocess command string."""
    from py_cq.execution_engine import run_tool
    cfg = ToolConfig(
        name="check", command="mytool {context_path} {exclude}",
        parser_class=MagicMock, order=1,
        warning_threshold=0.7, error_threshold=0.5,
        exclude_format=" --ignore {path}",
    )
    mock_result = MagicMock(stdout="", stderr="", returncode=0)
    mock_cache = MagicMock()
    mock_cache.get = MagicMock(return_value=None)
    with patch("py_cq.execution_engine._cache", mock_cache), \
         patch("py_cq.execution_engine.subprocess.run", return_value=mock_result) as mock_sub:
        run_tool(cfg, str(tmp_path), excludes=["demo"])
    called_cmd = mock_sub.call_args[0][0]
    assert "--ignore demo" in called_cmd


# --- run_tool real subprocess invocation ---

def test_run_tool_captures_stdout(tmp_path):
    """run_tool actually invokes subprocess and captures stdout."""
    from diskcache import Cache, JSONDisk
    from py_cq.execution_engine import run_tool
    cfg = ToolConfig(
        name="fake", command="{python} -c \"print('hello')\"",
        parser_class=MagicMock, order=1,
        warning_threshold=0.7, error_threshold=0.5,
    )
    test_cache = Cache(str(tmp_path / "cache"), disk=JSONDisk)
    with patch("py_cq.execution_engine._cache", test_cache):
        result = run_tool(cfg, str(tmp_path))
    assert result.stdout.strip() == "hello"
    assert result.return_code == 0
    assert result.tool_name == "fake"
    assert result.timestamp != ""


def test_run_tool_captures_nonzero_exit(tmp_path):
    """run_tool records non-zero exit codes."""
    from diskcache import Cache, JSONDisk
    from py_cq.execution_engine import run_tool
    cfg = ToolConfig(
        name="fake", command="{python} -c \"import sys; sys.exit(42)\"",
        parser_class=MagicMock, order=1,
        warning_threshold=0.7, error_threshold=0.5,
    )
    test_cache = Cache(str(tmp_path / "cache"), disk=JSONDisk)
    with patch("py_cq.execution_engine._cache", test_cache):
        result = run_tool(cfg, str(tmp_path))
    assert result.return_code == 42


def test_run_tool_result_is_cached(tmp_path):
    """Second call with identical inputs returns cached result (same timestamp)."""
    from diskcache import Cache, JSONDisk
    from py_cq.execution_engine import run_tool
    cfg = ToolConfig(
        name="fake", command="echo hi",
        parser_class=MagicMock, order=1,
        warning_threshold=0.7, error_threshold=0.5,
    )
    test_cache = Cache(str(tmp_path / "cache"), disk=JSONDisk)
    with patch("py_cq.execution_engine._cache", test_cache):
        r1 = run_tool(cfg, str(tmp_path))
        r2 = run_tool(cfg, str(tmp_path))
    assert r1.timestamp == r2.timestamp


def test_run_tool_cache_invalidated_on_content_change(tmp_path):
    """Changing file content (size) changes the cache key and forces a new subprocess call."""
    import subprocess as real_subprocess
    from diskcache import Cache, JSONDisk
    from py_cq.execution_engine import run_tool
    py_file = tmp_path / "module.py"
    py_file.write_text("x = 1")
    cfg = ToolConfig(
        name="fake", command="echo check",
        parser_class=MagicMock, order=1,
        warning_threshold=0.7, error_threshold=0.5,
    )
    test_cache = Cache(str(tmp_path / "cache"), disk=JSONDisk)
    with patch("py_cq.execution_engine._cache", test_cache), \
         patch("py_cq.execution_engine.subprocess.run", wraps=real_subprocess.run) as mock_sub:
        run_tool(cfg, str(py_file))
        # Write different-length content so size changes → new hash → cache miss
        py_file.write_text("x = 2\ny = 3\n")
        run_tool(cfg, str(py_file))
    # Two subprocess calls prove both were cache misses
    assert mock_sub.call_count == 2
