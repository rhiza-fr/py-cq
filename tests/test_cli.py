"""Tests for cli check command."""

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from py_cq.cli import app
from py_cq.localtypes import RawResult, ToolResult, CombinedToolResults

runner = CliRunner()


def _fake_tr(score=0.9):
    return ToolResult(metrics={"score": score}, raw=RawResult(tool_name="ruff"))


def _fake_combined(path=".", score=0.9):
    tr = _fake_tr(score)
    return CombinedToolResults(path=path, tool_results=[tr])


@pytest.fixture
def project_dir(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    return tmp_path


# --- --version flag ---

def test_version_flag_exits_zero():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "python-code-quality" in result.output


def test_version_flag_lists_deps():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "ruff" in result.output


# --- check: validation ---

def test_check_nonexistent_path():
    result = runner.invoke(app, ["check", "/nonexistent/path/does/not/exist/xyz"])
    assert result.exit_code != 0


def test_check_non_py_file(tmp_path):
    f = tmp_path / "data.txt"
    f.write_text("hello")
    result = runner.invoke(app, ["check", str(f)])
    assert result.exit_code != 0


def test_check_dir_without_pyproject(tmp_path):
    result = runner.invoke(app, ["check", str(tmp_path)])
    assert result.exit_code != 0


# --- check: output modes ---

def _mock_check(project_dir, *extra_args):
    tr = _fake_tr()
    combined = _fake_combined(str(project_dir))
    with patch("py_cq.api.run_tools", return_value=[tr]), \
         patch("py_cq.cli.aggregate_metrics", return_value=combined):
        return runner.invoke(app, ["check", str(project_dir)] + list(extra_args))


def test_check_score_output(project_dir):
    result = _mock_check(project_dir, "-o", "score")
    assert result.exit_code == 0
    assert "0.9" in result.output


def test_check_json_output(project_dir):
    import json
    result = _mock_check(project_dir, "-o", "json")
    assert result.exit_code == 0
    data = json.loads(result.output.strip())
    assert isinstance(data, list)


def test_check_raw_output(project_dir):
    result = _mock_check(project_dir, "-o", "raw")
    assert result.exit_code == 0
    assert '"tool_name"' in result.output
    assert '"stdout"' in result.output


def test_check_table_output(project_dir):
    result = _mock_check(project_dir)
    assert result.exit_code == 0
    assert "ruff" in result.output
    assert "0.9" in result.output


def test_check_llm_output(project_dir):
    tr = _fake_tr(score=1.0)
    combined = _fake_combined(str(project_dir), score=1.0)
    with patch("py_cq.api.run_tools", return_value=[tr]), \
         patch("py_cq.cli.aggregate_metrics", return_value=combined):
        result = runner.invoke(app, ["check", str(project_dir), "-o", "llm"])
    assert result.exit_code == 0
    assert "No issues found" in result.output


def test_check_clear_cache(project_dir):
    tr = _fake_tr()
    combined = _fake_combined(str(project_dir))
    with patch("py_cq.api.run_tools", return_value=[tr]), \
         patch("py_cq.cli.aggregate_metrics", return_value=combined), \
         patch("py_cq.api._cache") as mock_cache:
        result = runner.invoke(app, ["check", str(project_dir), "--clear-cache"])
    assert result.exit_code == 0
    mock_cache.clear.assert_called_once()


def test_check_py_file(tmp_path):
    py_file = tmp_path / "foo.py"
    py_file.write_text("x = 1")
    tr = _fake_tr()
    combined = _fake_combined(str(py_file))
    with patch("py_cq.api.run_tools", return_value=[tr]), \
         patch("py_cq.cli.aggregate_metrics", return_value=combined):
        result = runner.invoke(app, ["check", str(py_file), "-o", "score"])
    assert result.exit_code == 0


# --- check: language detection and --language flag ---

def test_check_typescript_project_prints_message(tmp_path):
    """A TypeScript project prints a clear message and exits 0."""
    (tmp_path / "package.json").write_text("{}")
    result = runner.invoke(app, ["check", str(tmp_path)])
    assert result.exit_code == 0
    assert "typescript" in result.output.lower()
    assert "not yet available" in result.output.lower()


def test_check_rust_project_prints_message(tmp_path):
    (tmp_path / "Cargo.toml").write_text("")
    result = runner.invoke(app, ["check", str(tmp_path)])
    assert result.exit_code == 0
    assert "rust" in result.output.lower()
    assert "not yet available" in result.output.lower()


def test_check_language_flag_overrides_detection(tmp_path):
    """--language typescript on an empty dir prints the message (no auto-detect needed)."""
    result = runner.invoke(app, ["check", str(tmp_path), "--language", "typescript"])
    assert result.exit_code == 0
    assert "typescript" in result.output.lower()
    assert "not yet available" in result.output.lower()


def test_check_language_flag_python_runs_normally(project_dir):
    """--language python still runs the Python fast path."""
    tr = _fake_tr()
    combined = _fake_combined(str(project_dir))
    with patch("py_cq.api.run_tools", return_value=[tr]), \
         patch("py_cq.cli.aggregate_metrics", return_value=combined):
        result = runner.invoke(app, ["check", str(project_dir), "--language", "python", "-o", "score"])
    assert result.exit_code == 0
    assert "0.9" in result.output


def test_check_unknown_dir_still_errors(tmp_path):
    """A directory with no recognised markers still produces an error."""
    result = runner.invoke(app, ["check", str(tmp_path)])
    assert result.exit_code != 0


# --- check: --only and --skip ---

def test_check_only_filters_tools(project_dir):
    tr = _fake_tr()
    combined = _fake_combined(str(project_dir))
    with patch("py_cq.api.run_tools", return_value=[tr]) as mock_run, \
         patch("py_cq.cli.aggregate_metrics", return_value=combined):
        runner.invoke(app, ["check", str(project_dir), "--only", "ruff,ty"])
    passed = list(mock_run.call_args[0][0])
    assert all(tc.name in {"ruff", "ty"} for tc in passed)


def test_check_skip_excludes_tools(project_dir):
    tr = _fake_tr()
    combined = _fake_combined(str(project_dir))
    with patch("py_cq.api.run_tools", return_value=[tr]) as mock_run, \
         patch("py_cq.cli.aggregate_metrics", return_value=combined):
        runner.invoke(app, ["check", str(project_dir), "--skip", "bandit,vulture"])
    passed = list(mock_run.call_args[0][0])
    assert all(tc.name not in {"bandit", "vulture"} for tc in passed)


def test_check_only_and_skip_combined(project_dir):
    """--only then --skip: only runs tools in both sets (only ∩ ¬skip)."""
    tr = _fake_tr()
    combined = _fake_combined(str(project_dir))
    with patch("py_cq.api.run_tools", return_value=[tr]) as mock_run, \
         patch("py_cq.cli.aggregate_metrics", return_value=combined):
        runner.invoke(app, ["check", str(project_dir), "--only", "ruff,ty,bandit", "--skip", "ty"])
    passed = list(mock_run.call_args[0][0])
    names = {tc.name for tc in passed}
    assert "ty" not in names
    assert names <= {"ruff", "bandit"}


def test_check_only_unknown_tool_errors(project_dir):
    result = runner.invoke(app, ["check", str(project_dir), "--only", "nonexistent"])
    assert result.exit_code != 0
    assert "nonexistent" in result.output
    assert "Available" in result.output


def test_check_exclude_merge(project_dir):
    """TOML exclude + CLI --exclude are merged and both passed to run_tools."""
    (project_dir / "pyproject.toml").write_text('[tool.cq]\nexclude = ["demo"]\n')
    tr = _fake_tr()
    combined = _fake_combined(str(project_dir))
    with patch("py_cq.api.run_tools", return_value=[tr]) as mock_run, \
         patch("py_cq.cli.aggregate_metrics", return_value=combined):
        runner.invoke(app, ["check", str(project_dir), "--exclude", "tests", "-o", "score"])
    excludes = mock_run.call_args.kwargs["excludes"]
    assert "demo" in excludes
    assert "tests" in excludes


def test_check_py_file_passes_full_registry(tmp_path):
    """When invoked on a .py file, run_tools receives the full (unfiltered) registry."""
    py_file = tmp_path / "foo.py"
    py_file.write_text("x = 1")
    tr = _fake_tr()
    combined = _fake_combined(str(py_file))
    with patch("py_cq.api.run_tools", return_value=[tr]) as mock_run, \
         patch("py_cq.cli.aggregate_metrics", return_value=combined):
        runner.invoke(app, ["check", str(py_file), "-o", "score"])
    passed_tools = list(mock_run.call_args[0][0])
    # All tools from the registry are passed — CLAUDE.md says pytest/coverage are skipped,
    # but the source has no such filter; this test documents the actual behaviour.
    from py_cq.tool_registry import tool_registry
    assert len(passed_tools) == len(tool_registry)


def test_main_entry_point():
    from py_cq.main import main
    with patch("py_cq.main.app") as mock_app:
        main()
        mock_app.assert_called_once()


def test_log_level_valid_debug(project_dir):
    """--log-level DEBUG is accepted and exits 0."""
    result = _mock_check(project_dir, "--log-level", "DEBUG")
    assert result.exit_code == 0


def test_log_level_valid_warning(project_dir):
    """--log-level WARNING is accepted and exits 0."""
    result = _mock_check(project_dir, "--log-level", "WARNING")
    assert result.exit_code == 0


def test_log_level_invalid_exits_nonzero(project_dir):
    """An unrecognised --log-level value produces a non-zero exit."""
    result = runner.invoke(app, ["check", str(project_dir), "--log-level", "NONSENSE"])
    assert result.exit_code != 0


def test_version_skips_extras_and_unknown_deps():
    """_version_callback handles extras markers and missing packages without crashing."""
    from importlib.metadata import PackageNotFoundError
    fake_reqs = ["requests>=2.0; extra == 'dev'", "nonexistent-pkg>=1.0"]
    with patch("py_cq.cli.requires", return_value=fake_reqs), \
         patch("py_cq.cli.version", side_effect=["1.0.0", PackageNotFoundError("nonexistent-pkg")]):
        result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "nonexistent-pkg" not in result.output
