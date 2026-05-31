"""Parses pytest test run output into a standardized :class:`ToolResult`.

This module provides :class:`PytestParser`, a concrete implementation of
:class:`AbstractParser` that consumes a :class:`RawResult` produced by a pytest
invocation and returns a :class:`ToolResult` instance.  The parser extracts
per-test statuses, calculates the overall pass rate, and attaches the
process return code so downstream components can uniformly consume results
from multiple test tools.  It is part of the test-collection framework and
enables consistent handling of pytest output across the system."""

import functools
import re as _re
from pathlib import Path as _Path

from py_cq.localtypes import AbstractParser, RawResult, ToolResult


@functools.lru_cache(maxsize=64)
def _section_pattern(test_name: str) -> _re.Pattern:
    return _re.compile(rf"_{{4,}}\s+{_re.escape(test_name)}\s+_{{4,}}")


def _target_dir(command: str) -> str:
    """Extract the --directory value from a uv run command, or ''."""
    m = _re.search(r'--directory\s+"?([^"\s]+)"?', command)
    return m.group(1) if m else ""


def _last_call_line_for_test(stdout: str, test_name: str) -> str:
    """Return the last source line before E-lines in a test's failure section.

    Captures both indented context lines and pytest's ``>``-prefixed
    current-executing-line marker.
    """
    lines = stdout.splitlines()
    pattern = _section_pattern(test_name)
    in_section = False
    last_src = ""
    for line in lines:
        if not in_section:
            if pattern.search(line):
                in_section = True
        else:
            stripped = line.strip()
            if stripped.startswith(("_", "=")):
                break
            if stripped.startswith("E ") or stripped == "E":
                break
            if line.startswith(("    ", "\t", ">")):
                src = line.lstrip("> \t")
                if src:
                    last_src = src
    return last_src


_COLLECTION_FILE_RE = _re.compile(r'E\s+File "([^"]+)", line (\d+)')
_COLLECTION_ERROR_RE = _re.compile(r"E\s+(\w+(?:Error|Warning|Exception)):\s*(.*)")


def _extract_collection_error(stdout: str) -> dict | None:
    """Return {file, line, type, help} if pytest stdout contains a collection error."""
    file_match = None
    error_match = None
    for line in stdout.splitlines():
        m = _COLLECTION_FILE_RE.search(line)
        if m:
            file_match = m
        m = _COLLECTION_ERROR_RE.search(line)
        if m:
            error_match = m
    if file_match and error_match:
        return {
            "file": file_match.group(1).replace("\\", "/"),
            "line": int(file_match.group(2)),
            "type": error_match.group(1),
            "help": error_match.group(2).strip(),
        }
    return None


def _extract_failure(stdout: str, test_name: str, max_lines: int) -> str:
    """Extract the failure section for test_name from pytest stdout."""
    lines = stdout.splitlines()
    pattern = _section_pattern(test_name)
    start = None
    for i, line in enumerate(lines):
        if pattern.search(line):
            start = i + 1
            break
    if start is None:
        return ""
    # Collect the full block - skip sub-section dividers ("_ _ _") but stop at
    # the next test header ("____") or summary line ("====").
    section = []
    for line in lines[start:]:
        stripped = line.strip()
        if _re.match(r"_{4,}", stripped) or stripped.startswith("="):
            break
        section.append(line)
    # Prefer E-lines (the actual assertion / exception messages).
    e_lines = [ln for ln in section if ln.startswith("E ") or ln.strip() == "E"]
    if e_lines:
        arrow_lines = [ln.lstrip("> \t") for ln in section if ln.startswith(">") and ln.lstrip("> \t")]
        cleaned = [_re.sub(r"^E\s*", "", ln) for ln in e_lines]
        # Drop "At index N diff:" lines - always redundant with the first E-line.
        cleaned = [ln for ln in cleaned if not _re.match(r"At index \d+ diff:", ln)]
        parts = ([f"> {arrow_lines[-1]}"] if arrow_lines else []) + cleaned
        text = "\n".join(parts[:max_lines]).strip()
    else:
        # Fall back: show the traceback up to max_lines, stopping before E-lines.
        sub = []
        for line in section:
            if line.startswith("E ") or line.strip() == "E":
                break
            sub.append(line)
            if len(sub) >= max_lines:
                break
        text = "\n".join(sub).strip()
    return f"\n```\n{text}\n```" if text else ""


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
            tr.metrics["tests"] = 0.0
        else:
            tests_found = dict()
            num_tests = 0
            passed_tests = 0
            for line in lines:
                # tests/test_common.py::test_name[param] PASSED    [ 8%]
                tests_match = _re.search(r"(.*\.py)::([\w\[\].,+\- ]+) (PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)", line)
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
                summary = _re.search(r"(\d+) passed(?:.*?(\d+) failed)?", raw_result.stdout)
                if summary:
                    passed_tests = int(summary.group(1))
                    failed_tests = int(summary.group(2)) if summary.group(2) else 0
                    num_tests = passed_tests + failed_tests
            tr.metrics["tests"] = passed_tests / num_tests if num_tests else 0
            tr.details = tests_found
        return tr

    def format_llm_message(self, tr: ToolResult, *, context_lines: int = 15, limit: int = 1) -> str:
        """Return the first failing test with function body, failure output, and callee signature."""
        from py_cq.parsers.common import (
            extract_callee_name,
            find_function_source,
            format_callee_context,
        )
        for file, tests in tr.details.items():
            if not isinstance(tests, dict):
                continue
            for test_name, status in tests.items():
                if status != "FAILED":
                    continue
                header = f"`{file}::{test_name}` - test **FAILED**"
                bare_name = test_name.split("[")[0]
                tdir = _target_dir(tr.raw.command)
                resolved = (_Path(tdir) / file).as_posix() if tdir and not _Path(file).is_absolute() else file
                body = find_function_source(resolved, bare_name, max_lines=context_lines)
                failure = _extract_failure(tr.raw.stdout, test_name, max_lines=50)
                callee = ""
                call_line = _last_call_line_for_test(tr.raw.stdout, test_name)
                if call_line:
                    func_name = extract_callee_name(call_line)
                    if func_name and func_name != bare_name:
                        callee = format_callee_context(func_name, resolved)
                parts = [header]
                if body:
                    parts.append(body)
                if failure:
                    parts.append(failure)
                if callee:
                    parts.append(callee)
                return "\n".join(parts)
        if "no tests ran" in tr.raw.stdout:
            return (
                "**No tests found.** pytest ran but collected nothing.\n\n"
                "Create `tests/test_basic.py` and write a first test covering a core function."
            )
        from py_cq.parsers.common import (
            extract_callee_name,
            format_callee_context,
            format_source_context,
        )
        combined = tr.raw.stdout + tr.raw.stderr
        err = _extract_collection_error(combined)
        if err:
            file, line, typ, help_msg = err["file"], err["line"], err["type"], err["help"]
            code_block = format_source_context(file, line, count=context_lines) or ""
            callee = ""
            # try to find callee from the offending source line via format_source_context result
            src_line = ""
            for ln in (tr.raw.stdout + tr.raw.stderr).splitlines():
                m = _re.match(r"E\s{6,}(\S.*)", ln)
                if m:
                    src_line = m.group(1)
            if src_line:
                func_name = extract_callee_name(src_line)
                if func_name:
                    callee = format_callee_context(func_name, file)
            return f"`{file}:{line}` - **{typ}**: {help_msg}{code_block}{callee}"
        output = combined.strip()
        if output:
            tail = "\n".join(output.splitlines()[-30:])
            return f"pytest reported failures:\n\n```\n{tail}\n```"
        return "pytest reported failures (no details available)"
