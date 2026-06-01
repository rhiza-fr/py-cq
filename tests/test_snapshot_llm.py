"""Snapshot tests for format_for_llm output format.

These lock the exact markdown produced for common defect types so that
silent format regressions fail loudly.
"""

from py_cq.llm_formatter import format_for_llm
from py_cq.localtypes import CombinedToolResults, RawResult, ToolConfig, ToolResult
from py_cq.parsers.banditparser import BanditParser
from py_cq.parsers.compileparser import CompileParser
from py_cq.parsers.complexityparser import ComplexityParser
from py_cq.parsers.coverageparser import CoverageParser
from py_cq.parsers.exitcodeparser import ExitCodeParser
from py_cq.parsers.halsteadparser import HalsteadParser
from py_cq.parsers.interrogateparser import InterrogateParser
from py_cq.parsers.linecountparser import LineCountParser
from py_cq.parsers.maintainabilityparser import MaintainabilityParser
from py_cq.parsers.pytestparser import PytestParser
from py_cq.parsers.regexcountparser import RegexCountParser
from py_cq.parsers.ruffparser import RuffParser
from py_cq.parsers.typarser import TyParser
from py_cq.parsers.vultureparser import VultureParser

CQ = "cq run test.py --llm"

RUFF_DEFECT_SNAPSHOT = (
    "src/bar.py:42 - E501: line too long\n\nPlease fix only this issue."
)

COMPILE_DEFECT_SNAPSHOT = (
    "src/foo.py:10 - SyntaxError: invalid syntax\n"
    "```python\n"
    "x = {a = b}\n"
    "```\n\n"
    "Please fix only this issue."
)

BANDIT_DEFECT_SNAPSHOT = (
    "src/vuln.py:5 - B101: [HIGH] Use of assert detected\n\nPlease fix only this issue."
)

COVERAGE_DEFECT_SNAPSHOT = (
    "src/low.py - 60% coverage (40 uncovered lines)\n\n"
    "Add tests to: tests/test_low.py\n\n"
    "Please fix only this issue."
)

VULTURE_DEFECT_SNAPSHOT = (
    "src/dead.py:10 - **unused function** `old_helper` (80% confidence)\n\n"
    "Please fix only this issue."
)

TY_DEFECT_SNAPSHOT = (
    "src/baz.py:7 - possibly-unbound: x may be unbound\n\nPlease fix only this issue."
)


def test_ruff_defect_snapshot():
    """Test the snapshot for ruff defect."""
    cfg = ToolConfig(name="ruff", command="", parser_class=RuffParser, order=3)
    tr = ToolResult(
        metrics={"lint": 0.5},
        details={
            "src/bar.py": [{"line": 42, "code": "E501", "message": "line too long"}]
        },
        raw=RawResult(tool_name="ruff"),
    )
    result = format_for_llm(
        {"ruff": cfg}, CombinedToolResults(".", [tr]), cq_invocation=CQ
    )
    assert result == RUFF_DEFECT_SNAPSHOT


def test_compile_defect_snapshot():
    """Test for compile defect snapshot."""
    cfg = ToolConfig(name="compile", command="", parser_class=CompileParser, order=1)
    tr = ToolResult(
        metrics={"compile": 0.5},
        details={
            "failed_files": {
                "src/foo.py": {
                    "line": 10,
                    "type": "SyntaxError",
                    "help": "invalid syntax",
                    "src": "x = {a = b}",
                }
            }
        },
        raw=RawResult(tool_name="compile"),
    )
    result = format_for_llm(
        {"compile": cfg}, CombinedToolResults(".", [tr]), cq_invocation=CQ
    )
    assert result == COMPILE_DEFECT_SNAPSHOT


def test_ty_defect_snapshot():
    """Test that ty defect snapshot is correctly formatted."""
    cfg = ToolConfig(name="ty", command="", parser_class=TyParser, order=2)
    tr = ToolResult(
        metrics={"type_check": 0.5},
        details={
            "src/baz.py": [
                {
                    "line": 7,
                    "code": "possibly-unbound",
                    "severity": "error",
                    "message": "x may be unbound",
                }
            ]
        },
        raw=RawResult(tool_name="ty"),
    )
    result = format_for_llm(
        {"ty": cfg}, CombinedToolResults(".", [tr]), cq_invocation=CQ
    )
    assert result == TY_DEFECT_SNAPSHOT


def test_bandit_defect_snapshot():
    """Test that bandit defects are correctly snapshotted."""
    cfg = ToolConfig(name="bandit", command="", parser_class=BanditParser, order=4)
    tr = ToolResult(
        metrics={"security": 0.5},
        details={
            "src/vuln.py": [
                {
                    "line": 5,
                    "code": "B101",
                    "severity": "HIGH",
                    "confidence": "HIGH",
                    "message": "Use of assert detected",
                }
            ]
        },
        raw=RawResult(tool_name="bandit"),
    )
    result = format_for_llm(
        {"bandit": cfg}, CombinedToolResults(".", [tr]), cq_invocation=CQ
    )
    assert result == BANDIT_DEFECT_SNAPSHOT


def test_coverage_defect_snapshot():
    """Test coverage defect snapshot."""
    cfg = ToolConfig(name="coverage", command="", parser_class=CoverageParser, order=6)
    tr = ToolResult(
        metrics={"coverage": 0.6},
        details={
            "src/low.py": [
                {"code": None, "line": None, "missing": 40, "file_coverage": 0.60}
            ]
        },
        raw=RawResult(tool_name="coverage"),
    )
    result = format_for_llm(
        {"coverage": cfg}, CombinedToolResults(".", [tr]), cq_invocation=CQ
    )
    assert result == COVERAGE_DEFECT_SNAPSHOT


def test_vulture_defect_snapshot():
    """Test for vulture defect snapshot."""
    cfg = ToolConfig(name="vulture", command="", parser_class=VultureParser, order=9)
    tr = ToolResult(
        metrics={"dead_code": 0.5},
        details={
            "src/dead.py": [
                {
                    "line": 10,
                    "type": "unused function",
                    "name": "old_helper",
                    "confidence": 80,
                }
            ]
        },
        raw=RawResult(tool_name="vulture"),
    )
    result = format_for_llm(
        {"vulture": cfg}, CombinedToolResults(".", [tr]), cq_invocation=CQ
    )
    assert result == VULTURE_DEFECT_SNAPSHOT


EXITCODE_DEFECT_SNAPSHOT = "error: command failed\n\nPlease fix only this issue."

HALSTEAD_BUG_DEFECT_SNAPSHOT = (
    "src/heavy.py has high estimated bug density (bugs: 2.500)\n\n"
    "Extract helper functions to reduce the function's size and scope.\n\n"
    "Please fix only this issue."
)

INTERROGATE_DEFECT_SNAPSHOT = (
    "src/undoc.py:5 - D103: missing docstring in function `some_func`\n\n"
    "Insert a docstring as the first statement in the body.\n\n"
    "Please fix only this issue."
)

LINECOUNT_DEFECT_SNAPSHOT = "violation: something wrong\n\nPlease fix only this issue."

REGEXCOUNT_DEFECT_SNAPSHOT = "match: error found here\n\nPlease fix only this issue."


def test_exitcode_defect_snapshot():
    """Test that exit code defect is correctly captured in the snapshot."""
    cfg = ToolConfig(name="mycheck", command="", parser_class=ExitCodeParser, order=1)
    tr = ToolResult(
        metrics={"exit_code": 0.0},
        raw=RawResult(tool_name="mycheck", stdout="error: command failed"),
    )
    result = format_for_llm(
        {"mycheck": cfg}, CombinedToolResults(".", [tr]), cq_invocation=CQ
    )
    assert result == EXITCODE_DEFECT_SNAPSHOT


def test_halstead_bug_defect_snapshot():
    """Test halstead bug defect snapshot."""
    cfg = ToolConfig(name="radon-hal", command="", parser_class=HalsteadParser, order=9)
    tr = ToolResult(
        metrics={"bug_free": 0.3},
        details={"src/heavy.py": {"bug_free": 0.3, "bugs": 2.5, "smallness": 0.8}},
        raw=RawResult(tool_name="radon-hal"),
    )
    result = format_for_llm(
        {"radon-hal": cfg}, CombinedToolResults(".", [tr]), cq_invocation=CQ
    )
    assert result == HALSTEAD_BUG_DEFECT_SNAPSHOT


def test_interrogate_defect_snapshot():
    """Test the interrogation of a defect snapshot."""
    cfg = ToolConfig(
        name="interrogate", command="", parser_class=InterrogateParser, order=11
    )
    tr = ToolResult(
        metrics={"doc_coverage": 0.6},
        details={
            "src/undoc.py": [
                {
                    "line": 5,
                    "code": "D103",
                    "message": "missing docstring in function `some_func`",
                }
            ]
        },
        raw=RawResult(tool_name="interrogate"),
    )
    result = format_for_llm(
        {"interrogate": cfg}, CombinedToolResults(".", [tr]), cq_invocation=CQ
    )
    assert result == INTERROGATE_DEFECT_SNAPSHOT


def test_linecount_defect_snapshot():
    """Test linecount defect snapshot."""
    cfg = ToolConfig(
        name="linecount", command="", parser_class=LineCountParser, order=10
    )
    tr = ToolResult(
        metrics={"violations": 0.5},
        details={"lines": ["violation: something wrong"]},
        raw=RawResult(tool_name="linecount"),
    )
    result = format_for_llm(
        {"linecount": cfg}, CombinedToolResults(".", [tr]), cq_invocation=CQ
    )
    assert result == LINECOUNT_DEFECT_SNAPSHOT


def test_regexcount_defect_snapshot():
    cfg = ToolConfig(
        name="regexcount", command="", parser_class=RegexCountParser, order=10
    )
    tr = ToolResult(
        metrics={"violations": 0.5},
        details={"count": 1, "matches": ["match: error found here"]},
        raw=RawResult(tool_name="regexcount"),
    )
    result = format_for_llm(
        {"regexcount": cfg}, CombinedToolResults(".", [tr]), cq_invocation=CQ
    )
    assert result == REGEXCOUNT_DEFECT_SNAPSHOT


COMPLEXITY_DEFECT_SNAPSHOT = (
    "**complexity** score: 0.600\n\nPlease fix only this issue."
)

MAINTAINABILITY_DEFECT_SNAPSHOT = (
    "**maintainability** score: 0.550\n\nPlease fix only this issue."
)


def test_complexity_defect_snapshot():
    cfg = ToolConfig(
        name="radon-cc", command="", parser_class=ComplexityParser, order=7
    )
    tr = ToolResult(
        metrics={"complexity": 0.6},
        raw=RawResult(tool_name="radon-cc"),
    )
    result = format_for_llm(
        {"radon-cc": cfg}, CombinedToolResults(".", [tr]), cq_invocation=CQ
    )
    assert result == COMPLEXITY_DEFECT_SNAPSHOT


def test_maintainability_defect_snapshot():
    cfg = ToolConfig(
        name="radon-mi", command="", parser_class=MaintainabilityParser, order=8
    )
    tr = ToolResult(
        metrics={"maintainability": 0.55},
        raw=RawResult(tool_name="radon-mi"),
    )
    result = format_for_llm(
        {"radon-mi": cfg}, CombinedToolResults(".", [tr]), cq_invocation=CQ
    )
    assert result == MAINTAINABILITY_DEFECT_SNAPSHOT


def test_pytest_defect_snapshot(tmp_path):
    """PytestParser snapshot: header, source body, failure excerpt, and footer all present."""
    test_file = tmp_path / "tests" / "test_foo.py"
    test_file.parent.mkdir()
    test_file.write_text("def test_bar():\n    assert 1 == 2\n")

    stdout = (
        "________ test_bar ________\n"
        "    assert 1 == 2\n"
        "E   AssertionError: assert 1 == 2\n"
        "short test summary info\n"
        f"FAILED {str(test_file).replace(chr(92), '/')}::test_bar\n"
    )
    cfg = ToolConfig(name="pytest", command="", parser_class=PytestParser, order=5)
    tr = ToolResult(
        metrics={"tests": 0.0},
        details={str(test_file): {"test_bar": "FAILED"}},
        raw=RawResult(tool_name="pytest", stdout=stdout),
    )
    result = format_for_llm(
        {"pytest": cfg}, CombinedToolResults(".", [tr]), cq_invocation=CQ
    )
    assert f"{str(test_file)}::test_bar" in result
    assert "test **FAILED**" in result
    assert "AssertionError" in result
    assert "Please fix only this issue" in result
