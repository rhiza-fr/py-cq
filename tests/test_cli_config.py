"""Tests for cli config command, _apply_user_config, and format_as_table."""

import pytest
import typer
from typer.testing import CliRunner

from py_cq.cli import _apply_user_config, app
from py_cq.localtypes import CombinedToolResults, RawResult, ToolConfig, ToolResult
from py_cq.table_formatter import format_as_table

runner = CliRunner()


def _tc(name="ruff", order=3):
    class FakeParser:
        def parse(self, raw):
            return ToolResult(metrics={"score": 1.0}, raw=raw)
        def format_llm_message(self, tr):
            return "no issues"
    return ToolConfig(name=name, command="", parser_class=FakeParser, order=order,
                      warning_threshold=0.7, error_threshold=0.5)


def _registry(name="ruff", warning=0.7, error=0.5):
    return {name: ToolConfig(name=name, command="", parser_class=object, order=3,
                             warning_threshold=warning, error_threshold=error)}


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


def test_apply_user_config_missing_required_field_raises():
    user_cfg = {
        "tools": {
            "mycheck": {
                "command": "mycheck {context_path}",
                "parser": "ExitCodeParser",
                # missing order, warning_threshold, error_threshold
            }
        }
    }
    with pytest.raises(typer.BadParameter) as exc_info:
        _apply_user_config({}, user_cfg)
    assert "mycheck" in str(exc_info.value)


def test_apply_user_config_adds_user_tool():
    """User can declare a new tool under [tool.cq.tools]."""
    cfg = {"ruff": _tc()}
    user_cfg = {
        "tools": {
            "mycheck": {
                "command": "mycheck {context_path}",
                "parser": "ExitCodeParser",
                "order": 99,
                "warning_threshold": 0.9,
                "error_threshold": 0.5,
            }
        }
    }
    result = _apply_user_config(cfg, user_cfg)
    assert "mycheck" in result
    assert result["mycheck"].order == 99
    assert result["mycheck"].warning_threshold == 0.9
    assert result["mycheck"].command == "mycheck {context_path}"


def test_apply_user_config_user_tool_parser_config():
    """parser_config is threaded through to the ToolConfig."""
    cfg = {}
    user_cfg = {
        "tools": {
            "mychecker": {
                "command": "cmd {context_path}",
                "parser": "LineCountParser",
                "order": 5,
                "warning_threshold": 0.8,
                "error_threshold": 0.5,
                "parser_config": {"scale_factor": 20},
            }
        }
    }
    result = _apply_user_config(cfg, user_cfg)
    assert result["mychecker"].parser_config == {"scale_factor": 20}


def test_apply_user_config_user_tool_overrides_builtin():
    """A user tool entry with the same key replaces the built-in."""
    cfg = {"ruff": _tc("ruff", order=2)}
    user_cfg = {
        "tools": {
            "ruff": {
                "command": "custom-ruff {context_path}",
                "parser": "ExitCodeParser",
                "order": 2,
                "warning_threshold": 0.5,
                "error_threshold": 0.3,
            }
        }
    }
    result = _apply_user_config(cfg, user_cfg)
    assert result["ruff"].command == "custom-ruff {context_path}"


# --- config command ---

def test_config_no_pyproject(tmp_path):
    result = runner.invoke(app, ["config", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert "not found" in result.output


def test_config_no_cq_section(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
    result = runner.invoke(app, ["config", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert "no" in result.output and "section" in result.output


def test_config_with_cq_section(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[tool.cq]\ndisable = ["vulture"]\n')
    result = runner.invoke(app, ["config", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert "merged" in result.output


def test_config_defaults_to_cwd(tmp_path):
    """config with no args uses cwd (which likely has no pyproject -> 'not found')."""
    result = runner.invoke(app, ["config"])
    assert result.exit_code == 0


def test_config_shows_user_defined_tool(tmp_path):
    toml = (
        "[tool.cq.tools.mycheck]\n"
        'command = "mycheck {context_path}"\n'
        'parser = "ExitCodeParser"\n'
        "order = 99\n"
        "warning_threshold = 0.9\n"
        "error_threshold = 0.5\n"
    )
    (tmp_path / "pyproject.toml").write_text(toml)
    result = runner.invoke(app, ["config", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert "mycheck" in result.output


# --- config set ---

def test_config_set_needs_warning_or_error(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.cq]\n")
    result = runner.invoke(app, ["config", "set", "ruff", "--path", str(tmp_path)])
    assert result.exit_code != 0
    assert "warning" in result.output.lower() or "error" in result.output.lower()


def test_config_set_unknown_tool(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.cq]\n")
    result = runner.invoke(app, [
        "config", "set", "nonexistent", "--warning", "0.8", "--path", str(tmp_path),
    ])
    assert result.exit_code != 0
    assert "Unknown tool" in result.output


def test_config_set_no_pyproject(tmp_path):
    result = runner.invoke(app, [
        "config", "set", "ruff", "--warning", "0.8", "--path", str(tmp_path),
    ])
    assert result.exit_code != 0
    assert "pyproject.toml" in result.output


def test_config_set_writes_warning(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.cq]\n")
    result = runner.invoke(app, [
        "config", "set", "ruff", "--warning", "0.8", "--path", str(tmp_path),
    ])
    assert result.exit_code == 0
    assert "ruff" in result.output
    assert "warning=0.8" in result.output
    # Verify the file was written correctly
    import tomllib
    with (tmp_path / "pyproject.toml").open("rb") as f:
        data = tomllib.load(f)
    assert data["tool"]["cq"]["thresholds"]["ruff"]["warning"] == 0.8


def test_config_set_writes_error(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.cq]\n")
    result = runner.invoke(app, [
        "config", "set", "ruff", "--error", "0.4", "--path", str(tmp_path),
    ])
    assert result.exit_code == 0
    import tomllib
    with (tmp_path / "pyproject.toml").open("rb") as f:
        data = tomllib.load(f)
    assert data["tool"]["cq"]["thresholds"]["ruff"]["error"] == 0.4


def test_config_set_writes_both(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.cq]\n")
    result = runner.invoke(app, [
        "config", "set", "ruff", "--warning", "0.8", "--error", "0.4",
        "--path", str(tmp_path),
    ])
    assert result.exit_code == 0
    import tomllib
    with (tmp_path / "pyproject.toml").open("rb") as f:
        data = tomllib.load(f)
    assert data["tool"]["cq"]["thresholds"]["ruff"]["warning"] == 0.8
    assert data["tool"]["cq"]["thresholds"]["ruff"]["error"] == 0.4


def test_config_set_updates_existing(tmp_path):
    existing = (
        '[tool.cq]\n'
        '[tool.cq.thresholds]\n'
        '"radon-hal" = { warning = 0.5, error = 0.3 }\n'
    )
    (tmp_path / "pyproject.toml").write_text(existing)
    result = runner.invoke(app, [
        "config", "set", "radon-hal", "--warning", "0.45", "--path", str(tmp_path),
    ])
    assert result.exit_code == 0
    import tomllib
    with (tmp_path / "pyproject.toml").open("rb") as f:
        data = tomllib.load(f)
    thresholds = data["tool"]["cq"]["thresholds"]["radon-hal"]
    assert thresholds["warning"] == 0.45
    assert thresholds["error"] == 0.3  # unchanged


def test_config_set_preserves_other_sections(tmp_path):
    toml_content = (
        "[project]\n"
        'name = "demo"\n'
        "version = \"1.0\"\n"
        "[tool.cq]\n"
        "exclude = [\"demo\"]\n"
    )
    (tmp_path / "pyproject.toml").write_text(toml_content)
    result = runner.invoke(app, [
        "config", "set", "ruff", "--error", "0.5", "--path", str(tmp_path),
    ])
    assert result.exit_code == 0
    import tomllib
    with (tmp_path / "pyproject.toml").open("rb") as f:
        data = tomllib.load(f)
    assert data["project"]["name"] == "demo"  # preserved
    assert data["tool"]["cq"]["exclude"] == ["demo"]  # preserved
    assert data["tool"]["cq"]["thresholds"]["ruff"]["error"] == 0.5


def test_config_set_creates_cq_section_if_missing(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = \"x\"\n")
    result = runner.invoke(app, [
        "config", "set", "ruff", "--error", "0.5", "--path", str(tmp_path),
    ])
    assert result.exit_code == 0
    import tomllib
    with (tmp_path / "pyproject.toml").open("rb") as f:
        data = tomllib.load(f)
    assert data["tool"]["cq"]["thresholds"]["ruff"]["error"] == 0.5


# --- format_as_table ---

def _render(table) -> str:
    from io import StringIO
    from rich.console import Console
    buf = StringIO()
    Console(file=buf, no_color=True, width=120).print(table)
    return buf.getvalue()


def test_format_as_table_ok_status():
    tr = ToolResult(metrics={"coverage": 0.9}, raw=RawResult(tool_name="ruff"))
    combined = CombinedToolResults(path=".", tool_results=[tr])
    text = _render(format_as_table(combined, _registry()))
    assert "ruff" in text
    assert "0.900" in text
    assert "OK" in text


def test_format_as_table_warning_status():
    tr = ToolResult(metrics={"coverage": 0.65}, raw=RawResult(tool_name="ruff"))
    combined = CombinedToolResults(path=".", tool_results=[tr])
    text = _render(format_as_table(combined, _registry()))
    assert "ruff" in text
    assert "0.650" in text
    assert "Warning" in text


def test_format_as_table_error_status():
    tr = ToolResult(metrics={"coverage": 0.3}, raw=RawResult(tool_name="ruff"))
    combined = CombinedToolResults(path=".", tool_results=[tr])
    text = _render(format_as_table(combined, _registry()))
    assert "ruff" in text
    assert "0.300" in text
    assert "Error" in text


def test_apply_user_config_invalid_parser_raises_module_not_found():
    """Documenting current behavior: an unknown parser name raises ModuleNotFoundError.

    The KeyError branch in _apply_user_config only catches missing required fields.
    A bad parser *name* triggers import_module which raises ModuleNotFoundError uncaught.
    """
    user_cfg = {
        "tools": {
            "mycheck": {
                "parser": "NonExistentParser123",
                "command": "echo {context_path}",
                "order": 99,
                "warning_threshold": 0.8,
                "error_threshold": 0.6,
            }
        }
    }
    with pytest.raises(ModuleNotFoundError):
        _apply_user_config({"ruff": _tc()}, user_cfg)


def test_config_command_end_to_end(tmp_path):
    """config command end-to-end: reads real pyproject.toml, applies user tool, shows in table."""
    toml = (
        "[tool.cq.tools.mycheck]\n"
        'command = "mycheck {context_path}"\n'
        'parser = "ExitCodeParser"\n'
        "order = 99\n"
        "warning_threshold = 0.9\n"
        "error_threshold = 0.5\n"
    )
    (tmp_path / "pyproject.toml").write_text(toml)
    result = runner.invoke(app, ["config", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert "mycheck" in result.output
    assert "99" in result.output   # order column
    assert "enabled" in result.output
