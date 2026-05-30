"""Hypothesis tests: format_llm_message never raises for any plausible ToolResult shape.

For each parser, we generate ToolResult instances with plausible-but-noisy
details dicts (missing keys, wrong value types, empty collections) and assert
that format_llm_message returns a string without raising.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from py_cq.localtypes import RawResult, ToolResult
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

# --- shared low-level strategies ---

_safe_float = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
_safe_int = st.integers(min_value=0, max_value=9999)
_short_text = st.text(max_size=30)

_metrics = st.dictionaries(
    st.text(min_size=1, max_size=20),
    _safe_float,
    min_size=0,
    max_size=5,
)

_raw = st.builds(
    RawResult,
    tool_name=_short_text,
    stdout=st.text(max_size=200),
    stderr=st.text(max_size=100),
    return_code=st.integers(min_value=0, max_value=5),
)

# An issue dict with optionally missing keys and possibly wrong types
_issue_dict = st.fixed_dictionaries(
    {},
    optional={
        "line": st.one_of(_safe_int, st.text(max_size=5)),
        "code": st.text(max_size=10),
        "message": st.text(max_size=50),
        "severity": st.text(max_size=10),
        "confidence": st.one_of(st.integers(0, 100), st.text(max_size=5)),
        "name": st.text(max_size=20),
        "type": st.text(max_size=20),
    },
)

# File-mapped issue list — includes empty list (robustness test) and wrong types
_issues_value = st.one_of(
    st.just([]),
    st.lists(_issue_dict, min_size=1, max_size=3),
    st.text(max_size=10),
    st.none(),
)

_file_issues_details = st.dictionaries(
    st.text(min_size=1, max_size=30),
    _issues_value,
    max_size=3,
)


# --- non-dict issue item guard (covers `if not isinstance(issue, dict)` branch) ---

@pytest.mark.parametrize("parser_cls,non_dict_issue", [
    (BanditParser, "string-issue"),
    (RuffParser, 42),
    (TyParser, ["nested", "list"]),
    (VultureParser, "string-issue"),
])
def test_non_dict_issue_returns_no_details(parser_cls, non_dict_issue):
    """Test that non-dict issues return no details."""
    tr = ToolResult(metrics={}, details={"src/foo.py": [non_dict_issue]})
    msg = parser_cls().format_llm_message(tr)
    assert "no details" in msg.lower()


# --- parsers with {file: [issue_dict]} details ---

@given(_file_issues_details, _metrics, _raw)
@settings(max_examples=50)
def test_bandit_format_never_raises(details, metrics, raw):
    """Test that BanditParser.format_llm_message never raises an exception."""
    tr = ToolResult(metrics=metrics, details=details, raw=raw)
    assert isinstance(BanditParser().format_llm_message(tr), str)


@given(_file_issues_details, _metrics, _raw)
@settings(max_examples=50)
def test_ruff_format_never_raises(details, metrics, raw):
    """Test that RuffParser.format_llm_message never raises an error."""
    tr = ToolResult(metrics=metrics, details=details, raw=raw)
    assert isinstance(RuffParser().format_llm_message(tr), str)


@given(_file_issues_details, _metrics, _raw)
@settings(max_examples=50)
def test_ty_format_never_raises(details, metrics, raw):
    """Test that ty_format never raises an exception."""
    tr = ToolResult(metrics=metrics, details=details, raw=raw)
    assert isinstance(TyParser().format_llm_message(tr), str)


@given(_file_issues_details, _metrics, _raw)
@settings(max_examples=50)
def test_vulture_format_never_raises(details, metrics, raw):
    """Test that VultureParser.format_llm_message never raises an exception."""
    tr = ToolResult(metrics=metrics, details=details, raw=raw)
    assert isinstance(VultureParser().format_llm_message(tr), str)


# --- CoverageParser: {file: [{code, line, signature, file_coverage, missing, ...}]} ---

_cov_issue = st.fixed_dictionaries(
    {},
    optional={
        "code": st.one_of(st.none(), st.text(max_size=20)),
        "line": st.one_of(st.none(), st.integers(min_value=1, max_value=9999)),
        "signature": st.one_of(st.none(), st.text(max_size=100)),
        "file_coverage": _safe_float,
        "missing": st.one_of(st.integers(min_value=0, max_value=1000), st.none()),
        "missing_lines": st.one_of(st.none(), st.text(max_size=50)),
    },
)
_cov_details = st.dictionaries(
    st.text(min_size=1),
    st.one_of(st.lists(_cov_issue, max_size=3), st.text(max_size=5), st.integers()),
    max_size=3,
)


@given(_cov_details, _metrics)
@settings(max_examples=50)
def test_coverage_format_never_raises(details, metrics):
    """Test that CoverageParser.format_llm_message never raises an error."""
    tr = ToolResult(metrics=metrics, details=details)
    assert isinstance(CoverageParser().format_llm_message(tr), str)


# --- InterrogateParser: {file: {total, missing, coverage}} ---

_interrogate_file_data = st.one_of(
    st.fixed_dictionaries(
        {},
        optional={
            "total": st.integers(min_value=0, max_value=100),
            "missing": st.integers(min_value=0, max_value=50),
            "coverage": _safe_float,
        },
    ),
    st.text(max_size=5),
)
_interrogate_details = st.dictionaries(st.text(min_size=1), _interrogate_file_data, max_size=3)


@given(_interrogate_details, _metrics)
@settings(max_examples=50)
def test_interrogate_format_never_raises(details, metrics):
    """Test that InterrogateParser.format_llm_message never raises an exception for various inputs."""
    tr = ToolResult(metrics=metrics, details=details)
    assert isinstance(InterrogateParser().format_llm_message(tr), str)


# --- HalsteadParser: {file: {bug_free, smallness, bugs, volume, functions: {fn: {...}}}} ---

_halstead_fn = st.fixed_dictionaries(
    {},
    optional={
        "no_bugs": _safe_float,
        "smallness": _safe_float,
        "bugs": _safe_float,
        "volume": st.floats(min_value=0.0, max_value=2000.0, allow_nan=False),
    },
)
_halstead_file = st.fixed_dictionaries(
    {},
    optional={
        "bug_free": _safe_float,
        "smallness": _safe_float,
        "bugs": _safe_float,
        "volume": st.floats(min_value=0.0, allow_nan=False, allow_infinity=False, max_value=5000.0),
        "functions": st.dictionaries(st.text(min_size=1, max_size=20), _halstead_fn, max_size=3),
    },
)
_halstead_details = st.dictionaries(st.text(min_size=1), _halstead_file, max_size=3)
_halstead_metrics = st.fixed_dictionaries(
    {},
    optional={
        "file_bug_free": _safe_float,
        "file_smallness": _safe_float,
        "functions_bug_free": _safe_float,
        "functions_smallness": _safe_float,
    },
)


@given(_halstead_details, _halstead_metrics)
@settings(max_examples=50)
def test_halstead_format_never_raises(details, metrics):
    tr = ToolResult(metrics=metrics, details=details)
    assert isinstance(HalsteadParser().format_llm_message(tr), str)


# --- CompileParser: {failed_files: {file: {line, src, type, help}}} ---

_compile_file_info = st.fixed_dictionaries(
    {},
    optional={
        "line": st.one_of(st.integers(min_value=1, max_value=9999), st.text(max_size=5)),
        "src": st.text(max_size=50),
        "type": st.text(max_size=20),
        "help": st.text(max_size=50),
    },
)
_compile_details = st.fixed_dictionaries(
    {},
    optional={
        "failed_files": st.one_of(
            st.just({}),
            st.dictionaries(st.text(min_size=1), _compile_file_info, max_size=3),
        ),
    },
)


@given(_compile_details, _metrics)
@settings(max_examples=50)
def test_compile_format_never_raises(details, metrics):
    tr = ToolResult(metrics=metrics, details=details)
    assert isinstance(CompileParser().format_llm_message(tr), str)


# --- PytestParser: {file: {test_name: status}} + needs raw.stdout ---

_pytest_status = st.one_of(
    st.sampled_from(["PASSED", "FAILED", "ERROR", "SKIPPED"]),
    st.text(max_size=10),
    st.none(),
    st.integers(),
)
_pytest_file_tests = st.one_of(
    st.just({}),
    st.dictionaries(st.text(min_size=1, max_size=20), _pytest_status, min_size=0, max_size=3),
    st.text(max_size=5),
)
_pytest_details = st.dictionaries(st.text(min_size=1), _pytest_file_tests, max_size=3)


@given(_pytest_details, _raw)
@settings(max_examples=50)
def test_pytest_format_never_raises(details, raw):
    tr = ToolResult(metrics={"tests": 0.5}, details=details, raw=raw)
    assert isinstance(PytestParser().format_llm_message(tr), str)


# --- ExitCodeParser: uses raw.stdout/stderr ---

@given(_raw)
@settings(max_examples=30)
def test_exitcode_format_never_raises(raw):
    tr = ToolResult(metrics={"exit_code": 0.0}, details={}, raw=raw)
    assert isinstance(ExitCodeParser().format_llm_message(tr), str)


# --- LineCountParser: {lines: [str]} ---

_linecount_details = st.fixed_dictionaries(
    {},
    optional={"lines": st.lists(st.text(max_size=50), max_size=5)},
)


@given(_linecount_details, _metrics)
@settings(max_examples=30)
def test_linecount_format_never_raises(details, metrics):
    tr = ToolResult(metrics=metrics, details=details)
    assert isinstance(LineCountParser().format_llm_message(tr), str)


# --- RegexCountParser: {count: int, matches: [str]} ---

_regex_details = st.fixed_dictionaries(
    {},
    optional={
        "count": st.integers(min_value=0, max_value=100),
        "matches": st.lists(st.text(max_size=50), max_size=5),
    },
)


@given(_regex_details, _metrics)
@settings(max_examples=30)
def test_regexcount_format_never_raises(details, metrics):
    tr = ToolResult(metrics=metrics, details=details)
    assert isinstance(RegexCountParser(parser_config={"pattern": ".*"}).format_llm_message(tr), str)


# --- ComplexityParser: uses AbstractParser default (reads metrics only) ---

@given(_metrics)
@settings(max_examples=30)
def test_complexity_format_never_raises(metrics):
    tr = ToolResult(metrics=metrics, details={})
    assert isinstance(ComplexityParser().format_llm_message(tr), str)


# --- MaintainabilityParser: uses AbstractParser default ---

@given(_metrics)
@settings(max_examples=30)
def test_maintainability_format_never_raises(metrics):
    tr = ToolResult(metrics=metrics, details={})
    assert isinstance(MaintainabilityParser().format_llm_message(tr), str)
