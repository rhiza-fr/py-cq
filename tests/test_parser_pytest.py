"""Tests for PytestParser."""

from conftest import raw

from py_cq.parsers.pytestparser import PytestParser

PYTEST_OUTPUT = """\
tests/test_foo.py::test_one PASSED    [ 50%]
tests/test_foo.py::test_two FAILED    [100%]
"""

PYTEST_NO_TESTS = "no tests ran"


def test_pytest_parse_mixed():
    tr = PytestParser().parse(raw(PYTEST_OUTPUT, return_code=1))
    assert tr.metrics["tests"] == 0.5
    assert "tests/test_foo.py" in tr.details
    assert tr.details["tests/test_foo.py"]["test_one"] == "PASSED"
    assert tr.details["tests/test_foo.py"]["test_two"] == "FAILED"


def test_pytest_parse_all_pass():
    tr = PytestParser().parse(raw("tests/test_foo.py::test_one PASSED    [100%]\n", return_code=0))
    assert tr.metrics["tests"] == 1.0


def test_pytest_parse_no_tests():
    tr = PytestParser().parse(raw(PYTEST_NO_TESTS))
    assert tr.metrics == {}


def test_pytest_parse_empty():
    tr = PytestParser().parse(raw(""))
    assert tr.metrics["tests"] == 0
