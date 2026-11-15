"""Parses output from the Kingfisher secret scanner into a standardized ToolResult.

Kingfisher (``uv tool install kingfisher-bin``) is invoked with ``-f json`` and
``--redact``, so the report on stdout never contains the secret itself, only a
hash. ``--no-validate`` keeps it from sending findings to provider APIs.

Each finding is listed against its file. The count becomes a logistic-variant
score stored under the ``secrets`` metric key.

When no report can be read (``kingfisher`` not on PATH) the tool reports no
metric instead of a failing one.
"""

import json
import logging

from py_cq.localtypes import AbstractParser, RawResult, ToolResult
from py_cq.parsers.common import extract_first_issue, score_logistic_variant

log = logging.getLogger("cq")


class KingfisherParser(AbstractParser):
    """Parses raw JSON output from ``kingfisher scan -f json`` into a ToolResult."""

    def parse(self, raw_result: RawResult) -> ToolResult:
        """Parses the raw Kingfisher JSON report into a ToolResult."""
        try:
            findings = json.loads(raw_result.stdout)["findings"]
        except (ValueError, KeyError, TypeError):
            log.warning(
                "kingfisher produced no report (return_code=%s), skipping. "
                "Install it with `uv tool install kingfisher-bin`.",
                raw_result.return_code,
            )
            return ToolResult(raw=raw_result)

        files: dict[str, list] = {}
        for entry in findings:
            rule = entry.get("rule") or {}
            finding = entry.get("finding") or {}
            path = str(finding.get("path", "")).replace("\\", "/")
            files.setdefault(path, []).append(
                {
                    "line": finding.get("line", 0),
                    "code": rule.get("id", ""),
                    "confidence": finding.get("confidence", ""),
                    "message": rule.get("description", ""),
                }
            )

        count = sum(len(issues) for issues in files.values())
        score = score_logistic_variant(count, scale_factor=5)
        return ToolResult(raw=raw_result, metrics={"secrets": score}, details=files)

    def format_llm_message(
        self, tr: ToolResult, *, context_lines: int = 15, limit: int = 1
    ) -> str:
        """Formats the first secret finding into an LLM-friendly message."""
        result = extract_first_issue(tr.details)
        if result is None:
            return "kingfisher reported secrets (no details available)"
        file, issue = result
        line = issue.get("line", "?")
        # No source excerpt: it would put the plaintext secret into the LLM prompt.
        return (
            f"{file}:{line} - {issue.get('code', '')}: "
            f"[{issue.get('confidence', '')} confidence] {issue.get('message', '')}\n\n"
            "Move the secret out of the source (environment variable or an untracked "
            "file) and rotate it if it was ever committed. If it is a test fixture or "
            "a false positive, add a `kingfisher:ignore` comment on that line."
        )
