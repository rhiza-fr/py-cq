"""Tests for load_user_config and _apply_user_config."""



from py_cq.cli import _apply_user_config
from py_cq.config import load_user_config
from py_cq.localtypes import ToolConfig


def _cfg(name: str, order: int = 1) -> ToolConfig:
    """Create a default ToolConfig."""
    return ToolConfig(
        name=name, command="", parser_class=object,
        order=order, warning_threshold=0.7, error_threshold=0.5,
    )


def _base() -> dict[str, ToolConfig]:
    """Return the base configuration."""
    return {"ruff": _cfg("ruff", 3), "coverage": _cfg("coverage", 6)}


# --- load_user_config ---

def test_load_no_pyproject(tmp_path):
    """Test that load_user_config returns an empty dict when no pyproject.toml is present."""
    assert load_user_config(tmp_path) == {}


def test_load_no_cq_section(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    assert load_user_config(tmp_path) == {}


def test_load_disable(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[tool.cq]\ndisable = ["coverage"]\n')
    assert load_user_config(tmp_path) == {"disable": ["coverage"]}


def test_load_thresholds(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.cq.thresholds.ruff]\nwarning = 0.95\nerror = 0.85\n"
    )
    cfg = load_user_config(tmp_path)
    assert cfg["thresholds"]["ruff"]["warning"] == 0.95
    assert cfg["thresholds"]["ruff"]["error"] == 0.85


def test_load_file_path_reads_parent(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[tool.cq]\ndisable = ["ruff"]\n')
    py_file = tmp_path / "foo.py"
    py_file.write_text("")
    assert load_user_config(py_file) == {"disable": ["ruff"]}


# --- _apply_user_config ---

def test_apply_empty():
    result = _apply_user_config(_base(), {})
    assert set(result) == {"ruff", "coverage"}


def test_apply_disable():
    result = _apply_user_config(_base(), {"disable": ["coverage"]})
    assert "coverage" not in result
    assert "ruff" in result


def test_apply_disable_unknown_is_noop():
    result = _apply_user_config(_base(), {"disable": ["nonexistent"]})
    assert set(result) == {"ruff", "coverage"}


def test_apply_thresholds():
    result = _apply_user_config(_base(), {
        "thresholds": {"ruff": {"warning": 0.95, "error": 0.85}}
    })
    assert result["ruff"].warning_threshold == 0.95
    assert result["ruff"].error_threshold == 0.85
    assert result["coverage"].warning_threshold == 0.7  # unchanged


def test_load_tools_key(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.cq.tools.mycheck]\n"
        'parser = "RuffParser"\n'
        'command = "ruff check {context_path}"\n'
        "order = 99\n"
        "warning_threshold = 0.8\n"
        "error_threshold = 0.6\n"
    )
    cfg = load_user_config(tmp_path)
    assert "tools" in cfg
    assert "mycheck" in cfg["tools"]
    assert cfg["tools"]["mycheck"]["parser"] == "RuffParser"
    assert cfg["tools"]["mycheck"]["order"] == 99


def test_load_context_lines(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.cq]\ncontext_lines = 5\n")
    assert load_user_config(tmp_path) == {"context_lines": 5}


def test_load_exclude(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[tool.cq]\nexclude = ["demo", "docs"]\n')
    assert load_user_config(tmp_path) == {"exclude": ["demo", "docs"]}


def test_apply_does_not_mutate_base():
    base = _base()
    _apply_user_config(base, {"disable": ["ruff"], "thresholds": {"coverage": {"warning": 0.99}}})
    assert "ruff" in base
    assert base["coverage"].warning_threshold == 0.7
