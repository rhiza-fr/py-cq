"""Parses output from bandit security linter into a standardized ToolResult.

Bandit is invoked with ``-f json``, producing a JSON blob on stdout.
The parser extracts per-file violations, applies severity weighting
(HIGH=5, MEDIUM=2, LOW=1), and converts the weighted count into a
logistic-variant score stored under the ``security`` metric key.
"""

import json
import logging

from py_cq.localtypes import AbstractParser, RawResult, ToolResult
from py_cq.parsers.common import extract_first_issue, format_source_context, score_logistic_variant

log = logging.getLogger("cq")

_SEVERITY_WEIGHT = {"HIGH": 5, "MEDIUM": 2, "LOW": 1}


class BanditParser(AbstractParser):
    """Parses raw JSON output from ``bandit -f json`` into a ToolResult."""

    def parse(self, raw_result: RawResult) -> ToolResult:
        try:
            data = json.loads(raw_result.stdout)
        except (json.JSONDecodeError, ValueError):
            log.warning("bandit output is not valid JSON (return_code=%s). Reporting degraded score.", raw_result.return_code)
            degraded = 0.0 if raw_result.return_code != 0 else 0.5
            return ToolResult(raw=raw_result, metrics={"security": degraded})
        if not isinstance(data, dict):
            log.warning("bandit output is not a JSON object. Reporting degraded score.")
            return ToolResult(raw=raw_result, metrics={"security": 0.5})

        # totals = data.get("metrics", {}).get("_totals", {})
        # log.debug("bandit scanned %d LOC across %d files", totals.get("loc", 0), len(data.get("metrics", {})) - 1)

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

    def format_llm_message(self, tr: ToolResult, *, context_lines: int = 15, limit: int = 1) -> str:
        result = extract_first_issue(tr.details)
        if result is None:
            return "bandit reported issues (no details available)"
        file, issue = result
        line = issue.get("line", "?")
        code = issue.get("code", "")
        severity = issue.get("severity", "")
        message = issue.get("message", "")
        return f"`{file}:{line}` — **{code}** [{severity}]: {message}{format_source_context(file, line, count=context_lines)}"
