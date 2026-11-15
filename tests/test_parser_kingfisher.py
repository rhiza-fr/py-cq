"""Tests for KingfisherParser."""

import json

from conftest import raw

from py_cq.localtypes import RawResult, ToolResult
from py_cq.parsers.kingfisherparser import KingfisherParser


def _finding(path, line, rule_id="betterleaks.github-pat", confidence="high"):
    return {
        "rule": {
            "id": rule_id,
            "name": rule_id.split(".")[-1],
            "description": "Uncovered a GitHub Personal Access Token.",
        },
        "finding": {
            "snippet": "[REDACTED:ee12f76d]",
            "confidence": confidence,
            "line": line,
            "path": path,
        },
    }


def _report(*findings):
    return json.dumps({"findings": list(findings), "metadata": {}})


def test_kingfisher_parse_clean():
    """No findings scores 1.0 with no details."""
    tr = KingfisherParser().parse(raw(_report()))
    assert tr.metrics == {"secrets": 1.0}
    assert tr.details == {}


def test_kingfisher_parse_finding():
    """A finding lowers the score and is listed against its file."""
    tr = KingfisherParser().parse(
        raw(_report(_finding("C:\\proj\\cfg.py", 3)), return_code=200)
    )
    assert tr.metrics["secrets"] < 1.0
    assert tr.details == {
        "C:/proj/cfg.py": [
            {
                "line": 3,
                "code": "betterleaks.github-pat",
                "confidence": "high",
                "message": "Uncovered a GitHub Personal Access Token.",
            }
        ]
    }


def test_kingfisher_more_findings_lower_score():
    one = KingfisherParser().parse(raw(_report(_finding("a.py", 1))))
    two = KingfisherParser().parse(
        raw(_report(_finding("a.py", 1), _finding("b.py", 2)))
    )
    assert two.metrics["secrets"] < one.metrics["secrets"]


def test_kingfisher_not_installed_gives_no_metric():
    """kingfisher missing from PATH is skipped, not failed."""
    result = RawResult(
        tool_name="kingfisher",
        stdout="",
        stderr="'kingfisher' is not recognized as an internal or external command",
        return_code=1,
    )
    tr = KingfisherParser().parse(result)
    assert tr.metrics == {}
    assert tr.details == {}


def test_kingfisher_unexpected_json_gives_no_metric():
    assert KingfisherParser().parse(raw("[]")).metrics == {}
    assert KingfisherParser().parse(raw("{}")).metrics == {}


def test_kingfisher_format_llm_with_finding(tmp_path):
    """The message names file, line and rule but never shows the source line."""
    src = tmp_path / "cfg.py"
    src.write_text("TOKEN = 'plaintext-secret-value'\n")
    tr = KingfisherParser().parse(raw(_report(_finding(str(src), 1))))
    msg = KingfisherParser().format_llm_message(tr)
    assert f"{src.as_posix()}:1 - betterleaks.github-pat" in msg
    assert "[high confidence]" in msg
    assert "kingfisher:ignore" in msg
    assert "plaintext-secret-value" not in msg


def test_kingfisher_format_llm_no_details():
    tr = ToolResult(metrics={"secrets": 0.5}, details={}, raw=RawResult())
    assert "no details" in KingfisherParser().format_llm_message(tr).lower()
