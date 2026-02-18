"""Tests for localtypes dataclasses and AbstractParser base class."""

from py_cq import hello
from py_cq.localtypes import AbstractParser, CombinedToolResults, RawResult, ToolResult


class MinimalParser(AbstractParser):
    def parse(self, raw_result): return ToolResult()


def test_hello():
    assert hello() == "Hello from py_cq!"


def test_raw_result_to_dict():
    r = RawResult(tool_name="ruff", command="ruff check .", stdout="out", stderr="err", return_code=1)
    d = r.to_dict()
    assert d["tool_name"] == "ruff"
    assert d["stdout"] == "out"
    assert d["return_code"] == 1


def test_tool_result_to_dict():
    tr = ToolResult(metrics={"lint": 0.9}, details={"f.py": []})
    d = tr.to_dict()
    assert d["metrics"] == {"lint": 0.9}
    assert "raw" in d


def test_tool_result_post_init_coerces_non_dict():
    tr = ToolResult.__new__(ToolResult)
    tr.metrics = "bad"
    tr.details = None
    tr.raw = RawResult()
    tr.__post_init__()
    assert tr.details == {}
    assert tr.metrics == {}


def test_combined_to_dict():
    tr = ToolResult(metrics={"lint": 0.8})
    c = CombinedToolResults(path="src/", tool_results=[tr])
    d = c.to_dict()
    assert d["path"] == "src/"
    assert "score" in d
    assert len(d["metrics"]) == 1


def test_abstract_format_llm_message_no_metrics():
    tr = ToolResult(metrics={})
    assert MinimalParser().format_llm_message(tr) == "No details available"


def test_abstract_parse_body_via_super():
    # Calls the abstract method body (pass) via super() to cover localtypes.py:129
    class SuperCaller(AbstractParser):
        def parse(self, raw_result):
            return super().parse(raw_result)
    assert SuperCaller().parse(RawResult()) is None
