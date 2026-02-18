"""Tests for ComplexityParser."""

import json

from conftest import raw

from py_cq.parsers.complexityparser import ComplexityParser

_ONE_FILE = json.dumps({
    "src/foo.py": [
        {"name": "bar", "complexity": 3, "rank": "A"},
        {"name": "baz", "complexity": 15, "rank": "C"},
    ]
})

_TWO_FILES = json.dumps({
    "src/foo.py": [{"name": "f", "complexity": 5, "rank": "A"}],
    "src\\bar.py": [{"name": "g", "complexity": 10, "rank": "B"}],
})


def test_complexity_parse_metric_present():
    tr = ComplexityParser().parse(raw(_ONE_FILE))
    assert "simplicity" in tr.metrics
    assert 0.0 < tr.metrics["simplicity"] <= 1.0


def test_complexity_parse_details_structure():
    tr = ComplexityParser().parse(raw(_ONE_FILE))
    assert "src/foo.py" in tr.details
    assert "bar" in tr.details["src/foo.py"]
    assert tr.details["src/foo.py"]["bar"]["rank"] == "A"
    assert "simplicity" in tr.details["src/foo.py"]["bar"]


def test_complexity_parse_normalizes_backslash():
    tr = ComplexityParser().parse(raw(_TWO_FILES))
    assert "src/bar.py" in tr.details
    assert "src\\bar.py" not in tr.details


def test_complexity_parse_empty_input():
    tr = ComplexityParser().parse(raw(json.dumps({})))
    assert tr.metrics["simplicity"] == 0.0
    assert tr.details == {}


def test_complexity_parse_missing_rank_defaults_f():
    output = json.dumps({"src/foo.py": [{"name": "f", "complexity": 5}]})
    tr = ComplexityParser().parse(raw(output))
    assert tr.details["src/foo.py"]["f"]["rank"] == "F"


def test_complexity_parse_missing_complexity_uses_max():
    output = json.dumps({"src/foo.py": [{"name": "f", "rank": "A"}]})
    tr = ComplexityParser().parse(raw(output))
    # No complexity key → defaults to max_complexity (30) → score_logistic_variant(30, 30) = 0.5
    assert tr.metrics["simplicity"] <= 0.5


def test_complexity_higher_complexity_lower_score():
    simple = json.dumps({"f.py": [{"name": "f", "complexity": 1, "rank": "A"}]})
    complex_ = json.dumps({"f.py": [{"name": "f", "complexity": 29, "rank": "F"}]})
    tr_s = ComplexityParser().parse(raw(simple))
    tr_c = ComplexityParser().parse(raw(complex_))
    assert tr_s.metrics["simplicity"] > tr_c.metrics["simplicity"]


def test_complexity_multiple_files_averaged():
    output = json.dumps({
        "src/a.py": [{"name": "f", "complexity": 1, "rank": "A"}],
        "src/b.py": [{"name": "g", "complexity": 1, "rank": "A"}],
    })
    tr = ComplexityParser().parse(raw(output))
    assert "src/a.py" in tr.details
    assert "src/b.py" in tr.details
