"""Parses output from vulture dead-code detector into a standardized ToolResult.

Vulture is invoked with ``--min-confidence 80``, producing one text line
per unused symbol::

    src/foo.py:10: unused function 'bar' (80% confidence)

The parser counts violations and converts the count into a logistic-variant
score stored under the ``dead_code`` metric key.
"""

import re

from py_cq.localtypes import AbstractParser, RawResult, ToolResult
from py_cq.parsers.common import format_source_context, score_logistic_variant

_LINE_RE = re.compile(r"^(.+):(\d+): (unused \S+) '(.+)' \((\d+)% confidence\)$")


class VultureParser(AbstractParser):
    """Parses raw text output from ``vulture`` into a ToolResult."""

    def parse(self, raw_result: RawResult) -> ToolResult:
        files: dict[str, list] = {}
        for line in (raw_result.stdout or "").splitlines():
            m = _LINE_RE.match(line)
            if m:
                path = m.group(1).replace("\\", "/")
                files.setdefault(path, []).append({
                    "line": int(m.group(2)),
                    "type": m.group(3),
                    "name": m.group(4),
                    "confidence": int(m.group(5)),
                })
        count = sum(len(v) for v in files.values())
        score = score_logistic_variant(count, scale_factor=15)
        return ToolResult(raw=raw_result, metrics={"dead_code": score}, details=files)

    def format_llm_message(self, tr: ToolResult, *, context_lines: int = 15) -> str:
        if not tr.details:
            return "vulture reported issues (no details available)"
        file, issues = next(iter(tr.details.items()))
        issue = issues[0]
        line = issue.get("line", "?")
        kind = issue.get("type", "unused")
        name = issue.get("name", "")
        confidence = issue.get("confidence", "?")
        return f"`{file}:{line}` — **{kind}** `{name}` ({confidence}% confidence){format_source_context(file, line, count=context_lines)}"
