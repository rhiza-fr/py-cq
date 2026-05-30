"""Property tests: no parser may raise an exception on arbitrary text input."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from conftest import raw
from py_cq.localtypes import ToolResult
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


@given(st.text())
def test_bandit_parse_never_crashes(text):
    """Test that BanditParser().parse() never crashes given any text input."""
    tr = BanditParser().parse(raw(text))
    assert isinstance(tr, ToolResult)
    assert all(0.0 <= v <= 1.0 for v in tr.metrics.values())


@given(st.text())
def test_compile_parse_never_crashes(text):
    """Test that compiling and parsing never crashes."""
    tr = CompileParser().parse(raw(text))
    assert isinstance(tr, ToolResult)
    assert all(0.0 <= v <= 1.0 for v in tr.metrics.values())


@given(st.text())
def test_complexity_parse_never_crashes(text):
    """Test that the complexity parser never crashes on any text input."""
    tr = ComplexityParser().parse(raw(text))
    assert isinstance(tr, ToolResult)
    assert all(0.0 <= v <= 1.0 for v in tr.metrics.values())


@given(st.text())
def test_coverage_parse_never_crashes(text):
    """Test that coverage parsing never crashes on arbitrary text input."""
    tr = CoverageParser().parse(raw(text))
    assert isinstance(tr, ToolResult)
    assert all(0.0 <= v <= 1.0 for v in tr.metrics.values())


@given(st.text())
def test_exitcode_parse_never_crashes(text):
    """Ensure that parsing arbitrary text never crashes."""
    tr = ExitCodeParser().parse(raw(text))

    assert isinstance(tr, ToolResult)
    assert all(0.0 <= v <= 1.0 for v in tr.metrics.values())


@given(st.text())
def test_halstead_parse_never_crashes(text):
    """Test that the Halstead parser never crashes with any input text."""
    tr = HalsteadParser().parse(raw(text))
    assert isinstance(tr, ToolResult)
    assert all(0.0 <= v <= 1.0 for v in tr.metrics.values())


@given(st.text())
def test_interrogate_parse_never_crashes(text):
    tr = InterrogateParser().parse(raw(text))
    assert isinstance(tr, ToolResult)
    assert all(0.0 <= v <= 1.0 for v in tr.metrics.values())


@given(st.text())
def test_linecount_parse_never_crashes(text):
    tr = LineCountParser().parse(raw(text))
    assert isinstance(tr, ToolResult)
    assert all(0.0 <= v <= 1.0 for v in tr.metrics.values())


@given(st.text())
def test_maintainability_parse_never_crashes(text):
    tr = MaintainabilityParser().parse(raw(text))
    assert isinstance(tr, ToolResult)
    assert all(0.0 <= v <= 1.0 for v in tr.metrics.values())


@given(st.text())
def test_pytest_parse_never_crashes(text):
    tr = PytestParser().parse(raw(text))
    assert isinstance(tr, ToolResult)
    assert all(0.0 <= v <= 1.0 for v in tr.metrics.values())


@given(st.text())
def test_regexcount_parse_never_crashes(text):
    tr = RegexCountParser(parser_config={"pattern": ".*"}).parse(raw(text))
    assert isinstance(tr, ToolResult)
    assert all(0.0 <= v <= 1.0 for v in tr.metrics.values())


@given(st.text())
def test_ruff_parse_never_crashes(text):
    tr = RuffParser().parse(raw(text))
    assert isinstance(tr, ToolResult)
    assert all(0.0 <= v <= 1.0 for v in tr.metrics.values())


@given(st.text())
def test_ty_parse_never_crashes(text):
    tr = TyParser().parse(raw(text))
    assert isinstance(tr, ToolResult)
    assert all(0.0 <= v <= 1.0 for v in tr.metrics.values())


@given(st.text())
def test_vulture_parse_never_crashes(text):
    tr = VultureParser().parse(raw(text))
    assert isinstance(tr, ToolResult)
    assert all(0.0 <= v <= 1.0 for v in tr.metrics.values())


# --- Idempotency: parse(raw) == parse(raw) ---

@pytest.mark.parametrize("parser_cls,kwargs", [
    (BanditParser, {}),
    (CompileParser, {}),
    (ComplexityParser, {}),
    (CoverageParser, {}),
    (ExitCodeParser, {}),
    (HalsteadParser, {}),
    (InterrogateParser, {}),
    (LineCountParser, {}),
    (MaintainabilityParser, {}),
    (PytestParser, {}),
    (RegexCountParser, {"parser_config": {"pattern": ".*"}}),
    (RuffParser, {}),
    (TyParser, {}),
    (VultureParser, {}),
])
@given(st.text())
@settings(max_examples=30)
def test_parse_is_idempotent(parser_cls, kwargs, text):
    """Calling parse twice on the same RawResult produces identical metrics and detail keys."""
    raw_result = raw(text)
    parser = parser_cls(**kwargs)
    tr1 = parser.parse(raw_result)
    tr2 = parser.parse(raw_result)
    assert tr1.metrics == tr2.metrics
    assert set(tr1.details.keys()) == set(tr2.details.keys())
