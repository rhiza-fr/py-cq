"""Integration tests: CLI output formats verified end-to-end.

Uses a minimal temp project with all built-in tools disabled and one
ExitCodeParser tool so tests are fast and deterministic.
"""

import json
import re

import pytest
from typer.testing import CliRunner

from py_cq.cli import app

runner = CliRunner()

_DISABLE_ALL = [
    "compile", "ruff", "ty", "bandit", "pytest", "coverage",
    "radon-cc", "radon-mi", "radon-hal", "vulture", "interrogate",
]


def _project(tmp_path, command, warning=0.9999, error=0.9999):
    """Write a pyproject.toml with all built-in tools disabled and one ExitCodeParser tool."""
    disable = ", ".join(f'"{t}"' for t in _DISABLE_ALL)
    lines = [
        "[tool.cq]",
        f"disable = [{disable}]",
        "",
        "[tool.cq.tools.mycheck]",
        f'command = "{command}"',
        'parser = "ExitCodeParser"',
        "order = 1",
        f"warning_threshold = {warning}",
        f"error_threshold = {error}",
    ]
    (tmp_path / "pyproject.toml").write_text("\n".join(lines))
    return str(tmp_path)


def test_json_output_is_list(tmp_path):
    path = _project(tmp_path, "echo hello")
    result = runner.invoke(app, ["check", path, "-o", "json", "--workers", "1"])
    assert result.exit_code == 0
    data = json.loads(result.output.strip())
    assert isinstance(data, list)
    assert len(data) > 0


def test_json_output_structure(tmp_path):
    path = _project(tmp_path, "echo hello")
    result = runner.invoke(app, ["check", path, "-o", "json", "--workers", "1"])
    assert result.exit_code == 0
    data = json.loads(result.output.strip())
    entry = data[0]
    assert "tool_name" in entry
    assert "metrics" in entry
    assert "details" in entry


def test_score_output_is_float(tmp_path):
    path = _project(tmp_path, "echo hello")
    result = runner.invoke(app, ["check", path, "-o", "score", "--workers", "1"])
    assert result.exit_code == 0
    score = float(result.output.strip())
    assert 0.0 <= score <= 1.0


def test_llm_output_is_markdown(tmp_path):
    script = tmp_path / "fail.py"
    script.write_text("import sys; sys.exit(1)")
    cmd = f"{{python}} {script.as_posix()}"
    path = _project(tmp_path, cmd, error=0.0)
    result = runner.invoke(app, ["check", path, "-o", "llm", "--workers", "1"])
    assert result.exit_code == 0
    out = result.output.strip()
    assert "Tool exited" in out  # ExitCodeParser message for non-zero exit
    assert "Please fix" in out   # LLM formatter footer


def test_raw_output_has_required_keys(tmp_path):
    path = _project(tmp_path, "echo hello")
    result = runner.invoke(app, ["check", path, "-o", "raw", "--workers", "1"])
    assert result.exit_code == 0
    data = json.loads(result.output.strip())
    assert isinstance(data, list) and len(data) > 0
    entry = data[0]
    assert isinstance(entry["tool_name"], str)
    assert isinstance(entry["stdout"], str)
    assert isinstance(entry["return_code"], int)


def test_exit_code_1_on_error(tmp_path):
    script = tmp_path / "fail.py"
    script.write_text("import sys; sys.exit(1)")
    cmd = f"{{python}} {script.as_posix()}"
    path = _project(tmp_path, cmd, error=1.0)
    result = runner.invoke(app, ["check", path, "-o", "score", "--workers", "1"])
    assert result.exit_code == 1


def test_exit_code_0_on_pass(tmp_path):
    path = _project(tmp_path, "echo hello")
    result = runner.invoke(app, ["check", path, "-o", "score", "--workers", "1"])
    assert result.exit_code == 0


def test_score_output_is_consistent_with_json(tmp_path):
    path = _project(tmp_path, "echo hello")
    r_score = runner.invoke(app, ["check", path, "-o", "score", "--workers", "1"])
    r_json = runner.invoke(app, ["check", path, "-o", "json", "--workers", "1"])
    assert r_score.exit_code == 0
    assert r_json.exit_code == 0
    score_val = float(r_score.output.strip())
    data = json.loads(r_json.output.strip())
    # Single-tool project: score equals the one tool's single metric value
    assert len(data) == 1
    tool_metrics = data[0]["metrics"]
    assert len(tool_metrics) == 1
    expected = next(iter(tool_metrics.values()))
    assert score_val == pytest.approx(expected)


def test_only_flag_limits_tools(tmp_path):
    path = _project(tmp_path, "echo hello")
    result = runner.invoke(app, ["check", path, "--only", "mycheck", "-o", "json", "--workers", "1"])
    assert result.exit_code == 0
    data = json.loads(result.output.strip())
    assert all(entry["tool_name"] == "mycheck" for entry in data)


def test_skip_flag_removes_tool(tmp_path):
    path = _project(tmp_path, "echo hello")
    result = runner.invoke(app, ["check", path, "--skip", "mycheck", "-o", "json", "--workers", "1"])
    assert result.exit_code == 0
    data = json.loads(result.output.strip())
    assert all(entry["tool_name"] != "mycheck" for entry in data)


def test_clear_cache_then_runs(tmp_path):
    path = _project(tmp_path, "echo hello")
    r1 = runner.invoke(app, ["check", path, "-o", "score", "--workers", "1"])
    r2 = runner.invoke(app, ["check", path, "--clear-cache", "-o", "score", "--workers", "1"])
    assert r1.exit_code == 0
    assert r2.exit_code == 0
    assert float(r1.output.strip()) == pytest.approx(float(r2.output.strip()))


def test_table_output_renders(tmp_path):
    path = _project(tmp_path, "echo hello")
    result = runner.invoke(app, ["check", path, "-o", "table", "--workers", "1"])
    assert result.exit_code == 0
    assert "mycheck" in result.output
    assert "1.000" in result.output  # score column
    assert "OK" in result.output      # status column


def test_exclude_flag_runs_cleanly(tmp_path):
    path = _project(tmp_path, "echo hello")
    result = runner.invoke(app, ["check", path, "--exclude", "demo", "-o", "score", "--workers", "1"])
    assert result.exit_code == 0
    score = float(result.output.strip())
    assert 0.0 <= score <= 1.0


def _two_tool_project(tmp_path, cmd1, cmd2):
    """Write a pyproject.toml with two ExitCodeParser tools and all built-ins disabled."""
    disable = ", ".join(f'"{t}"' for t in _DISABLE_ALL)
    lines = [
        "[tool.cq]",
        f"disable = [{disable}]",
        "",
        "[tool.cq.tools.tool_pass]",
        f'command = "{cmd1}"',
        'parser = "ExitCodeParser"',
        "order = 1",
        "warning_threshold = 0.5",
        "error_threshold = 0.0",
        "",
        "[tool.cq.tools.tool_fail]",
        f'command = "{cmd2}"',
        'parser = "ExitCodeParser"',
        "order = 2",
        "warning_threshold = 0.5",
        "error_threshold = 0.0",
    ]
    (tmp_path / "pyproject.toml").write_text("\n".join(lines))
    return str(tmp_path)


def test_multi_tool_mixed_pass_fail_score(tmp_path):
    """Two tools: one exits 0 (score 1.0), one exits 1 (score 0.0) → combined score 0.5."""
    script = tmp_path / "fail.py"
    script.write_text("import sys; sys.exit(1)")
    fail_cmd = f"{{python}} {script.as_posix()}"
    path = _two_tool_project(tmp_path, "echo hello", fail_cmd)
    result = runner.invoke(app, ["check", path, "-o", "score", "--workers", "1"])
    assert result.exit_code == 0  # error_threshold=0.0 so no error exit
    score = float(result.output.strip())
    assert score == pytest.approx(0.5)


def test_parallel_execution_score_stable(tmp_path):
    """Running with --workers 4 gives same score as sequential."""
    path = _project(tmp_path, "echo hello")
    r_seq = runner.invoke(app, ["check", path, "-o", "score", "--workers", "1"])
    r_par = runner.invoke(app, ["check", path, "-o", "score", "--workers", "4"])
    assert r_seq.exit_code == 0
    assert r_par.exit_code == 0
    assert float(r_seq.output.strip()) == pytest.approx(float(r_par.output.strip()))


def test_cache_round_trip_identical_output(tmp_path):
    """Second run without --clear-cache returns identical score (diskcache semantics)."""
    path = _project(tmp_path, "echo hello")
    r1 = runner.invoke(app, ["check", path, "-o", "score", "--workers", "1"])
    r2 = runner.invoke(app, ["check", path, "-o", "score", "--workers", "1"])
    assert r1.exit_code == 0
    assert r2.exit_code == 0
    assert r1.output.strip() == r2.output.strip()


def test_language_flag_non_python_exits_cleanly(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    result = runner.invoke(app, ["check", str(tmp_path), "--language", "go"])
    assert result.exit_code == 0
    assert "not yet available" in result.output.lower()


def test_llm_output_passing_case(tmp_path):
    path = _project(tmp_path, "echo hello")
    result = runner.invoke(app, ["check", path, "-o", "llm", "--workers", "1"])
    assert result.exit_code == 0
    assert "# No issues found" in result.output
    assert "Overall score:" in result.output
    assert re.search(r"\*\*1\.000 / 1\.0\*\*", result.output)


def test_json_output_includes_duration(tmp_path):
    path = _project(tmp_path, "echo hello")
    result = runner.invoke(app, ["check", path, "-o", "json", "--workers", "1"])
    assert result.exit_code == 0
    data = json.loads(result.output.strip())
    assert "duration_s" in data[0]
    assert isinstance(data[0]["duration_s"], (int, float))


def test_raw_output_includes_all_fields(tmp_path):
    path = _project(tmp_path, "echo hello")
    result = runner.invoke(app, ["check", path, "-o", "raw", "--workers", "1"])
    assert result.exit_code == 0
    data = json.loads(result.output.strip())
    entry = data[0]
    for field in ("tool_name", "command", "stdout", "stderr", "return_code", "timestamp"):
        assert field in entry, f"missing field: {field}"


def test_score_output_contains_only_float(tmp_path):
    path = _project(tmp_path, "echo hello")
    result = runner.invoke(app, ["check", path, "-o", "score", "--workers", "1"])
    assert result.exit_code == 0
    assert re.fullmatch(r"[0-9]+\.[0-9]+", result.output.strip())


def test_json_output_starts_with_bracket(tmp_path):
    path = _project(tmp_path, "echo hello")
    result = runner.invoke(app, ["check", path, "-o", "json", "--workers", "1"])
    assert result.exit_code == 0
    assert result.output.lstrip()[0] == "["


def test_user_threshold_override_triggers_exit_1(tmp_path):
    """A passing tool (score 1.0) with error_threshold > 1.0 forces exit code 1."""
    path = _project(tmp_path, "echo hello", error=1.01)
    result = runner.invoke(app, ["check", path, "-o", "score", "--workers", "1"])
    assert result.exit_code == 1


_JSON_SCHEMA = {
    "tool_name": str,
    "metrics": dict,
    "details": dict,
    "duration_s": float,
}

_RAW_SCHEMA = {
    "tool_name": str,
    "command": str,
    "stdout": str,
    "stderr": str,
    "return_code": int,
    "timestamp": str,
}


@pytest.mark.parametrize("output,schema", [(["-o", "json"], _JSON_SCHEMA), (["-o", "raw"], _RAW_SCHEMA)])
def test_output_schema_contract(tmp_path, output, schema):
    path = _project(tmp_path, "echo hello")
    result = runner.invoke(app, ["check", path, *output, "--workers", "1"])
    data = json.loads(result.output.strip())
    entry = data[0]
    for key, typ in schema.items():
        assert key in entry, f"missing key: {key}"
        assert isinstance(entry[key], typ), f"{key}: expected {typ}, got {type(entry[key])}"
    assert set(entry.keys()) == set(schema.keys()), f"unexpected keys: {set(entry.keys()) - set(schema.keys())}"


def test_llm_output_only_runs_first_failing_tool(tmp_path):
    """-o llm activates early_exit; the selected defect is from the failing tool, not the passing one."""
    script = tmp_path / "fail.py"
    script.write_text("import sys; sys.exit(1)")
    fail_cmd = f"{{python}} {script.as_posix()}"

    disable = ", ".join(f'"{t}"' for t in _DISABLE_ALL)
    lines = [
        "[tool.cq]",
        f"disable = [{disable}]",
        "",
        "[tool.cq.tools.tool_pass]",
        'command = "echo PASS_OUTPUT"',
        'parser = "ExitCodeParser"',
        "order = 1",
        "warning_threshold = 0.5",
        "error_threshold = 0.0",  # score 1.0 never triggers error
        "",
        "[tool.cq.tools.tool_fail]",
        f'command = "{fail_cmd}"',
        'parser = "ExitCodeParser"',
        "order = 2",
        "warning_threshold = 0.9",
        "error_threshold = 0.9",  # score 0.0 < 0.9 → error → early_exit stops here
    ]
    (tmp_path / "pyproject.toml").write_text("\n".join(lines))
    result = runner.invoke(app, ["check", str(tmp_path), "-o", "llm", "--workers", "1"])
    # LLM format was used
    assert "Please fix" in result.output
    # tool_pass stdout "PASS_OUTPUT" is not the selected defect
    assert "PASS_OUTPUT" not in result.output
