"""Tests for storage.save_result."""

import json

from py_cq.localtypes import CombinedToolResults, RawResult, ToolResult
from py_cq.storage import save_result


def _combined(path="test.py", tool_results=None):
    return CombinedToolResults(path=path, tool_results=tool_results or [])


def test_save_result_writes_json(tmp_path):
    out = tmp_path / "results.json"
    save_result(_combined(), str(out))
    data = json.loads(out.read_text())
    assert "score" in data
    assert "path" in data


def test_save_result_empty_filename_is_noop():
    save_result(_combined(), "")  # must not raise


def test_save_result_content_path_and_score(tmp_path):
    out = tmp_path / "out.json"
    save_result(_combined(path="myproject/"), str(out))
    data = json.loads(out.read_text())
    assert data["path"] == "myproject/"


def test_save_result_includes_tool_metrics(tmp_path):
    out = tmp_path / "out.json"
    combined = CombinedToolResults(
        path=".",
        tool_results=[ToolResult(metrics={"lint": 0.9}, raw=RawResult(tool_name="ruff"))],
    )
    save_result(combined, str(out))
    data = json.loads(out.read_text())
    assert len(data["metrics"]) == 1
    assert data["metrics"][0]["metrics"]["lint"] == 0.9
