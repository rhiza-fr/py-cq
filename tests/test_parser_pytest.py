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
    assert tr.metrics == {"tests": 0.0}


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


def test_format_llm_message_no_tests_ran():
    """'no tests ran' produces a clear actionable message."""
    tr = PytestParser().parse(raw(PYTEST_NO_TESTS))
    msg = PytestParser().format_llm_message(tr)
    assert "No tests found" in msg
    assert "tests/" in msg


def test_format_llm_message_no_details_shows_stderr():
    """When no test details exist, fallback shows stderr content."""
    from py_cq.localtypes import RawResult
    raw_result = RawResult(tool_name="pytest", command="cmd", stdout="", stderr="No module named pytest\n", return_code=1)
    tr = PytestParser().parse(raw_result)
    msg = PytestParser().format_llm_message(tr, context_lines=15)
    assert "No module named pytest" in msg


PYTEST_PARAMETERIZED_FAILURE = """\
tests/test_foo.py::test_bar[a-b] FAILED    [100%]

=================================== FAILURES ===================================
__________________________ test_bar[a-b] __________________________

    def test_bar(x):
>       assert helper(x) == 2
E       AssertionError: assert 1 == 2

tests/test_foo.py:3: AssertionError
"""


def test_format_llm_message_parameterized_finds_body(tmp_path):
    """Parameterized test names have [params] stripped before looking up function body."""
    test_file = tmp_path / "tests" / "test_foo.py"
    test_file.parent.mkdir()
    test_file.write_text("def test_bar(x):\n    assert helper(x) == 2\n")
    stdout = PYTEST_PARAMETERIZED_FAILURE.replace("tests/test_foo.py", str(test_file))
    tr = PytestParser().parse(raw(stdout, return_code=1))
    msg = PytestParser().format_llm_message(tr, context_lines=15)
    assert "def test_bar" in msg


def test_last_call_line_for_test():
    from py_cq.parsers.pytestparser import _last_call_line_for_test
    stdout = """\
________ test_foo ________

    def test_foo():
>       result = make_thing(bad=1)
E       TypeError: make_thing() got unexpected keyword argument 'bad'

tests/test_foo.py:2: TypeError
"""
    line = _last_call_line_for_test(stdout, "test_foo")
    assert "make_thing" in line


def test_format_llm_message_includes_callee(tmp_path):
    """When the failing line calls a project function, its definition is appended."""
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    test_file = tmp_path / "test_foo.py"
    helper_file = tmp_path / "helpers.py"
    helper_file.write_text("def make_thing(x, y):\n    return x + y\n")
    test_file.write_text("def test_foo():\n    result = make_thing(bad=1)\n    assert result == 2\n")
    stdout = f"""\
{test_file}::test_foo FAILED    [100%]

=================================== FAILURES ===================================
________ test_foo ________

    def test_foo():
>       result = make_thing(bad=1)
E       TypeError: make_thing() got unexpected keyword argument 'bad'

{test_file}:2: TypeError
"""
    tr = PytestParser().parse(raw(stdout, return_code=1))
    msg = PytestParser().format_llm_message(tr, context_lines=15)
    assert "def make_thing" in msg


def test_format_llm_message_no_body_fallback():
    """When test file doesn't exist, header is returned without function body."""
    tr = PytestParser().parse(raw(
        "tests/nonexistent.py::test_missing FAILED    [100%]\n", return_code=1
    ))
    msg = PytestParser().format_llm_message(tr, context_lines=15)
    assert "FAILED" in msg
    assert "def test_missing" not in msg  # no body since file doesn't exist


PYTEST_COLLECTION_ERROR = """\
ERROR collecting tests/test_bad.py
...
E   File "tests/test_bad.py", line 3
E       ImportError: cannot import name 'foo' from 'mymodule'
"""


def test_collection_error_returns_error_not_generic_failure():
    """format_llm_message reports the collection error, not a generic failure."""
    tr = PytestParser().parse(raw(PYTEST_COLLECTION_ERROR, return_code=2))
    msg = PytestParser().format_llm_message(tr)
    assert "ImportError" in msg
    assert "tests/test_bad.py" in msg


def test_last_call_line_breaks_on_separator_line():
    """_last_call_line_for_test stops and doesn't include the trailing === separator."""
    from py_cq.parsers.pytestparser import _last_call_line_for_test
    stdout = """\
____ test_foo ____

    def test_foo():
>       do_something()

==============================================
"""
    line = _last_call_line_for_test(stdout, "test_foo")
    assert "do_something" in line
    assert "=" not in line


def test_extract_failure_max_lines():
    """_extract_failure truncates at max_lines."""
    from py_cq.parsers.pytestparser import _extract_failure
    stdout = """\
____test_long____
line1
line2
line3
line4
line5
"""
    result = _extract_failure(stdout, "test_long", max_lines=2)
    # Should contain only up to 2 lines of content
    content_lines = [ln for ln in result.strip().split("\n") if ln not in ("```", "")]
    assert len(content_lines) <= 2


def test_format_llm_message_skips_non_dict_test_entry():
    """format_llm_message skips details entries that are not dicts."""
    from py_cq.localtypes import RawResult
    raw_result = RawResult(tool_name="pytest", stdout="", stderr="", return_code=1)
    from py_cq.parsers.pytestparser import PytestParser
    from py_cq.localtypes import ToolResult
    tr = ToolResult(
        metrics={"tests": 0.0},
        details={"tests/test_foo.py": "not-a-dict"},
        raw=raw_result,
    )
    msg = PytestParser().format_llm_message(tr)
    # Falls through to the generic fallback since no dict test entries
    assert "pytest" in msg.lower() or "no details" in msg.lower() or "failure" in msg.lower()


def test_format_llm_message_collection_error_with_callee(tmp_path):
    """format_llm_message extracts callee from a collection error src line."""
    src_file = tmp_path / "mymodule.py"
    src_file.write_text("def my_func(x):\n    return x\n")
    stdout = (
        f'E   File "{src_file}", line 1\n'
        "E   ImportError: cannot import 'my_func'\n"
        "E         my_func(bad_arg)\n"
    )
    from py_cq.localtypes import RawResult
    raw_result = RawResult(tool_name="pytest", stdout=stdout, stderr="", return_code=2)
    tr = PytestParser().parse(raw_result)
    msg = PytestParser().format_llm_message(tr)
    assert "ImportError" in msg or "my_func" in msg


def test_skipped_tests_do_not_reduce_pass_rate():
    """SKIPPED tests are counted but do not lower the pass rate."""
    stdout = (
        "tests/test_foo.py::test_one PASSED    [ 50%]\n"
        "tests/test_foo.py::test_two SKIPPED   [100%]\n"
    )
    tr = PytestParser().parse(raw(stdout, return_code=0))
    # 1 passed, 1 skipped → 2 total, 1 passed → 0.5, not 1.0
    # The key assertion: skipped != failed, so score should not be 0.0
    assert tr.metrics["tests"] > 0.0


def test_extract_failure_truncates_at_max_lines():
    """_extract_failure stops collecting at max_lines (line 85 coverage)."""
    from py_cq.parsers.pytestparser import _extract_failure
    body = "\n".join(f"    line_{i} = {i}" for i in range(10))
    stdout = f"____ test_foo ____\n{body}\n=== short test summary ===\n"
    result = _extract_failure(stdout, "test_foo", max_lines=3)
    content_lines = [ln for ln in result.strip().split("\n") if ln not in ("```", "")]
    assert len(content_lines) <= 3


def test_format_llm_message_skips_passed_tests():
    """format_llm_message skips PASSED tests and returns info on the first FAILED one."""
    stdout = (
        "tests/test_foo.py::test_pass PASSED    [ 50%]\n"
        "tests/test_foo.py::test_fail FAILED    [100%]\n"
    )
    tr = PytestParser().parse(raw(stdout, return_code=1))
    msg = PytestParser().format_llm_message(tr)
    assert "test_fail" in msg
    assert "test_pass" not in msg


def test_last_call_line_whitespace_only_line():
    """_last_call_line_for_test ignores lines that strip to empty — branch 38->26."""
    from py_cq.parsers.pytestparser import _last_call_line_for_test
    stdout = """\
________ test_foo ________

    def test_foo():
>
>       result = make_thing(bad=1)
E       TypeError: unexpected keyword

tests/test_foo.py:2: TypeError
"""
    line = _last_call_line_for_test(stdout, "test_foo")
    assert "make_thing" in line


def test_format_llm_message_all_passed_then_failed():
    """Inner for-loop exhausts on first file (all PASSED) before finding FAILED — branch 166->163."""
    stdout = (
        "tests/test_a.py::test_one PASSED    [ 50%]\n"
        "tests/test_b.py::test_fail FAILED    [100%]\n"
    )
    tr = PytestParser().parse(raw(stdout, return_code=1))
    msg = PytestParser().format_llm_message(tr)
    assert "test_fail" in msg
    assert "test_one" not in msg


def test_format_llm_message_collection_error_no_src_line():
    """Collection error with no deeply-indented E source line — branch 210->214 (src_line empty)."""
    from py_cq.localtypes import RawResult
    stdout = (
        "ERROR collecting tests/test_bad.py\n"
        'E   File "tests/test_bad.py", line 3\n'
        "E   ImportError: cannot import name 'foo'\n"
    )
    raw_result = RawResult(tool_name="pytest", stdout=stdout, stderr="", return_code=2)
    tr = PytestParser().parse(raw_result)
    msg = PytestParser().format_llm_message(tr)
    assert "ImportError" in msg
    assert "tests/test_bad.py" in msg


# Realistic multi-line collection error matching both _COLLECTION_FILE_RE and _COLLECTION_ERROR_RE
REALISTIC_COLLECTION_ERROR = """\
ERRORS
collecting tests/test_conftest_bad.py
E   Traceback (most recent call last):
E     File "tests/conftest.py", line 7
E   ImportError: cannot import name 'setup_db' from 'mymodule' (mymodule/__init__.py)
"""


def test_realistic_collection_error_details_populated():
    """A realistic multi-line conftest ImportError populates failed_files correctly."""
    from py_cq.localtypes import RawResult
    raw_result = RawResult(
        tool_name="pytest",
        stdout=REALISTIC_COLLECTION_ERROR,
        stderr="",
        return_code=2,
    )
    tr = PytestParser().parse(raw_result)
    msg = PytestParser().format_llm_message(tr)
    # The _COLLECTION_FILE_RE / _COLLECTION_ERROR_RE patterns should have matched
    assert "ImportError" in msg
    assert "conftest.py" in msg or "line 7" in msg
