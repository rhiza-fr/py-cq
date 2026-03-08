"""Parses pytest test run output into a standardized :class:`ToolResult`.

This module provides :class:`PytestParser`, a concrete implementation of
:class:`AbstractParser` that consumes a :class:`RawResult` produced by a pytest
invocation and returns a :class:`ToolResult` instance.  The parser extracts
per-test statuses, calculates the overall pass rate, and attaches the
process return code so downstream components can uniformly consume results
from multiple test tools.  It is part of the test-collection framework and
enables consistent handling of pytest output across the system."""

import re

from py_cq.localtypes import AbstractParser, RawResult, ToolResult


class PytestParser(AbstractParser):
    """Parses raw pytest output into a structured `ToolResult`.

    Transforms the low-level output from a pytest run into a `ToolResult` that includes pass-rate metrics and detailed per-file test information, enabling downstream components to consume test metrics in a consistent, typed format. Inherits from `AbstractParser` to integrate with the existing parsing framework."""

    def parse(self, raw_result: RawResult) -> ToolResult:
        """Parse pytest raw output into a structured ToolResult.

        This method transforms the textual output of a pytest run into a
        :class:`ToolResult` object containing two pieces of information:

        * ``metrics['tests']`` - the fraction of tests that passed (``0`` when no
          tests were executed).
        * ``details`` - a mapping from each test file to the names of the
          tests defined in that file and their status (`PASSED`, `FAILED`, etc.).
          The dictionary also includes the process ``return_code`` for
          downstream consumers.

        The method splits ``raw_result.stdout`` into lines, checks for the
        ``'no tests ran'`` sentinel, then uses a regular expression to locate
        ``<file>::<test_name> <status>`` patterns.  It counts the total number of
        tests and the number of passed tests to compute the pass-rate metric.

        Args:
            raw_result (RawResult): Raw output produced by a pytest run,
                containing ``stdout`` and ``return_code``.

        Returns:
            ToolResult: A structured result that includes a ``tests`` metric
            and a ``details`` dictionary as described above.

        Raises:
            None.  The method never raises an exception; it gracefully handles
            malformed input by treating it as no tests were run."""
        # Simplified parsing - replace with actual logic
        lines = raw_result.stdout.splitlines()
        tr = ToolResult(raw=raw_result)
        if "no tests ran" in raw_result.stdout:
            pass
        else:
            tests_found = dict()
            num_tests = 0
            passed_tests = 0
            for line in lines:
                # tests/test_common.py::test_name[param] PASSED    [ 8%]
                tests_match = re.search(r"(.*\.py)::([\w\[\].,+\- ]+) (PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)", line)
                if tests_match:
                    test_file = tests_match.group(1)
                    test_name = tests_match.group(2).strip()
                    test_status = tests_match.group(3)
                    tests_found.setdefault(test_file, {})[test_name] = test_status
                    num_tests += 1
                    if test_status == "PASSED":
                        passed_tests += 1
            if num_tests == 0:
                # No individual test lines found (e.g. non-verbose output);
                # fall back to parsing the pytest summary line.
                summary = re.search(r"(\d+) passed(?:.*?(\d+) failed)?", raw_result.stdout)
                if summary:
                    passed_tests = int(summary.group(1))
                    failed_tests = int(summary.group(2)) if summary.group(2) else 0
                    num_tests = passed_tests + failed_tests
            tr.metrics["tests"] = passed_tests / num_tests if num_tests else 0
            tr.details = tests_found
        return tr

    def format_llm_message(self, tr: ToolResult, context_lines: int = 15) -> str:
        """Return the first failing test as a defect description."""
        for file, tests in tr.details.items():
            if isinstance(tests, dict):
                for test_name, status in tests.items():
                    if status == "FAILED":
                        return f"`{file}::{test_name}` — test **FAILED**"
        return "pytest reported failures (no details available)"
