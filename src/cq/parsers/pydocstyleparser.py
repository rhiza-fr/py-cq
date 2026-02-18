"""Parses output from the pydocstyle linter into a standardized `ToolResult`.

This module defines :class:`PydocstyleParser`, an implementation of
:class:`~.AbstractParser` that converts the raw stdout and exit code
produced by the `pydocstyle` command into a :class:`~.ToolResult`
object.  The parser counts docstring style violations, applies a
logistic-variant scoring function bounded by
``MAX_DOCSTRING_ERRORS``, and embeds the original output in the
``details`` field for debugging.

The parser expects ``raw_result.stdout`` to contain violations in the
format:

``path:line: code: message``

Each violation is followed by an empty line, so two consecutive
lines represent one violation.  The resulting :class:`ToolResult`
provides a ``metrics`` dictionary with a ``docstyle`` key and the
original ``stdout`` and return code in ``details``."""

import logging
import re

from cq.localtypes import AbstractParser, RawResult, ToolResult
from cq.parsers.common import score_logistic_variant, read_source_line

log = logging.getLogger("cq")

_LOC_RE = re.compile(r"^[./\\]*(.*\.py):(\d+) (.*):$")
_CODE_RE = re.compile(r"(D\d+): (.+)")


class PydocstyleParser(AbstractParser):
    """Parses raw results from the pydocstyle linter and converts them into a standardized ToolResult format, extracting relevant data and computing a docstring violation score."""

    def parse(self, raw_result: RawResult) -> ToolResult:
        """Parse the output of the `pydocstyle` linter and return a :class:`ToolResult`.

        The linter reports each violation on its own line followed by a blank line.
        This method treats every two lines as a single violation, counts them,
        and converts the count into a logistic-variant score bounded by
        ``MAX_DOCSTRING_ERRORS``.  The score is stored under the ``docstyle`` key
        in :pyattr:`ToolResult.metrics`, while the raw stdout and exit code are
        preserved in :pyattr:`ToolResult.details` for debugging.

        Args:
            raw_result: The result object returned by the `pydocstyle` command,
                containing ``stdout`` and ``return_code``.

        Returns:
            ToolResult: A result instance containing the computed score and the
            original command output.

        Example:
            >>> parser = PydocstyleParser()
            >>> tr = parser.parse(raw_result)
            >>> tr.metrics['docstyle']
            0.75"""
        # .\data\problems\travelling_salesman\ts_bad.py:1 at module level:
        #         D100: Missing docstring in public module
        # .\data\problems\travelling_salesman\ts_bad.py:13 in public function `find_nearest_city`:
        #         D200: One-line docstring should fit on one line with quotes (found 3)
        # .\data\problems\travelling_salesman\ts_bad.py:13 in public function `find_nearest_city`:
        #         D212: Multi-line docstring summary should start at the first line
        # .\data\problems\travelling_salesman\ts_bad.py:27 in public function `generate_tour`:
        #         D200: One-line docstring should fit on one line with quotes (found 3)
        # .\data\problems\travelling_salesman\ts_bad.py:27 in public function `generate_tour`:
        #         D212: Multi-line docstring summary should start at the first line
        # .\data\problems\travelling_salesman\ts_bad.py:48 in public function `main`:
        #         D103: Missing docstring in public function
        tr = ToolResult(raw=raw_result)
        MAX_DOCSTRING_ERRORS = 60
        lines = raw_result.stdout.splitlines()
        violations: dict[str, list] = {}
        i = 0
        while i < len(lines) - 1:
            loc = _LOC_RE.match(lines[i].strip())
            code = _CODE_RE.search(lines[i + 1])
            if loc and code:
                file_path = loc.group(1).replace("\\", "/")
                violations.setdefault(file_path, []).append(
                    {"line": int(loc.group(2)), "code": code.group(1), "message": code.group(2)}
                )
                i += 2
            else:
                i += 1
        errors = sum(len(v) for v in violations.values())
        score = score_logistic_variant(errors, scale_factor=MAX_DOCSTRING_ERRORS)
        log.debug("Docstring errors: %s, score: %s", errors, score)
        tr.metrics = {"docstyle": score}
        tr.details = violations
        return tr

    def format_llm_message(self, tr: ToolResult) -> str:
        """Return the first docstring violation as a defect description."""
        if not tr.details:
            return "pydocstyle reported issues (no details available)"
        file, issues = next(iter(tr.details.items()))
        issue = issues[0]
        line = issue.get("line", "?")
        code = issue.get("code", "")
        message = issue.get("message", "")
        src_line = read_source_line(file, line)
        code_block = f"\n```python\n{src_line}\n```" if src_line else ""
        return f"`{file}:{line}` — **{code}**: {message}{code_block}"
