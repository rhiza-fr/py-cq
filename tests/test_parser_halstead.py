"""Tests for HalsteadParser."""

import json

from conftest import raw
from py_cq.parsers.halsteadparser import HalsteadParser


# --- parse ---

def test_halstead_invalid_json_returns_perfect_score():
    tr = HalsteadParser().parse(raw("not-valid-json{{{"))
    assert tr.metrics == {
        "file_bug_free": 1.0, "file_smallness": 1.0,
        "functions_bug_free": 1.0, "functions_smallness": 1.0,
    }


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


def test_parse_total_only_no_functions():
    """A file with 'total' but empty 'functions' should not crash; function metrics default to 1.0."""
    data = {
        "src/foo.py": {
            "total": {"bugs": 0.5, "volume": 300.0},
            "functions": {}
        }
    }
    tr = HalsteadParser().parse(raw(stdout=json.dumps(data)))
    assert tr.metrics["functions_bug_free"] == 1.0
    assert tr.metrics["functions_smallness"] == 1.0
    assert "src/foo.py" in tr.details


def test_format_llm_message_tie_in_function_smallness():
    """Two functions with identical smallness scores should not raise."""
    tr = _tr_with_metrics(
        metrics={
            "file_bug_free": 0.9,
            "file_smallness": 0.9,
            "functions_bug_free": 0.9,
            "functions_smallness": 0.3,
        },
        details={
            "src/foo.py": {
                "bug_free": 0.9, "smallness": 0.9, "bugs": 0.01, "volume": 100,
                "functions": {
                    "fn_a": {"no_bugs": 0.9, "smallness": 0.3, "bugs": 0.01, "volume": 400},
                    "fn_b": {"no_bugs": 0.9, "smallness": 0.3, "bugs": 0.01, "volume": 400},
                },
            }
        },
    )
    msg = HalsteadParser().format_llm_message(tr)
    assert "src/foo.py" in msg


def test_parse_duplicate_file_key():
    """Duplicate file key (after backslash normalization) reuses existing entry — branch 73->79."""
    data = {
        "src/foo.py": {"total": {"bugs": 0.05, "volume": 100.0}, "functions": {}},
        "src\\foo.py": {"total": {"bugs": 0.10, "volume": 200.0}, "functions": {}},
    }
    tr = HalsteadParser().parse(raw(stdout=json.dumps(data)))
    assert "src/foo.py" in tr.details
    # Second entry overwrites total values (same key reused)
    assert tr.details["src/foo.py"]["volume"] == 200.0


def test_extract_bugs_and_volume_zero_values():
    """extract_bugs_and_volume with bugs=0, volume=0 returns scores in [0, 1]."""
    parser = HalsteadParser()
    no_bugs_score, smallness_score = parser.extract_bugs_and_volume(
        {"bugs": 0, "volume": 0}, max_bugs=1.0, max_volume=1000.0
    )
    assert 0.0 <= no_bugs_score <= 1.0
    assert 0.0 <= smallness_score <= 1.0


def test_extract_bugs_and_volume_max_values():
    """extract_bugs_and_volume with bugs=max, volume=max returns scores in [0, 1]."""
    parser = HalsteadParser()
    no_bugs_score, smallness_score = parser.extract_bugs_and_volume(
        {"bugs": 1.0, "volume": 1000.0}, max_bugs=1.0, max_volume=1000.0
    )
    assert 0.0 <= no_bugs_score <= 1.0
    assert 0.0 <= smallness_score <= 1.0


def test_parse_json_array_returns_perfect_score():
    """Parsed JSON that is not a dict (e.g. an array) should return perfect scores."""
    tr = HalsteadParser().parse(raw(stdout="[]"))
    assert tr.metrics == {
        "file_bug_free": 1.0, "file_smallness": 1.0,
        "functions_bug_free": 1.0, "functions_smallness": 1.0,
    }


def test_format_llm_message_second_file_not_worse():
    """Second file has higher score than first — branch 143->131 (s >= worst_score, no update)."""
    tr = _tr_with_metrics(
        metrics={"file_bug_free": 0.3, "file_smallness": 0.9,
                 "functions_bug_free": 0.9, "functions_smallness": 0.9},
        details={
            "src/bad.py": {"bug_free": 0.3, "smallness": 0.9, "bugs": 0.1, "volume": 500, "functions": {}},
            "src/good.py": {"bug_free": 0.8, "smallness": 0.9, "bugs": 0.01, "volume": 50, "functions": {}},
        },
    )
    msg = HalsteadParser().format_llm_message(tr)
    assert "src/bad.py" in msg
