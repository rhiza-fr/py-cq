"""Parses output from bandit security linter into a standardized ToolResult.

Bandit is invoked with ``-f json``, producing a JSON blob on stdout.
The parser extracts per-file violations, applies severity weighting
(HIGH=5, MEDIUM=2, LOW=1), and converts the weighted count into a
logistic-variant score stored under the ``security`` metric key.
"""

import json

from py_cq.localtypes import AbstractParser, RawResult, ToolResult
from py_cq.parsers.common import format_source_context, score_logistic_variant

_SEVERITY_WEIGHT = {"HIGH": 5, "MEDIUM": 2, "LOW": 1}


class BanditParser(AbstractParser):
    """Parses raw JSON output from ``bandit -f json`` into a ToolResult."""

    def parse(self, raw_result: RawResult) -> ToolResult:
        try:
            data = json.loads(raw_result.stdout)
        except (json.JSONDecodeError, ValueError):
            return ToolResult(raw=raw_result, metrics={"security": 1.0})
        if not isinstance(data, dict):
            return ToolResult(raw=raw_result, metrics={"security": 1.0})

        files: dict[str, list] = {}
        weighted = 0
        for issue in data.get("results", []):
            path = issue.get("filename", "").replace("\\", "/")
            if "/.venv/" in path or "/site-packages/" in path:
                continue
            severity = issue.get("issue_severity", "LOW")
            files.setdefault(path, []).append({
                "line": issue.get("line_number", 0),
                "code": issue.get("test_id", ""),
                "severity": severity,
                "confidence": issue.get("issue_confidence", ""),
                "message": issue.get("issue_text", ""),
            })
            weighted += _SEVERITY_WEIGHT.get(severity, 1)

        score = score_logistic_variant(weighted, scale_factor=10)
        return ToolResult(raw=raw_result, metrics={"security": score}, details=files)

    def format_llm_message(self, tr: ToolResult, *, context_lines: int = 15) -> str:
        if not tr.details:
            return "bandit reported issues (no details available)"
        file, issues = next(iter(tr.details.items()))
        if not isinstance(issues, list) or not issues:
            return "bandit reported issues (no details available)"
        issue = issues[0]
        if not isinstance(issue, dict):
            return "bandit reported issues (no details available)"
        line = issue.get("line", "?")
        code = issue.get("code", "")
        severity = issue.get("severity", "")
        message = issue.get("message", "")
        return f"`{file}:{line}` — **{code}** [{severity}]: {message}{format_source_context(file, line, count=context_lines)}"
