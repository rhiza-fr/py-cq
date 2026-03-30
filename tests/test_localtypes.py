"""Tests for localtypes dataclasses and AbstractParser base class."""

from py_cq.localtypes import AbstractParser, CombinedToolResults, RawResult, ToolResult
from py_cq.metric_aggregator import aggregate_metrics


class MinimalParser(AbstractParser):
    def parse(self, raw_result): return ToolResult()


def test_raw_result_to_dict():
    r = RawResult(tool_name="ruff", command="ruff check .", stdout="out", stderr="err", return_code=1)
    d = r.to_dict()
    assert d["tool_name"] == "ruff"
    assert d["stdout"] == "out"
    assert d["return_code"] == 1


def test_tool_result_to_dict():
    tr = ToolResult(metrics={"lint": 0.9}, details={"f.py": []}, raw=RawResult(tool_name="ruff"))
    d = tr.to_dict()
    assert d["tool_name"] == "ruff"
    assert d["metrics"] == {"lint": 0.9}
    assert "raw" not in d


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


def test_aggregate_metrics_returns_combined():
    tr = ToolResult(metrics={"score": 0.9}, raw=RawResult(tool_name="ruff"))
    result = aggregate_metrics("myproject", [tr])
    assert isinstance(result, CombinedToolResults)
    assert result.path == "myproject"
    assert len(result.tool_results) == 1


def test_aggregate_metrics_empty():
    result = aggregate_metrics(".", [])
    assert result.score == 0.0


def test_toolconfig_parser_config_defaults_to_empty_dict():
    from py_cq.localtypes import ToolConfig
    tc = ToolConfig(name="x", command="cmd", parser_class=object)
    assert tc.parser_config == {}


def test_abstract_parser_stores_parser_config():
    from py_cq.localtypes import AbstractParser, RawResult, ToolResult

    class MyParser(AbstractParser):
        def parse(self, raw_result: RawResult) -> ToolResult:
            return ToolResult()

    p = MyParser({"scale_factor": 10})
    assert p.parser_config == {"scale_factor": 10}


def test_abstract_parser_defaults_config_to_empty():
    from py_cq.localtypes import AbstractParser, RawResult, ToolResult

    class MyParser(AbstractParser):
        def parse(self, raw_result: RawResult) -> ToolResult:
            return ToolResult()

    p = MyParser()
    assert p.parser_config == {}
