"""Parses output from the ty type checker into a standardized ToolResult.

This module defines :class:`TyParser`, an implementation of
:class:`~.AbstractParser` that converts the raw stdout produced by
``ty check --output-format concise`` into a :class:`~.ToolResult`.

The concise output format is one diagnostic per line::

    <file>:<line>:<col>: <severity>[<code>] <message>

followed by a summary line ``Found N diagnostic`` or ``All checks passed!``.
Errors count more heavily than warnings toward the score."""

import re

from py_cq.localtypes import AbstractParser, RawResult, ToolResult
from py_cq.parsers.common import format_source_context, score_logistic_variant

_DIAG_RE = re.compile(r"^(.+):(\d+):\d+:\s+(error|warning)\[([^\]]+)\] (.+)$")

_CALL_CODES = frozenset([
    "call-non-callable",
    "missing-argument",
    "unexpected-keyword",
    "argument-type",
    "too-many-positional-arguments",
    "invalid-argument-type",
    "no-matching-overload",
])


class TyParser(AbstractParser):
    """Parses raw output from ``ty check`` into a structured ToolResult."""

    def parse(self, raw_result: RawResult) -> ToolResult:
        """Parse concise ty output and return a ToolResult.

        Args:
            raw_result: Raw output from ``ty check --output-format concise``.

        Returns:
            ToolResult with a ``type_check`` metric in [0, 1] and per-file diagnostics in details.
        """
        files: dict[str, list] = {}
        weighted = 0
        for line in (raw_result.stdout or "").splitlines():
            m = _DIAG_RE.match(line)
            if m:
                path = m.group(1).replace("\\", "/")
                severity = m.group(3)
                files.setdefault(path, []).append({
                    "line": int(m.group(2)),
                    "code": m.group(4),
                    "severity": severity,
                    "message": m.group(5),
                })
                weighted += 3 if severity == "error" else 1

        score = score_logistic_variant(weighted, scale_factor=10)
        return ToolResult(raw=raw_result, metrics={"type_check": score}, details=files)

    def format_llm_message(self, tr: ToolResult, *, context_lines: int = 15) -> str:
        """Return the first type-check diagnostic as a defect description."""
        if not tr.details:
            return "ty reported issues (no details available)"
        file, issues = next(iter(tr.details.items()))
        if not isinstance(issues, list) or not issues:
            return "ty reported issues (no details available)"
        issue = issues[0]
        if not isinstance(issue, dict):
            return "ty reported issues (no details available)"
        line = issue.get("line", "?")
        code = issue.get("code", "")
        message = issue.get("message", "")
        src_ctx = format_source_context(file, line, count=context_lines)
        callee = ""
        if code in _CALL_CODES and isinstance(line, int):
            from py_cq.parsers.common import extract_callee_name, format_callee_context, read_source_lines
            src_line = read_source_lines(file, line, count=1)
            func_name = extract_callee_name(src_line)
            if func_name:
                callee = format_callee_context(func_name, file)
        return f"`{file}:{line}` — **{code}**: {message}{src_ctx}{callee}"
