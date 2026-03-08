"""Tests for cli module."""

import json
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from py_cq.cli import _apply_user_config, app, format_as_table
from py_cq.localtypes import CombinedToolResults, RawResult, ToolConfig, ToolResult

runner = CliRunner()


def _tc(name="ruff", order=3):
    class FakeParser:
        def parse(self, raw):
            return ToolResult(metrics={"score": 1.0}, raw=raw)
        def format_llm_message(self, tr):
            return "no issues"
    return ToolConfig(name=name, command="", parser_class=FakeParser, order=order,
                      warning_threshold=0.7, error_threshold=0.5)


def _fake_tr(score=0.9):
    return ToolResult(metrics={"score": score}, raw=RawResult(tool_name="ruff"))


def _fake_combined(path=".", score=0.9):
    tr = _fake_tr(score)
    return CombinedToolResults(path=path, tool_results=[tr])


@pytest.fixture
def project_dir(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    return tmp_path


# --- _apply_user_config ---

def test_apply_user_config_empty():
    cfg = {"ruff": _tc()}
    result = _apply_user_config(cfg, {})
    assert "ruff" in result
    assert result["ruff"].warning_threshold == 0.7


def test_apply_user_config_disable():
    cfg = {"ruff": _tc(), "bandit": _tc("bandit", 2)}
    result = _apply_user_config(cfg, {"disable": ["ruff"]})
    assert "ruff" not in result
    assert "bandit" in result


def test_apply_user_config_disable_unknown_tool():
    cfg = {"ruff": _tc()}
    result = _apply_user_config(cfg, {"disable": ["nonexistent"]})
    assert "ruff" in result


def test_apply_user_config_threshold_warning():
    cfg = {"ruff": _tc()}
    result = _apply_user_config(cfg, {"thresholds": {"ruff": {"warning": 0.8}}})
    assert result["ruff"].warning_threshold == 0.8
    assert result["ruff"].error_threshold == 0.5  # unchanged


def test_apply_user_config_threshold_error():
    cfg = {"ruff": _tc()}
    result = _apply_user_config(cfg, {"thresholds": {"ruff": {"error": 0.6}}})
    assert result["ruff"].error_threshold == 0.6
    assert result["ruff"].warning_threshold == 0.7  # unchanged


def test_apply_user_config_threshold_unknown_tool():
    cfg = {"ruff": _tc()}
    result = _apply_user_config(cfg, {"thresholds": {"unknown": {"warning": 0.9}}})
    assert result["ruff"].warning_threshold == 0.7


def test_apply_user_config_does_not_mutate_original():
    tc = _tc()
    cfg = {"ruff": tc}
    _apply_user_config(cfg, {"thresholds": {"ruff": {"warning": 0.99}}})
    assert tc.warning_threshold == 0.7


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
    with patch("py_cq.cli.run_tools", return_value=[tr]), \
         patch("py_cq.cli.aggregate_metrics", return_value=combined):
        return runner.invoke(app, ["check", str(project_dir)] + list(extra_args))


def test_check_score_output(project_dir):
    result = _mock_check(project_dir, "-o", "score")
    assert result.exit_code == 0
    assert "0.9" in result.output


def test_check_json_output(project_dir):
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


def test_check_llm_output(project_dir):
    result = _mock_check(project_dir, "-o", "llm")
    assert result.exit_code == 0


def test_check_clear_cache(project_dir):
    tr = _fake_tr()
    combined = _fake_combined(str(project_dir))
    with patch("py_cq.cli.run_tools", return_value=[tr]), \
         patch("py_cq.cli.aggregate_metrics", return_value=combined), \
         patch("py_cq.cli.tool_cache") as mock_cache:
        result = runner.invoke(app, ["check", str(project_dir), "--clear-cache"])
    assert result.exit_code == 0
    mock_cache.clear.assert_called_once()


def test_check_py_file(tmp_path):
    py_file = tmp_path / "foo.py"
    py_file.write_text("x = 1")
    tr = _fake_tr()
    combined = _fake_combined(str(py_file))
    with patch("py_cq.cli.run_tools", return_value=[tr]), \
         patch("py_cq.cli.aggregate_metrics", return_value=combined):
        result = runner.invoke(app, ["check", str(py_file), "-o", "score"])
    assert result.exit_code == 0


# --- config command ---

def test_config_no_pyproject(tmp_path):
    result = runner.invoke(app, ["config", str(tmp_path)])
    assert result.exit_code == 0
    assert "not found" in result.output


def test_config_no_cq_section(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
    result = runner.invoke(app, ["config", str(tmp_path)])
    assert result.exit_code == 0
    assert "no" in result.output and "section" in result.output


def test_config_with_cq_section(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[tool.cq]\ndisable = ["vulture"]\n')
    result = runner.invoke(app, ["config", str(tmp_path)])
    assert result.exit_code == 0
    assert "merged" in result.output


def test_config_py_file_input(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    py_file = tmp_path / "foo.py"
    py_file.write_text("x = 1")
    result = runner.invoke(app, ["config", str(py_file)])
    assert result.exit_code == 0


# --- format_as_table ---

def _registry(name="ruff", warning=0.7, error=0.5):
    return {name: ToolConfig(name=name, command="", parser_class=object, order=3,
                             warning_threshold=warning, error_threshold=error)}


def test_format_as_table_ok_status():
    tr = ToolResult(metrics={"coverage": 0.9}, raw=RawResult(tool_name="ruff"))
    combined = CombinedToolResults(path=".", tool_results=[tr])
    table = format_as_table(combined, _registry())
    from rich.table import Table
    assert isinstance(table, Table)


def test_format_as_table_warning_status():
    tr = ToolResult(metrics={"coverage": 0.65}, raw=RawResult(tool_name="ruff"))
    combined = CombinedToolResults(path=".", tool_results=[tr])
    table = format_as_table(combined, _registry())
    from rich.table import Table
    assert isinstance(table, Table)


def test_format_as_table_error_status():
    tr = ToolResult(metrics={"coverage": 0.3}, raw=RawResult(tool_name="ruff"))
    combined = CombinedToolResults(path=".", tool_results=[tr])
    table = format_as_table(combined, _registry())
    from rich.table import Table
    assert isinstance(table, Table)
