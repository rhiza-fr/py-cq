"""Tests for llm_formatter pipeline and each parser's format_llm_message."""

from py_cq.llm_formatter import format_for_llm
from py_cq.localtypes import AbstractParser, CombinedToolResults, RawResult, ToolConfig, ToolResult
from py_cq.parsers.compileparser import CompileParser
from py_cq.parsers.halsteadparser import HalsteadParser
from py_cq.parsers.interrogateparser import InterrogateParser
from py_cq.parsers.pytestparser import PytestParser
from py_cq.parsers.ruffparser import RuffParser
from py_cq.parsers.typarser import TyParser

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


# --- priority ordering ---

def test_priority1_beats_priority3_same_severity():
    """Within the same severity tier, lower priority number wins."""
    registry = make_registry(make_config("compile", 1), make_config("ruff", 3))
    combined = make_combined([
        make_tr("ruff", 0.4),    # error state
        make_tr("compile", 0.3), # error state, higher priority → wins
    ])
    result = format_for_llm(registry, combined, cq_invocation=CQ)
    assert "0.300" in result  # compile selected
    assert "0.400" not in result


def test_priority2_beats_priority5_same_severity():
    """Within the same severity tier, lower priority number wins."""
    registry = make_registry(make_config("pytest", 2), make_config("interrogate", 5))
    combined = make_combined([
        make_tr("interrogate", 0.4), # error state
        make_tr("pytest", 0.3),      # error state, higher priority → wins
    ])
    result = format_for_llm(registry, combined, cq_invocation=CQ)
    assert "0.300" in result  # pytest selected
    assert "0.400" not in result


def test_severity_beats_priority():
    """A tool in error state wins over a higher-priority tool in warning/ok state."""
    registry = make_registry(make_config("compile", 1), make_config("interrogate", 5))
    combined = make_combined([
        make_tr("compile", 0.8),     # warning/ok state
        make_tr("interrogate", 0.3), # error state → wins despite lower priority
    ])
    result = format_for_llm(registry, combined, cq_invocation=CQ)
    assert "0.300" in result  # interrogate selected
    assert "0.800" not in result


def test_same_priority_worst_score_wins():
    registry = make_registry(make_config("ruff", 3), make_config("ty", 3))
    combined = make_combined([
        make_tr("ruff", 0.8),
        make_tr("ty", 0.2),  # worse score → wins
    ])
    result = format_for_llm(registry, combined, cq_invocation=CQ)
    assert "0.200" in result  # ty selected
    assert "0.800" not in result


def test_passing_tool_ignored():
    registry = make_registry(make_config("compile", 1), make_config("ruff", 3))
    combined = make_combined([
        make_tr("compile", 1.0), # passes → ignored
        make_tr("ruff", 0.5),
    ])
    result = format_for_llm(registry, combined, cq_invocation=CQ)
    assert "0.500" in result  # ruff selected
    assert "1.000" not in result


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


def test_interrogate_format_llm_message():
    tr = _tr("interrogate", {"src/qux.py": {"total": 4, "missing": 2, "coverage": 0.5}})
    msg = InterrogateParser().format_llm_message(tr)
    assert "src/qux.py" in msg
    assert "2 undocumented" in msg


def test_pytest_format_llm_message():
    tr = _tr("pytest", {"tests/test_foo.py": {"test_bar": "FAILED", "test_baz": "PASSED"}})
    msg = PytestParser().format_llm_message(tr)
    assert "tests/test_foo.py::test_bar" in msg
    assert "FAILED" in msg
    assert "test_baz" not in msg


def test_pytest_format_llm_message_no_failures():
    tr = _tr("pytest", {})
    assert "no details" in PytestParser().format_llm_message(tr).lower()


def test_halstead_format_llm_message_function_bugs():
    tr = _tr("radon hal", {
        "src/foo.py": {
            "bug_free": 0.9, "smallness": 0.9, "bugs": 0.05, "volume": 100,
            "functions": {
                "big_fn": {"no_bugs": 0.3, "smallness": 0.8, "bugs": 0.45, "volume": 200},
                "small_fn": {"no_bugs": 0.95, "smallness": 0.95, "bugs": 0.01, "volume": 20},
            },
        }
    })
    tr.metrics = {"functions_bug_free": 0.3, "functions_smallness": 0.8, "file_bug_free": 0.9, "file_smallness": 0.9}
    msg = HalsteadParser().format_llm_message(tr)
    assert "src/foo.py" in msg
    assert "big_fn" in msg
    assert "0.450" in msg
    assert "complexity" in msg.lower() or "bug" in msg.lower()


def test_halstead_format_llm_message_file_volume():
    tr = _tr("radon hal", {
        "src/large.py": {
            "bug_free": 0.8, "smallness": 0.2, "bugs": 0.1, "volume": 1900,
            "functions": {},
        }
    })
    tr.metrics = {"file_bug_free": 0.8, "file_smallness": 0.2, "functions_bug_free": 1.0, "functions_smallness": 1.0}
    msg = HalsteadParser().format_llm_message(tr)
    assert "src/large.py" in msg
    assert "1900" in msg
    assert "split" in msg.lower() or "large" in msg.lower()


def test_halstead_format_llm_message_no_metrics():
    tr = ToolResult(metrics={}, details={}, raw=RawResult())
    assert "No Halstead" in HalsteadParser().format_llm_message(tr)


def test_halstead_format_llm_message_no_matching_files():
    tr = _tr("radon hal", {})
    tr.metrics = {"file_bug_free": 0.3}
    msg = HalsteadParser().format_llm_message(tr)
    assert "file_bug_free" in msg
    assert "0.300" in msg


def test_default_fallback_metric():
    """AbstractParser default shows metric name and score."""
    tr = ToolResult(metrics={"coverage": 0.4}, raw=RawResult())
    msg = FakeParser().format_llm_message(tr)
    assert "coverage" in msg
    assert "0.400" in msg


def test_format_for_llm_default_invocation():
    config = ToolConfig(name="ruff", command="", parser_class=RuffParser, priority=3)
    registry = {"ruff": config}
    tr = ToolResult(
        metrics={"lint": 0.5},
        details={"src/foo.py": [{"line": 1, "code": "E501", "message": "too long"}]},
        raw=RawResult(tool_name="ruff", command="python -m ruff check src/"),
    )
    combined = CombinedToolResults(path=".", tool_results=[tr])
    result = format_for_llm(registry, combined)  # no cq_invocation → uses sys.argv
    assert "cq" in result
