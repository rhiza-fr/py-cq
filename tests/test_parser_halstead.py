"""Tests for HalsteadParser."""

import json

from conftest import raw
from py_cq.parsers.halsteadparser import HalsteadParser


# --- parse ---

def test_parse_with_error_key():
    """Files with an 'error' key should set all min scores to 0."""
    data = {
        "src/bad.py": {
            "error": "syntax error"
        }
    }
    tr = HalsteadParser().parse(raw(stdout=json.dumps(data)))
    assert tr.metrics["file_bug_free"] == 0.0
    assert tr.metrics["file_smallness"] == 0.0
    assert tr.metrics["functions_bug_free"] == 0.0
    assert tr.metrics["functions_smallness"] == 0.0
    assert tr.details["src/bad.py"]["error"] == "syntax error"


def test_parse_file_with_total_and_functions():
    data = {
        "src/foo.py": {
            "total": {"bugs": 0.05, "volume": 100.0},
            "functions": {
                "helper": {"bugs": 0.01, "volume": 50.0}
            }
        }
    }
    tr = HalsteadParser().parse(raw(stdout=json.dumps(data)))
    assert "file_bug_free" in tr.metrics
    assert "functions_bug_free" in tr.metrics
    assert tr.details["src/foo.py"]["bugs"] == 0.05
    assert tr.details["src/foo.py"]["volume"] == 100.0
    assert "helper" in tr.details["src/foo.py"]["functions"]


def test_parse_backslash_path_normalized():
    """Windows-style backslash paths should be normalized to forward slashes."""
    data = {".\\src\\foo.py": {"total": {"bugs": 0.0, "volume": 10.0}, "functions": {}}}
    tr = HalsteadParser().parse(raw(stdout=json.dumps(data)))
    assert "./src/foo.py" in tr.details


# --- format_llm_message: functions_smallness ---

def _tr_with_metrics(metrics, details):
    from py_cq.localtypes import RawResult, ToolResult
    return ToolResult(metrics=metrics, details=details, raw=RawResult(tool_name="radon hal"))


def test_format_llm_message_functions_smallness():
    """functions_smallness as worst metric should find the worst function by smallness."""
    tr = _tr_with_metrics(
        metrics={
            "file_bug_free": 0.9,
            "file_smallness": 0.9,
            "functions_bug_free": 0.9,
            "functions_smallness": 0.2,  # worst metric
        },
        details={
            "src/foo.py": {
                "bug_free": 0.9, "smallness": 0.9, "bugs": 0.01, "volume": 100,
                "functions": {
                    "big_fn": {"no_bugs": 0.9, "smallness": 0.2, "bugs": 0.01, "volume": 550},
                    "small_fn": {"no_bugs": 0.9, "smallness": 0.95, "bugs": 0.001, "volume": 20},
                },
            }
        },
    )
    msg = HalsteadParser().format_llm_message(tr)
    assert "src/foo.py" in msg
    assert "big_fn" in msg
    assert "550" in msg
    assert "split" in msg.lower() or "large" in msg.lower()


def test_format_llm_message_worst_bugs_is_none():
    """When bug details are missing, format still works."""
    tr = _tr_with_metrics(
        metrics={"file_bug_free": 0.3, "file_smallness": 0.9,
                 "functions_bug_free": 0.9, "functions_smallness": 0.9},
        details={
            "src/foo.py": {
                "bug_free": 0.3,
                "smallness": 0.9,
                # no 'bugs' or 'volume' keys
                "functions": {},
            }
        },
    )
    msg = HalsteadParser().format_llm_message(tr)
    assert "src/foo.py" in msg


def test_format_llm_message_worst_volume_is_none():
    """When volume details are missing, format still works."""
    tr = _tr_with_metrics(
        metrics={"file_bug_free": 0.9, "file_smallness": 0.2,
                 "functions_bug_free": 0.9, "functions_smallness": 0.9},
        details={
            "src/foo.py": {
                "bug_free": 0.9,
                "smallness": 0.2,
                # no 'bugs' or 'volume' keys
                "functions": {},
            }
        },
    )
    msg = HalsteadParser().format_llm_message(tr)
    assert "src/foo.py" in msg
