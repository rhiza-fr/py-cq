"""Tests for MaintainabilityParser."""

import json

from conftest import raw

from py_cq.parsers.maintainabilityparser import MaintainabilityParser

_NORMAL = json.dumps({
    "src/foo.py": {"mi": 73.0, "rank": "A"},
    "src\\bar.py": {"mi": 45.0, "rank": "C"},
})

_ERROR = json.dumps({
    "src/bad.py": {"error": "syntax error in file"},
})

_MIXED = json.dumps({
    "src/good.py": {"mi": 80.0, "rank": "A"},
    "src/bad.py": {"error": "oops"},
})


def test_maintainability_metric_present():
    """Test that the maintainability metric is present in the parsed output."""
    tr = MaintainabilityParser().parse(raw(_NORMAL))
    assert "maintainability" in tr.metrics
    assert 0.0 < tr.metrics["maintainability"] <= 1.0


def test_maintainability_details_structure():
    """Test that the maintainability details structure is correctly parsed."""
    tr = MaintainabilityParser().parse(raw(_NORMAL))
    tr = MaintainabilityParser().parse(raw(_NORMAL))
    assert "src/foo.py" in tr.details
    assert tr.details["src/foo.py"]["rank"] == "A"


def test_maintainability_normalizes_backslash():
    tr = MaintainabilityParser().parse(raw(_NORMAL))
    assert "src/bar.py" in tr.details
    assert "src\\bar.py" not in tr.details


def test_maintainability_error_file_recorded():
    tr = MaintainabilityParser().parse(raw(_ERROR))
    assert "src/bad.py" in tr.details
    assert tr.details["src/bad.py"]["rank"] == "F"
    assert tr.details["src/bad.py"]["mi"] == 0.0
    assert tr.details["src/bad.py"]["error"] == "syntax error in file"


def test_maintainability_error_file_not_counted_in_score():
    tr = MaintainabilityParser().parse(raw(_ERROR))
    assert tr.metrics["maintainability"] == 0.0


def test_maintainability_error_does_not_affect_good_file_score():
    tr_mixed = MaintainabilityParser().parse(raw(_MIXED))
    tr_good = MaintainabilityParser().parse(raw(
        json.dumps({"src/good.py": {"mi": 80.0, "rank": "A"}})
    ))
    assert tr_mixed.metrics["maintainability"] == tr_good.metrics["maintainability"]


def test_maintainability_empty():
    tr = MaintainabilityParser().parse(raw(json.dumps({})))
    assert tr.metrics["maintainability"] == 0.0
    assert tr.details == {}


def test_maintainability_higher_mi_higher_score():
    high = json.dumps({"f.py": {"mi": 90.0, "rank": "A"}})
    low = json.dumps({"f.py": {"mi": 20.0, "rank": "F"}})
    tr_high = MaintainabilityParser().parse(raw(high))
    tr_low = MaintainabilityParser().parse(raw(low))
    assert tr_high.metrics["maintainability"] > tr_low.metrics["maintainability"]


def test_maintainability_format_llm_message_uses_base_fallback():
    tr = MaintainabilityParser().parse(raw(_NORMAL))
    msg = MaintainabilityParser().format_llm_message(tr)
    assert isinstance(msg, str)
    assert len(msg) > 0


def test_maintainability_unknown_keys_skipped():
    """File entry with neither 'error' nor 'mi' is ignored — branch 54->47."""
    data = json.dumps({
        "src/foo.py": {"mi": 70.0, "rank": "B"},
        "src/weird.py": {"some_other_key": 42},
    })
    tr = MaintainabilityParser().parse(raw(data))
    assert "src/weird.py" not in tr.details
    assert "src/foo.py" in tr.details


def test_maintainability_non_dict_json_returns_zero():
    tr = MaintainabilityParser().parse(raw(json.dumps([1, 2, 3])))
    assert tr.metrics["maintainability"] == 0.0
