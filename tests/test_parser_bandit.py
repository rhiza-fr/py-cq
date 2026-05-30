"""Tests for BanditParser."""

import json

import pytest
from conftest import raw
from hypothesis import given
from hypothesis import strategies as st

from py_cq.localtypes import RawResult, ToolResult
from py_cq.parsers.banditparser import BanditParser, _SEVERITY_WEIGHT

_SEVERITIES = sorted(_SEVERITY_WEIGHT.keys())  # HIGH, LOW, MEDIUM
_CONFIDENCES = ["HIGH", "MEDIUM", "LOW"]

_issue_strategy = st.fixed_dictionaries({
    "filename": st.just("src/app.py"),
    "line_number": st.integers(min_value=1, max_value=9999),
    "test_id": st.sampled_from(["B101", "B105", "B301", "B311", "B506"]),
    "issue_severity": st.sampled_from(_SEVERITIES),
    "issue_confidence": st.sampled_from(_CONFIDENCES),
    "issue_text": st.text(max_size=80),
})


def _bandit_json(results):
    """Return bandit results as a JSON string."""
    return json.dumps({"results": results, "metrics": {"_totals": {}}})


def test_bandit_parse_clean():
    """Test bandit parser with clean input."""
    tr = BanditParser().parse(raw(_bandit_json([]), return_code=0))
    assert tr.metrics["security"] == 1.0
    assert tr.details == {}


def test_bandit_parse_low_issue():
    """Test bandit parser with a low severity issue."""
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


def test_bandit_invalid_json_returns_degraded_score():
    tr = BanditParser().parse(raw("not json", return_code=0))
    assert tr.metrics["security"] == 0.5


def test_bandit_non_dict_json_returns_degraded_score():
    tr = BanditParser().parse(raw("[]", return_code=0))
    assert tr.metrics["security"] == 0.5


def test_bandit_crash_returns_zero():
    """When bandit crashes (non-zero exit + non-JSON), score should be 0.0."""
    tr = BanditParser().parse(raw("not json", return_code=2))
    assert tr.metrics["security"] == 0.0


def test_bandit_skips_venv_paths():
    payload = _bandit_json([{
        "filename": "/project/.venv/lib/foo.py",
        "line_number": 1,
        "test_id": "B301",
        "issue_severity": "HIGH",
        "issue_confidence": "HIGH",
        "issue_text": "Dangerous",
    }])
    tr = BanditParser().parse(raw(payload, return_code=1))
    assert tr.details == {}


def test_bandit_skips_site_packages_paths():
    payload = _bandit_json([{
        "filename": "/usr/lib/python3/site-packages/foo.py",
        "line_number": 1,
        "test_id": "B301",
        "issue_severity": "HIGH",
        "issue_confidence": "HIGH",
        "issue_text": "Dangerous",
    }])
    tr = BanditParser().parse(raw(payload, return_code=1))
    assert tr.details == {}


def test_bandit_format_llm_no_details():
    tr = ToolResult(metrics={"security": 0.5}, details={}, raw=RawResult())
    assert "no details" in BanditParser().format_llm_message(tr).lower()


def test_bandit_mixed_severity_scores_lower_than_either_alone():
    """One LOW + one HIGH together score lower than each alone (more weighted issues = lower score)."""
    low_only = _bandit_json([{"filename": "a.py", "line_number": 1,
        "test_id": "B105", "issue_severity": "LOW", "issue_confidence": "HIGH", "issue_text": ""}])
    high_only = _bandit_json([{"filename": "a.py", "line_number": 1,
        "test_id": "B301", "issue_severity": "HIGH", "issue_confidence": "HIGH", "issue_text": ""}])
    mixed = _bandit_json([
        {"filename": "a.py", "line_number": 1,
         "test_id": "B105", "issue_severity": "LOW", "issue_confidence": "HIGH", "issue_text": ""},
        {"filename": "a.py", "line_number": 2,
         "test_id": "B301", "issue_severity": "HIGH", "issue_confidence": "HIGH", "issue_text": ""},
    ])
    low_score = BanditParser().parse(raw(low_only, return_code=1)).metrics["security"]
    high_score = BanditParser().parse(raw(high_only, return_code=1)).metrics["security"]
    mixed_score = BanditParser().parse(raw(mixed, return_code=1)).metrics["security"]
    # HIGH alone is worse than LOW alone (higher weight)
    assert high_score < low_score
    # Combined LOW+HIGH scores worse than HIGH alone (total weight is additive)
    assert mixed_score < high_score


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


# --- property-based tests ---

@given(st.lists(_issue_strategy, min_size=1, max_size=50))
def test_bandit_score_always_in_unit_interval(issues):
    """Score is always in [0.0, 1.0] regardless of severity/confidence mix."""
    payload = json.dumps({"results": issues})
    tr = BanditParser().parse(raw(payload, return_code=1))
    score = tr.metrics["security"]
    assert 0.0 <= score <= 1.0


@given(st.lists(_issue_strategy, min_size=1, max_size=30))
def test_bandit_adding_issue_never_improves_score(issues):
    """Appending any additional issue never raises the security score."""
    payload_before = json.dumps({"results": issues})
    extra = {
        "filename": "src/app.py", "line_number": 1, "test_id": "B101",
        "issue_severity": "HIGH", "issue_confidence": "HIGH", "issue_text": "x",
    }
    payload_after = json.dumps({"results": issues + [extra]})
    score_before = BanditParser().parse(raw(payload_before, return_code=1)).metrics["security"]
    score_after = BanditParser().parse(raw(payload_after, return_code=1)).metrics["security"]
    assert score_after <= score_before


@pytest.mark.parametrize("worse,better", [
    ("HIGH", "MEDIUM"),
    ("HIGH", "LOW"),
    ("MEDIUM", "LOW"),
])
def test_bandit_severity_ordering_single_issue(worse, better):
    """A single issue with higher severity scores strictly lower than lower severity."""
    def score_for(severity):
        payload = json.dumps({"results": [{
            "filename": "src/app.py", "line_number": 1, "test_id": "B101",
            "issue_severity": severity, "issue_confidence": "HIGH", "issue_text": "",
        }]})
        return BanditParser().parse(raw(payload, return_code=1)).metrics["security"]

    assert score_for(worse) < score_for(better)
