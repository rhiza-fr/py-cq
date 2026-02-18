"""Tests for llm_formatter pipeline and each parser's format_llm_message."""

from cq.llm_formatter import format_for_llm, _clean_command
from cq.localtypes import AbstractParser, CombinedToolResults, RawResult, ToolConfig, ToolResult
from cq.parsers.compileparser import CompileParser
from cq.parsers.ruffparser import RuffParser
from cq.parsers.typarser import TyParser
from cq.parsers.pydocstyleparser import PydocstyleParser
from cq.parsers.pytestparser import PytestParser

CQ = "cq run test.py --llm"


class FakeParser(AbstractParser):
    """Minimal parser for pipeline tests; format_llm_message uses the default fallback."""
    def parse(self, raw_result): return ToolResult()


def make_config(name: str, priority: int) -> ToolConfig:
    return ToolConfig(name=name, command="", parser_class=FakeParser, priority=priority)


def make_tr(tool_name: str, score: float, details: dict | None = None, command: str = "") -> ToolResult:
    return ToolResult(
        metrics={"score": score},
        details=details or {},
        raw=RawResult(tool_name=tool_name, command=command),
    )


def make_combined(tool_results: list[ToolResult]) -> CombinedToolResults:
    return CombinedToolResults(path="test.py", tool_results=tool_results)


def make_registry(*configs: ToolConfig) -> dict:
    return {tc.name: tc for tc in configs}


# --- command cleaning ---

def test_clean_command_strips_interpreter():
    cmd = r"C:\venv\python.exe -m ruff check --no-cache src/foo.py"
    assert _clean_command(cmd) == "ruff check --no-cache src/foo.py"


def test_clean_command_no_module_flag():
    assert _clean_command("ruff check src/foo.py") == "ruff check src/foo.py"


def test_clean_command_empty():
    assert _clean_command("") == ""


# --- priority ordering ---

def test_priority1_beats_priority3_same_severity():
    """Within the same severity tier, lower priority number wins."""
    registry = make_registry(make_config("compile", 1), make_config("ruff", 3))
    combined = make_combined([
        make_tr("ruff", 0.4, command="python -m ruff check src/"),    # error state (< 0.5)
        make_tr("compile", 0.3, command="python -m compileall src/"),  # error state (< 0.5)
    ])
    result = format_for_llm(registry, combined, cq_invocation=CQ)
    assert "compileall src/" in result
    assert "ruff check" not in result


def test_priority2_beats_priority5_same_severity():
    """Within the same severity tier, lower priority number wins."""
    registry = make_registry(make_config("pytest", 2), make_config("pydocstyle", 5))
    combined = make_combined([
        make_tr("pydocstyle", 0.4, command="python -m pydocstyle src/"),  # error state (< 0.5)
        make_tr("pytest", 0.3, command="python -m pytest -v src/"),        # error state (< 0.5)
    ])
    result = format_for_llm(registry, combined, cq_invocation=CQ)
    assert "pytest -v src/" in result
    assert "pydocstyle" not in result


def test_severity_beats_priority():
    """A tool in error state wins over a higher-priority tool in OK state."""
    registry = make_registry(make_config("compile", 1), make_config("pydocstyle", 5))
    combined = make_combined([
        make_tr("compile", 0.8, command="python -m compileall src/"),    # OK state (>= 0.7)
        make_tr("pydocstyle", 0.3, command="python -m pydocstyle src/"), # error state (< 0.5)
    ])
    result = format_for_llm(registry, combined, cq_invocation=CQ)
    assert "pydocstyle src/" in result
    assert "compileall" not in result


def test_same_priority_worst_score_wins():
    registry = make_registry(make_config("ruff", 3), make_config("ty", 3))
    combined = make_combined([
        make_tr("ruff", 0.8, command="python -m ruff check src/"),
        make_tr("ty", 0.2, command="python -m ty check src/"),
    ])
    result = format_for_llm(registry, combined, cq_invocation=CQ)
    assert "ty check src/" in result
    assert "ruff check" not in result


def test_passing_tool_ignored():
    registry = make_registry(make_config("compile", 1), make_config("ruff", 3))
    combined = make_combined([
        make_tr("compile", 1.0, command="python -m compileall src/"),
        make_tr("ruff", 0.5, command="python -m ruff check src/"),
    ])
    result = format_for_llm(registry, combined, cq_invocation=CQ)
    assert "ruff check src/" in result
    assert "compileall" not in result


def test_all_passing_returns_no_issues():
    registry = make_registry(make_config("ruff", 3))
    result = format_for_llm(registry, make_combined([make_tr("ruff", 1.0)]), cq_invocation=CQ)
    assert result.startswith("# No issues found")


def test_empty_results_returns_no_issues():
    result = format_for_llm({}, make_combined([]), cq_invocation=CQ)
    assert result.startswith("# No issues found")


def test_cq_invocation_in_footer():
    registry = make_registry(make_config("ruff", 3))
    result = format_for_llm(registry, make_combined([make_tr("ruff", 0.5)]), cq_invocation="cq run myfile.py --llm")
    assert "cq run myfile.py --llm" in result


# --- parser format_llm_message ---

def _tr(tool_name: str, details: dict) -> ToolResult:
    return ToolResult(metrics={"score": 0.5}, details=details, raw=RawResult(tool_name=tool_name))


def test_compile_format_llm_message():
    tr = _tr("compile", {"failed_files": {
        "src/foo.py": {"line": 10, "src": "x = {a = b}", "type": "SyntaxError", "help": "invalid syntax"}
    }})
    msg = CompileParser().format_llm_message(tr)
    assert "src/foo.py:10" in msg
    assert "SyntaxError" in msg
    assert "invalid syntax" in msg
    assert "x = {a = b}" in msg


def test_compile_format_llm_message_no_details():
    tr = _tr("compile", {})
    assert "no details" in CompileParser().format_llm_message(tr)


def test_ruff_format_llm_message():
    tr = _tr("ruff", {"src/bar.py": [{"line": 42, "code": "E501", "message": "line too long"}]})
    msg = RuffParser().format_llm_message(tr)
    assert "src/bar.py:42" in msg
    assert "E501" in msg
    assert "line too long" in msg


def test_ty_format_llm_message():
    tr = _tr("ty", {"src/baz.py": [{"line": 7, "code": "possibly-unbound", "message": "x may be unbound"}]})
    msg = TyParser().format_llm_message(tr)
    assert "src/baz.py:7" in msg
    assert "possibly-unbound" in msg


def test_pydocstyle_format_llm_message():
    tr = _tr("pydocstyle", {"src/qux.py": [{"line": 1, "code": "D100", "message": "Missing docstring"}]})
    msg = PydocstyleParser().format_llm_message(tr)
    assert "src/qux.py:1" in msg
    assert "D100" in msg


def test_pytest_format_llm_message():
    tr = _tr("pytest", {"tests/test_foo.py": {"test_bar": "FAILED", "test_baz": "PASSED"}})
    msg = PytestParser().format_llm_message(tr)
    assert "tests/test_foo.py::test_bar" in msg
    assert "FAILED" in msg
    assert "test_baz" not in msg


def test_pytest_format_llm_message_no_failures():
    tr = _tr("pytest", {})
    assert "no details" in PytestParser().format_llm_message(tr).lower()


def test_default_fallback_metric():
    """AbstractParser default shows metric name and score."""
    tr = ToolResult(metrics={"coverage": 0.4}, raw=RawResult())
    msg = FakeParser().format_llm_message(tr)
    assert "coverage" in msg
    assert "0.400" in msg
