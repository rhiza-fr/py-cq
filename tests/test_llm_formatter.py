"""Tests for llm_formatter pipeline and each parser's format_llm_message."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from py_cq.llm_formatter import _severity, format_for_llm
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


def make_config(name: str, order: int) -> ToolConfig:
    return ToolConfig(name=name, command="", parser_class=FakeParser, order=order)


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


# --- _severity ---

def test_severity_ok_returns_2():
    cfg = make_config("tool", 1)
    assert _severity(1.0, cfg) == 2


def test_severity_error_returns_0():
    cfg = make_config("tool", 1)  # error_threshold=0.5
    assert _severity(0.3, cfg) == 0


def test_severity_warning_returns_1():
    cfg = make_config("tool", 1)  # error_threshold=0.5, warning_threshold=0.7
    assert _severity(0.6, cfg) == 1


def test_severity_at_error_threshold_returns_warning():
    cfg = make_config("tool", 1)  # error_threshold=0.5 (strict <)
    assert _severity(0.5, cfg) == 1  # exactly at boundary → not error


def test_severity_at_warning_threshold_returns_ok():
    cfg = make_config("tool", 1)  # warning_threshold=0.7 (strict <)
    assert _severity(0.7, cfg) == 2  # exactly at boundary → ok


@pytest.mark.parametrize("score,warn,err,expected", [
    (0.0, 0.8, 0.6, 0),   # deep error
    (0.5, 0.8, 0.6, 0),   # below error
    (0.6, 0.8, 0.6, 1),   # exactly at error_threshold → warning
    (0.7, 0.8, 0.6, 1),   # between thresholds → warning
    (0.8, 0.8, 0.6, 2),   # exactly at warning_threshold → ok
    (1.0, 0.8, 0.6, 2),   # perfect → ok
    (0.3, 0.3, 0.3, 2),   # equal thresholds, score at both → ok
    (0.29, 0.3, 0.3, 0),  # below both equal thresholds → error
])
def test_severity_parametrized_custom_thresholds(score, warn, err, expected):
    cfg = ToolConfig(name="t", command="", parser_class=FakeParser, order=1,
                     warning_threshold=warn, error_threshold=err)
    assert _severity(score, cfg) == expected


@given(
    score=st.floats(min_value=0.0, max_value=1.0),
    error_threshold=st.floats(min_value=0.0, max_value=1.0),
    warning_threshold=st.floats(min_value=0.0, max_value=1.0),
)
@settings(max_examples=300)
def test_severity_correct_region(score, error_threshold, warning_threshold):
    cfg = ToolConfig(name="t", command="", parser_class=FakeParser, order=1,
                     error_threshold=error_threshold, warning_threshold=warning_threshold)
    result = _severity(score, cfg)
    assert result in (0, 1, 2)
    if score < error_threshold:
        assert result == 0
    elif score < warning_threshold:
        assert result == 1
    else:
        assert result == 2


@given(
    score_lo=st.floats(min_value=0.0, max_value=1.0),
    delta=st.floats(min_value=0.0, max_value=1.0),
    error_threshold=st.floats(min_value=0.0, max_value=1.0),
    warning_threshold=st.floats(min_value=0.0, max_value=1.0),
)
@settings(max_examples=300)
def test_severity_monotone(score_lo, delta, error_threshold, warning_threshold):
    score_hi = min(score_lo + delta, 1.0)
    cfg = ToolConfig(name="t", command="", parser_class=FakeParser, order=1,
                     error_threshold=error_threshold, warning_threshold=warning_threshold)
    assert _severity(score_lo, cfg) <= _severity(score_hi, cfg)


# --- order ordering ---

def test_order1_beats_order3_same_severity():
    """Within the same severity tier, lower order number wins."""
    registry = make_registry(make_config("compile", 1), make_config("ruff", 3))
    combined = make_combined([
        make_tr("ruff", 0.4),    # error state
        make_tr("compile", 0.3), # error state, lower order → wins
    ])
    result = format_for_llm(registry, combined, cq_invocation=CQ)
    assert "0.300" in result  # compile selected
    assert "0.400" not in result


def test_order2_beats_order5_same_severity():
    """Within the same severity tier, lower order number wins."""
    registry = make_registry(make_config("pytest", 2), make_config("interrogate", 5))
    combined = make_combined([
        make_tr("interrogate", 0.4), # error state
        make_tr("pytest", 0.3),      # error state, lower order → wins
    ])
    result = format_for_llm(registry, combined, cq_invocation=CQ)
    assert "0.300" in result  # pytest selected
    assert "0.400" not in result


def test_severity_beats_order():
    """A tool in error state wins over a lower-order tool in warning/ok state."""
    registry = make_registry(make_config("compile", 1), make_config("interrogate", 5))
    combined = make_combined([
        make_tr("compile", 0.8),     # warning/ok state
        make_tr("interrogate", 0.3), # error state → wins despite higher order number
    ])
    result = format_for_llm(registry, combined, cq_invocation=CQ)
    assert "0.300" in result  # interrogate selected
    assert "0.800" not in result


def test_same_order_worst_score_wins():
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
    result = format_for_llm(registry, make_combined([make_tr("ruff", 0.5)]), cq_invocation="cq run myfile.py --llm", hint=True)
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


def test_format_for_llm_passing_exact_format():
    """Passing case produces the exact expected string."""
    registry = make_registry(make_config("ruff", 3))
    combined = make_combined([make_tr("ruff", 1.0)])
    result = format_for_llm(registry, combined, cq_invocation=CQ)
    assert result == "# No issues found\n\nOverall score: **1.000 / 1.0**"


def test_format_for_llm_defect_footer_exact():
    """Defect output ends with the exact footer (no hint by default)."""
    registry = make_registry(make_config("ruff", 3))
    result = format_for_llm(registry, make_combined([make_tr("ruff", 0.5)]), cq_invocation=CQ)
    assert result.endswith("Please fix only this issue.")

def test_format_for_llm_defect_footer_hint():
    """With hint=True the footer includes the run-again instruction."""
    registry = make_registry(make_config("ruff", 3))
    result = format_for_llm(registry, make_combined([make_tr("ruff", 0.5)]), cq_invocation=CQ, hint=True)
    assert result.endswith(f"Please fix only this issue. After fixing, run `{CQ}` to verify.")


def test_format_for_llm_context_lines_forwarded():
    """context_lines is forwarded to parser.format_llm_message."""
    received: dict = {}

    class RecordingParser(AbstractParser):
        def parse(self, raw_result): return ToolResult()
        def format_llm_message(self, tr, *, context_lines=15, limit=1):
            received["context_lines"] = context_lines
            return "recorded"

    cfg = ToolConfig(name="tool", command="", parser_class=RecordingParser, order=1)
    tr = make_tr("tool", 0.3)
    combined = make_combined([tr])
    format_for_llm({"tool": cfg}, combined, cq_invocation=CQ, context_lines=5)
    assert received.get("context_lines") == 5


@given(st.lists(st.floats(min_value=0.0, max_value=1.0), min_size=1, max_size=5))
@settings(max_examples=50)
def test_format_for_llm_output_starts_with_heading(scores):
    configs = [make_config(f"tool{i}", i + 1) for i in range(len(scores))]
    registry = make_registry(*configs)
    trs = [make_tr(f"tool{i}", s) for i, s in enumerate(scores)]
    result = format_for_llm(registry, make_combined(trs), cq_invocation="cq check .")
    # Every output is either the passing header or a defect with the footer
    assert result.startswith("# No issues found") or "Please fix only this issue" in result


@given(st.lists(st.floats(min_value=0.0, max_value=1.0), min_size=0, max_size=5))
@settings(max_examples=100)
def test_format_for_llm_never_raises(scores):
    """format_for_llm does not raise for arbitrary valid inputs."""
    configs = [make_config(f"tool{i}", i + 1) for i in range(len(scores))]
    registry = make_registry(*configs)
    trs = [make_tr(f"tool{i}", s) for i, s in enumerate(scores)]
    result = format_for_llm(registry, make_combined(trs), cq_invocation=CQ)
    assert isinstance(result, str)


def test_format_for_llm_unknown_tool_name_in_result():
    """format_for_llm with a result whose tool_name is absent from the registry does not raise."""
    # Empty registry — result's tool name has no matching config
    tr = make_tr("unknown_tool", 0.3)
    combined = make_combined([tr])
    result = format_for_llm({}, combined, cq_invocation=CQ)
    # The unknown tool is filtered out by the walrus operator (cfg := by_name.get(...))
    assert isinstance(result, str)
    assert result.startswith("# No issues found")


def test_format_for_llm_partial_registry_unknown_tool():
    """format_for_llm skips results whose tool_name is not in the provided registry."""
    registry = make_registry(make_config("known_tool", 3))
    tr_unknown = make_tr("unknown_tool", 0.1)
    tr_known = make_tr("known_tool", 0.5)
    combined = make_combined([tr_unknown, tr_known])
    result = format_for_llm(registry, combined, cq_invocation=CQ)
    # unknown_tool has no config so it is ignored; known_tool (0.5) is selected
    assert isinstance(result, str)
    assert "0.500" in result


@given(st.permutations([0, 1, 2, 3]))
@settings(max_examples=50)
def test_format_for_llm_selection_is_shuffle_invariant(perm):
    """The tool selected by format_for_llm is the same regardless of input list order."""
    configs = [
        make_config("compile", 1),
        make_config("ruff", 3),
        make_config("ty", 4),
        make_config("interrogate", 5),
    ]
    trs = [
        make_tr("compile", 0.90),   # ok — not in failing list
        make_tr("ruff", 0.42),      # error, order 3 — lowest order among errors → selected
        make_tr("ty", 0.31),        # error, order 4
        make_tr("interrogate", 0.45),  # error, order 5
    ]
    registry = make_registry(*configs)
    shuffled = [trs[i] for i in perm]
    result = format_for_llm(registry, make_combined(shuffled), cq_invocation=CQ)
    # ruff (order 3) should always be selected: its metric "0.420" appears; others should not
    assert "0.420" in result
    assert "0.310" not in result
    assert "0.450" not in result


def test_context_lines_affects_output_length(tmp_path):
    """context_lines controls how many source lines appear; more lines → longer output."""
    test_file = tmp_path / "test_long.py"
    # Write a function with 20 body lines so context_lines=1 vs context_lines=10 differ visibly
    body_lines = "\n".join(f"    x{i} = {i}" for i in range(20))
    test_file.write_text(f"def test_long():\n{body_lines}\n")

    stdout = "________ test_long ________\nE   AssertionError\n"
    cfg = ToolConfig(name="pytest", command="", parser_class=PytestParser, order=5)
    tr = ToolResult(
        metrics={"tests": 0.0},
        details={str(test_file): {"test_long": "FAILED"}},
        raw=RawResult(tool_name="pytest", stdout=stdout),
    )
    combined = CombinedToolResults(".", [tr])

    r_small = format_for_llm({"pytest": cfg}, combined, cq_invocation=CQ, context_lines=1)
    r_large = format_for_llm({"pytest": cfg}, combined, cq_invocation=CQ, context_lines=10)
    assert len(r_large) > len(r_small)


def test_format_for_llm_default_invocation():
    config = ToolConfig(name="ruff", command="", parser_class=RuffParser, order=3)
    registry = {"ruff": config}
    tr = ToolResult(
        metrics={"lint": 0.5},
        details={"src/foo.py": [{"line": 1, "code": "E501", "message": "too long"}]},
        raw=RawResult(tool_name="ruff", command="python -m ruff check src/"),
    )
    combined = CombinedToolResults(path=".", tool_results=[tr])
    result = format_for_llm(registry, combined, hint=True)  # no cq_invocation → uses sys.argv
    assert "cq" in result
    assert "src/foo.py" in result  # file from ruff details
    assert "E501" in result         # specific violation code
    assert "Please fix" in result   # LLM formatter footer


def test_format_for_llm_limit_multiple_issues():
    config = ToolConfig(name="ruff", command="", parser_class=RuffParser, order=3)
    registry = {"ruff": config}
    tr = ToolResult(
        metrics={"lint": 0.3},
        details={"src/foo.py": [
            {"line": 1, "code": "E501", "message": "line too long"},
            {"line": 2, "code": "F401", "message": "[*] `os` imported but unused"},
            {"line": 3, "code": "F841", "message": "Local variable `x` is assigned to but never used"},
        ]},
        raw=RawResult(tool_name="ruff"),
    )
    combined = CombinedToolResults(path=".", tool_results=[tr])
    result = format_for_llm(registry, combined, limit=2)
    assert "---" in result          # separator between issues
    assert "E501" in result
    assert "F401" in result
    assert "F841" not in result     # third issue excluded
    assert "Please fix these 2 issues" in result


def test_format_for_llm_limit_1_unchanged():
    config = ToolConfig(name="ruff", command="", parser_class=RuffParser, order=3)
    registry = {"ruff": config}
    tr = ToolResult(
        metrics={"lint": 0.3},
        details={"src/foo.py": [
            {"line": 1, "code": "E501", "message": "line too long"},
            {"line": 2, "code": "F401", "message": "[*] `os` imported but unused"},
        ]},
        raw=RawResult(tool_name="ruff"),
    )
    combined = CombinedToolResults(path=".", tool_results=[tr])
    result = format_for_llm(registry, combined, limit=1)
    assert "E501" in result
    assert "F401" not in result
    assert "Please fix only this issue" in result
