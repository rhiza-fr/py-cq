"""Tests for PytestParser."""

import pytest
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


def test_pytest_deselected_summary_only():
    """Summary line only (no verbose lines) with deselected tests should report pass rate from summary."""
    stdout = "256 passed, 13 deselected in 16.83s"
    tr = PytestParser().parse(raw(stdout, return_code=0))
    assert tr.metrics["tests"] == 1.0


def test_pytest_deselected_with_failures_summary_only():
    stdout = "254 passed, 2 failed, 13 deselected in 16.83s"
    tr = PytestParser().parse(raw(stdout, return_code=1))
    assert tr.metrics["tests"] == pytest.approx(254 / 256)


PYTEST_WITH_FAILURE = """\
tests/test_foo.py::test_bar FAILED    [100%]

=================================== FAILURES ===================================
________________________________ test_bar ________________________________

    def test_bar():
>       assert 1 == 2
E       AssertionError: assert 1 == 2

tests/test_foo.py:5: AssertionError
=========================== short test summary info ============================
FAILED tests/test_foo.py::test_bar - AssertionError: assert 1 == 2
"""

def test_format_llm_message_includes_failure_output(tmp_path):
    test_file = tmp_path / "tests" / "test_foo.py"
    test_file.parent.mkdir()
    test_file.write_text("def test_bar():\n    assert 1 == 2\n")
    stdout = PYTEST_WITH_FAILURE.replace("tests/test_foo.py", str(test_file))
    tr = PytestParser().parse(raw(stdout, return_code=1))
    msg = PytestParser().format_llm_message(tr, context_lines=15)
    assert "FAILED" in msg
    assert "AssertionError" in msg


def test_format_llm_message_includes_function_body(tmp_path):
    test_file = tmp_path / "tests" / "test_foo.py"
    test_file.parent.mkdir()
    test_file.write_text("def test_bar():\n    assert 1 == 2\n")
    stdout = f"{test_file}::test_bar FAILED    [100%]\n"
    tr = PytestParser().parse(raw(stdout, return_code=1))
    msg = PytestParser().format_llm_message(tr, context_lines=15)
    assert "def test_bar" in msg


def test_format_llm_message_no_body_fallback():
    """When test file doesn't exist, still returns something useful."""
    tr = PytestParser().parse(raw(
        "tests/nonexistent.py::test_missing FAILED    [100%]\n", return_code=1
    ))
    msg = PytestParser().format_llm_message(tr, context_lines=15)
    assert "FAILED" in msg
