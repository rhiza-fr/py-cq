"""Tests for BanditParser."""

import json

from conftest import raw

from py_cq.localtypes import RawResult, ToolResult
from py_cq.parsers.banditparser import BanditParser


def _bandit_json(results):
    return json.dumps({"results": results, "metrics": {"_totals": {}}})


def test_bandit_parse_clean():
    tr = BanditParser().parse(raw(_bandit_json([]), return_code=0))
    assert tr.metrics["security"] == 1.0
    assert tr.details == {}


def test_bandit_parse_low_issue():
    payload = _bandit_json([{
        "filename": "src/foo.py",
        "line_number": 10,
        "test_id": "B105",
        "issue_severity": "LOW",
        "issue_confidence": "MEDIUM",
        "issue_text": "Possible hardcoded password: ''",
    }])
    tr = BanditParser().parse(raw(payload, return_code=1))
    assert tr.metrics["security"] < 1.0
    assert "src/foo.py" in tr.details
    assert tr.details["src/foo.py"][0]["code"] == "B105"
    assert tr.details["src/foo.py"][0]["severity"] == "LOW"


def test_bandit_high_severity_scores_lower_than_low():
    low_payload = _bandit_json([{"filename": "a.py", "line_number": 1,
        "test_id": "B105", "issue_severity": "LOW", "issue_confidence": "HIGH", "issue_text": ""}])
    high_payload = _bandit_json([{"filename": "a.py", "line_number": 1,
        "test_id": "B301", "issue_severity": "HIGH", "issue_confidence": "HIGH", "issue_text": ""}])
    low_tr = BanditParser().parse(raw(low_payload, return_code=1))
    high_tr = BanditParser().parse(raw(high_payload, return_code=1))
    assert high_tr.metrics["security"] < low_tr.metrics["security"]


def test_bandit_invalid_json_returns_perfect_score():
    tr = BanditParser().parse(raw("not json", return_code=0))
    assert tr.metrics["security"] == 1.0


def test_bandit_format_llm_no_details():
    tr = ToolResult(metrics={"security": 0.5}, details={}, raw=RawResult())
    assert "no details" in BanditParser().format_llm_message(tr).lower()


def test_bandit_format_llm_with_issue():
    tr = ToolResult(
        metrics={"security": 0.5},
        details={"src/foo.py": [{"line": 42, "code": "B301", "severity": "HIGH", "confidence": "HIGH", "message": "Use of pickle"}]},
        raw=RawResult(),
    )
    msg = BanditParser().format_llm_message(tr)
    assert "src/foo.py:42" in msg
    assert "B301" in msg
    assert "HIGH" in msg
