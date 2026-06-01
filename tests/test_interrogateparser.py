"""Tests for InterrogateParser.parse()."""

from pytest import approx as pytest_approx

from py_cq.localtypes import RawResult
from py_cq.parsers.interrogateparser import InterrogateParser

_TABLE_HEADER = """\
| Name         |  Total |  Miss |  Cover |  Cover% |
|--------------|--------|-------|--------|---------|
"""
_TABLE_FOOTER = """\
|--------------|--------|-------|--------|---------|
| TOTAL        |      5 |     2 |      3 |   60.0% |
"""


def _raw(stdout, command="cmd"):
    """Return a RawResult from the stdout and command."""
    return RawResult(tool_name="interrogate", command=command, stdout=stdout)


def _output(*file_rows):
    """Format file rows into a table."""
    return _TABLE_HEADER + "".join(file_rows) + _TABLE_FOOTER


# --- context_path extraction ---


def test_context_path_extracted_from_command(tmp_path):
    """Test that the context path is correctly extracted from the command."""
    (tmp_path / "src.py").write_text("x = 1\n")
    output = _output("| src.py       |      3 |     1 |      2 |     67% |\n")
    r = InterrogateParser().parse(_raw(output, command=f'interrogate "{tmp_path}"'))
    assert r.metrics["doc_coverage"] == pytest_approx(2 / 3)


def test_context_path_defaults_to_dot_when_no_command_match():
    """Test that context path defaults to dot when no command matches."""
    output = _output("| src/foo.py   |      5 |     2 |      3 |     60% |\n")
    r = InterrogateParser().parse(_raw(output, command="interrogate"))
    assert r.metrics["doc_coverage"] == pytest_approx(3 / 5)
    # File not resolvable from "." in this environment but score is always computed
    assert "doc_coverage" in r.metrics


# --- score calculation ---


def test_score_partial_coverage():
    """Test partial covergare parsing"""
    output = _output("| src/foo.py   |      4 |     1 |      3 |     75% |\n")
    r = InterrogateParser().parse(_raw(output))
    assert r.metrics["doc_coverage"] == pytest_approx(0.75)


def test_score_full_coverage():
    """Test that score calculation provides full coverage."""
    output = (
        _TABLE_HEADER
        + "| src/foo.py   |      5 |     0 |      5 |    100% |\n"
        + "|--------------|--------|-------|--------|---------|\n"
        + "| TOTAL        |      5 |     0 |      5 |  100.0% |\n"
    )
    r = InterrogateParser().parse(_raw(output))
    assert r.metrics["doc_coverage"] == 1.0


def test_score_zero_total_gives_one():
    """Test that a score of zero total gives a doc coverage of one."""
    r = InterrogateParser().parse(_raw(""))
    assert r.metrics["doc_coverage"] == 1.0


# --- .venv files skipped ---


def test_venv_files_excluded_from_score():
    """Test that files in .venv are excluded from the score."""
    output = (
        _TABLE_HEADER
        + "| .venv/lib/foo.py |  10 |     5 |      5 |     50% |\n"
        + "| src/real.py      |   4 |     0 |      4 |    100% |\n"
        + "|------------------|-----|-------|--------|---------|\n"
        + "| TOTAL            |  14 |     5 |      9 |   64.3% |\n"
    )
    r = InterrogateParser().parse(_raw(output))
    assert r.metrics["doc_coverage"] == 1.0  # only real.py counts, 0 missing


# --- prefix from Coverage-for header ---


def test_prefix_applied_when_coverage_root_is_subdir(tmp_path):
    """Verify that the prefix is applied correctly when the coverage root is a subdirectory."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "mod.py").write_text("def f():\n    pass\n")
    coverage_line = f"Coverage for {src}\n"
    output = (
        _TABLE_HEADER
        + coverage_line
        + "| mod.py       |      1 |     1 |      0 |      0% |\n"
        + "|--------------|--------|-------|--------|---------|\n"
        + "| TOTAL        |      1 |     1 |      0 |    0.0% |\n"
    )
    r = InterrogateParser().parse(_raw(output, command=f'interrogate "{tmp_path}"'))
    # file key should be prefixed with "src"
    assert any("src" in k for k in r.details)


def test_prefix_not_applied_when_coverage_root_unrelated(tmp_path):
    """Verify that the prefix is not applied when the coverage root is unrelated.

    Args:
        tmp_path: Pytest fixture for temporary directory.
    """
    output = (
        _TABLE_HEADER
        + "Coverage for /unrelated/path\n"
        + "| src/mod.py   |      2 |     1 |      1 |     50% |\n"
        + "|--------------|--------|-------|--------|---------|\n"
        + "| TOTAL        |      2 |     1 |      1 |   50.0% |\n"
    )
    r = InterrogateParser().parse(_raw(output, command=f'interrogate "{tmp_path}"'))
    # ValueError swallowed, no prefix - key stays as-is
    assert r.metrics["doc_coverage"] == pytest_approx(0.5)


# --- skip_empty_init ---


def test_skip_empty_init_default(tmp_path):
    """Test empty"""
    (tmp_path / "__init__.py").write_text("")
    output = (
        _TABLE_HEADER
        + "| __init__.py  |      1 |     1 |      0 |      0% |\n"
        + "|--------------|--------|-------|--------|---------|\n"
        + "| TOTAL        |      1 |     1 |      0 |    0.0% |\n"
    )
    r = InterrogateParser().parse(_raw(output, command=f'interrogate "{tmp_path}"'))
    assert r.metrics["doc_coverage"] == 1.0  # empty init skipped entirely


def test_skip_empty_init_disabled(tmp_path):
    """Test skip empty"""
    (tmp_path / "__init__.py").write_text("")
    output = (
        _TABLE_HEADER
        + "| __init__.py  |      1 |     1 |      0 |      0% |\n"
        + "|--------------|--------|-------|--------|---------|\n"
        + "| TOTAL        |      1 |     1 |      0 |    0.0% |\n"
    )
    r = InterrogateParser({"skip_empty_init": False}).parse(
        _raw(output, command=f'interrogate "{tmp_path}"')
    )
    assert r.metrics["doc_coverage"] == 0.0


# --- on-disk _missing_docstrings integration ---


def test_details_populated_from_real_file(tmp_path):
    """Test details"""
    f = tmp_path / "mod.py"
    f.write_text("def helper(x):\n    return x\n")
    output = (
        _TABLE_HEADER
        + "| mod.py       |      1 |     1 |      0 |      0% |\n"
        + "|--------------|--------|-------|--------|---------|\n"
        + "| TOTAL        |      1 |     1 |      0 |    0.0% |\n"
    )
    r = InterrogateParser().parse(_raw(output, command=f'interrogate "{tmp_path}"'))
    issues = r.details.get("mod.py", [])
    assert any(i["code"] == "D103" for i in issues)
    assert any("helper" in i["message"] for i in issues)


def test_details_empty_when_file_not_on_disk():
    """Test details"""
    output = _output("| src/ghost.py |      3 |     2 |      1 |     33% |\n")
    r = InterrogateParser().parse(_raw(output))
    assert "src/ghost.py" not in r.details


def test_d100_module_code_assigned(tmp_path):
    """Test D100"""
    f = tmp_path / "mod.py"
    f.write_text("x = 1\n")
    output = (
        _TABLE_HEADER
        + "| mod.py       |      1 |     1 |      0 |      0% |\n"
        + "|--------------|--------|-------|--------|---------|\n"
        + "| TOTAL        |      1 |     1 |      0 |    0.0% |\n"
    )
    r = InterrogateParser().parse(_raw(output, command=f'interrogate "{tmp_path}"'))
    issues = r.details.get("mod.py", [])
    assert any(i["code"] == "D100" for i in issues)
    assert any(i["line"] == 1 for i in issues)


def test_d101_class_code_assigned(tmp_path):
    """Test D101"""
    f = tmp_path / "mod.py"
    f.write_text('"""module."""\nclass Foo:\n    pass\n')
    output = (
        _TABLE_HEADER
        + "| mod.py       |      2 |     1 |      1 |     50% |\n"
        + "|--------------|--------|-------|--------|---------|\n"
        + "| TOTAL        |      2 |     1 |      1 |   50.0% |\n"
    )
    r = InterrogateParser().parse(_raw(output, command=f'interrogate "{tmp_path}"'))
    issues = r.details.get("mod.py", [])
    assert any(i["code"] == "D101" for i in issues)


# --- interrogate_cfg filtering ---


def test_ignore_semiprivate_filters_underscore_functions(tmp_path):
    """Test ignore semi private"""
    f = tmp_path / "mod.py"
    f.write_text('"""module."""\ndef _helper():\n    pass\n')
    (tmp_path / "pyproject.toml").write_text(
        "[tool.interrogate]\nignore-semiprivate = true\n"
    )
    output = (
        _TABLE_HEADER
        + "| mod.py       |      2 |     1 |      1 |     50% |\n"
        + "|--------------|--------|-------|--------|---------|\n"
        + "| TOTAL        |      2 |     1 |      1 |   50.0% |\n"
    )
    r = InterrogateParser().parse(_raw(output, command=f'interrogate "{tmp_path}"'))
    issues = r.details.get("mod.py", [])
    assert not any("_helper" in i.get("message", "") for i in issues)


def test_ignore_magic_filters_dunder_methods(tmp_path):
    """Test ignore magic"""
    f = tmp_path / "mod.py"
    f.write_text('"""module."""\nclass Foo:\n    """Foo."""\n    def __str__(self):\n        return ""\n')
    (tmp_path / "pyproject.toml").write_text(
        "[tool.interrogate]\nignore-magic = true\n"
    )
    output = (
        _TABLE_HEADER
        + "| mod.py       |      3 |     1 |      2 |     67% |\n"
        + "|--------------|--------|-------|--------|---------|\n"
        + "| TOTAL        |      3 |     1 |      2 |   66.7% |\n"
    )
    r = InterrogateParser().parse(_raw(output, command=f'interrogate "{tmp_path}"'))
    issues = r.details.get("mod.py", [])
    assert not any("__str__" in i.get("message", "") for i in issues)


# --- details ordering ---


def test_details_sorted_worst_coverage_first(tmp_path):
    """Test sorted"""
    (tmp_path / "good.py").write_text("def f():\n    pass\n")
    (tmp_path / "bad.py").write_text("def g():\n    pass\n")
    output = (
        _TABLE_HEADER
        + "| good.py      |      4 |     1 |      3 |     75% |\n"
        + "| bad.py       |      4 |     3 |      1 |     25% |\n"
        + "|--------------|--------|-------|--------|---------|\n"
        + "| TOTAL        |      8 |     4 |      4 |   50.0% |\n"
    )
    r = InterrogateParser().parse(_raw(output, command=f'interrogate "{tmp_path}"'))
    keys = list(r.details.keys())
    assert keys.index("bad.py") < keys.index("good.py")

