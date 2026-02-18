"""Parses output from ruff check into a standardized ToolResult.

This module defines :class:`RuffParser`, an implementation of
:class:`~.AbstractParser` that converts the raw stdout produced by
``ruff check --output-format concise`` into a :class:`~.ToolResult`.

The concise output format is one violation per line::

    <file>:<line>:<col>: <CODE> <message>

followed by a summary line ``Found N error.`` or ``All checks passed!``."""

import re

from cq.localtypes import AbstractParser, RawResult, ToolResult
from cq.parsers.common import score_logistic_variant, read_source_line

_DIAG_RE = re.compile(r"^(.+):(\d+):(\d+): ([A-Z]\d+) (.+)$")


class RuffParser(AbstractParser):
    """Parses raw output from ``ruff check`` into a structured ToolResult."""

    def parse(self, raw_result: RawResult) -> ToolResult:
        """Parse concise ruff output and return a ToolResult.

        Args:
            raw_result: Raw output from ``ruff check --output-format concise``.

        Returns:
            ToolResult with a ``lint`` metric in [0, 1] and per-file violations in details.
        """
        files: dict[str, list] = {}
        for line in (raw_result.stdout or "").splitlines():
            m = _DIAG_RE.match(line)
            if m:
                path = m.group(1).replace("\\", "/")
                files.setdefault(path, []).append({
                    "line": int(m.group(2)),
                    "code": m.group(4),
                    "message": m.group(5),
                })
        score = score_logistic_variant(
            sum(len(v) for v in files.values()), scale_factor=20
        )
        return ToolResult(raw=raw_result, metrics={"lint": score}, details=files)

    def format_llm_message(self, tr: ToolResult) -> str:
        """Return the first lint violation as a defect description."""
        if not tr.details:
            return "ruff reported issues (no details available)"
        file, issues = next(iter(tr.details.items()))
        issue = issues[0]
        line = issue.get("line", "?")
        code = issue.get("code", "")
        message = issue.get("message", "")
        src_line = read_source_line(file, line)
        code_block = f"\n```python\n{src_line}\n```" if src_line else ""
        return f"`{file}:{line}` — **{code}**: {message}{code_block}"
