"""Integration tests: user-defined tools run through the full cq check pipeline.

These tests do NOT mock run_tools - they execute real subprocess commands and
verify that results flow correctly through parser -> scorer -> CLI output.
All 11 built-in tools are disabled so each test only runs its user-defined tool.
"""

from typer.testing import CliRunner

from py_cq.cli import app

runner = CliRunner()

_DISABLE_ALL = [
    "compile",
    "ruff",
    "ty",
    "bandit",
    "pytest",
    "coverage",
    "radon-cc",
    "radon-mi",
    "radon-hal",
    "vulture",
    "interrogate",
]


def _project(
    tmp_path,
    tool_name,
    command,
    parser,
    warning=0.9999,
    error=0.9999,
    parser_config=None,
):
    """Write a pyproject.toml with all built-in tools disabled and one user tool."""
    disable = ", ".join(f'"{t}"' for t in _DISABLE_ALL)
    lines = [
        "[tool.cq]",
        f"disable = [{disable}]",
        "",
        f"[tool.cq.tools.{tool_name}]",
        f'command = "{command}"',
        f'parser = "{parser}"',
        "order = 1",
        f"warning_threshold = {warning}",
        f"error_threshold = {error}",
    ]
    if parser_config:
        lines.append(f"\n[tool.cq.tools.{tool_name}.parser_config]")
        for k, v in parser_config.items():
            lines.append(f'{k} = "{v}"' if isinstance(v, str) else f"{k} = {v}")
    (tmp_path / "pyproject.toml").write_text("\n".join(lines))
    return str(tmp_path)


# --- ExitCodeParser ---


def test_exitcode_pass(tmp_path):
    """ExitCodeParser: exit 0 -> score 1.0, process exits 0."""
    path = _project(tmp_path, "mycheck", "echo hello", "ExitCodeParser")
    result = runner.invoke(app, ["check", path, "-o", "score"])
    assert result.exit_code == 0
    assert "1.0" in result.output


def test_exitcode_fail(tmp_path):
    """ExitCodeParser: exit 1 -> score 0.0, process exits 1."""
    script = tmp_path / "fail.py"
    script.write_text("import sys; sys.exit(1)")
    cmd = f"{{python}} {script.as_posix()}"
    path = _project(tmp_path, "mycheck", cmd, "ExitCodeParser")
    result = runner.invoke(app, ["check", path, "-o", "score"])
    assert result.exit_code == 1
    assert "0.0" in result.output


def test_exitcode_llm_output(tmp_path):
    """ExitCodeParser: LLM output includes stdout when the command fails."""
    script = tmp_path / "loud.py"
    script.write_text("import sys; print('critical failure detected'); sys.exit(1)")
    cmd = f"{{python}} {script.as_posix()}"
    path = _project(tmp_path, "mycheck", cmd, "ExitCodeParser", error=0.0)
    result = runner.invoke(app, ["check", path, "-o", "llm"])
    assert result.exit_code == 0
    assert "critical failure detected" in result.output


# --- LineCountParser ---


def test_linecount_no_output(tmp_path):
    """LineCountParser: no stdout lines -> score 1.0."""
    script = tmp_path / "silent.py"
    script.write_text("pass")
    cmd = f"{{python}} {script.as_posix()}"
    path = _project(tmp_path, "mycheck", cmd, "LineCountParser")
    result = runner.invoke(app, ["check", path, "-o", "score"])
    assert result.exit_code == 0
    assert "1.0" in result.output


def test_linecount_with_violations(tmp_path):
    """LineCountParser: N stdout lines -> score between 0 and 1."""
    script = tmp_path / "violations.py"
    script.write_text("print('e1')\nprint('e2')\n")
    cmd = f"{{python}} {script.as_posix()}"
    path = _project(tmp_path, "mycheck", cmd, "LineCountParser", error=0.0)
    result = runner.invoke(app, ["check", path, "-o", "score"])
    assert result.exit_code == 0
    assert 0.0 < float(result.output.strip()) < 1.0


def test_linecount_custom_scale_factor(tmp_path):
    """LineCountParser: stricter scale_factor lowers the score for the same output."""
    script = tmp_path / "one_line.py"
    script.write_text("print('violation')")
    cmd = f"{{python}} {script.as_posix()}"

    (tmp_path / "strict").mkdir()
    path_strict = _project(
        tmp_path / "strict",
        "mycheck",
        cmd,
        "LineCountParser",
        error=0.0,
        parser_config={"scale_factor": 1},
    )

    (tmp_path / "default").mkdir()
    path_default = _project(
        tmp_path / "default", "mycheck", cmd, "LineCountParser", error=0.0
    )

    r_strict = runner.invoke(app, ["check", path_strict, "-o", "score"])
    r_default = runner.invoke(app, ["check", path_default, "-o", "score"])
    assert float(r_strict.output.strip()) < float(r_default.output.strip())


# --- RegexCountParser ---


def test_regexcount_no_match(tmp_path):
    """RegexCountParser: no lines match pattern -> score 1.0."""
    script = tmp_path / "info.py"
    script.write_text("print('INFO: all good')")
    cmd = f"{{python}} {script.as_posix()}"
    path = _project(
        tmp_path,
        "mycheck",
        cmd,
        "RegexCountParser",
        parser_config={"pattern": "^ERROR"},
    )
    result = runner.invoke(app, ["check", path, "-o", "score"])
    assert result.exit_code == 0
    assert "1.0" in result.output


def test_regexcount_with_match(tmp_path):
    """RegexCountParser: matching lines -> score between 0 and 1."""
    script = tmp_path / "errors.py"
    script.write_text("print('ERROR: bad')\nprint('INFO: ok')\n")
    cmd = f"{{python}} {script.as_posix()}"
    path = _project(
        tmp_path,
        "mycheck",
        cmd,
        "RegexCountParser",
        error=0.0,
        parser_config={"pattern": "^ERROR"},
    )
    result = runner.invoke(app, ["check", path, "-o", "score"])
    assert result.exit_code == 0
    assert 0.0 < float(result.output.strip()) < 1.0


def test_regexcount_llm_output_shows_matching_line(tmp_path):
    """RegexCountParser: LLM output includes the matched violation line."""
    script = tmp_path / "mixed.py"
    script.write_text("print('ERROR: something broke')\nprint('INFO: other')\n")
    cmd = f"{{python}} {script.as_posix()}"
    path = _project(
        tmp_path,
        "mycheck",
        cmd,
        "RegexCountParser",
        error=0.0,
        parser_config={"pattern": "^ERROR"},
    )
    result = runner.invoke(app, ["check", path, "-o", "llm"])
    assert result.exit_code == 0
    assert "ERROR: something broke" in result.output
