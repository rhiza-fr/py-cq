"""Parses output from ``uv audit`` into a standardized ToolResult.

``uv audit --output-format json`` checks the packages pinned in ``uv.lock``
against the OSV advisory database and prints a JSON report on stdout.

Only advisories with a fix version are counted: those are the ones an upgrade
resolves. The same vulnerability is often listed once per advisory database
(GHSA, PYSEC), so entries that alias one already seen for a package are
dropped. The count becomes a logistic-variant score stored under the
``dependencies`` metric key.

When no report can be read (``uv`` missing, no ``pyproject.toml`` or
``uv.lock``, no network) the tool reports no metric instead of a failing one.
"""

import json
import logging

from py_cq.localtypes import AbstractParser, RawResult, ToolResult
from py_cq.parsers.common import extract_first_issue, score_logistic_variant

log = logging.getLogger("cq")

_LOCKFILE = "uv.lock"


class UvAuditParser(AbstractParser):
    """Parses raw JSON output from ``uv audit`` into a ToolResult."""

    def parse(self, raw_result: RawResult) -> ToolResult:
        """Parses the raw ``uv audit`` JSON report into a ToolResult."""
        try:
            vulnerabilities = json.loads(raw_result.stdout)["vulnerabilities"]
        except (ValueError, KeyError, TypeError):
            reason = (raw_result.stderr or "").strip().splitlines()[-1:]
            log.warning(
                "uv audit produced no report (return_code=%s), skipping: %s",
                raw_result.return_code,
                reason[0] if reason else "no output",
            )
            return ToolResult(raw=raw_result)

        seen: set[tuple[str, str]] = set()
        issues: list[dict] = []
        for vuln in vulnerabilities:
            fix_versions = [str(v) for v in vuln.get("fix_versions") or []]
            if not fix_versions:
                continue
            dependency = vuln.get("dependency") or {}
            package = dependency.get("name", "")
            ids = {vuln.get("id", ""), *(vuln.get("aliases") or [])}
            if any((package, i) in seen for i in ids):
                continue
            seen.update((package, i) for i in ids)
            issues.append(
                {
                    "code": vuln.get("id", ""),
                    "package": package,
                    "version": dependency.get("version", ""),
                    "fix_versions": fix_versions,
                    "message": vuln.get("summary") or "",
                    "link": vuln.get("link") or "",
                }
            )

        score = score_logistic_variant(len(issues), scale_factor=5)
        details = {_LOCKFILE: issues} if issues else {}
        return ToolResult(
            raw=raw_result, metrics={"dependencies": score}, details=details
        )

    def format_llm_message(
        self, tr: ToolResult, *, context_lines: int = 15, limit: int = 1
    ) -> str:
        """Formats the first vulnerable dependency into an LLM-friendly message."""
        result = extract_first_issue(tr.details)
        if result is None:
            return "uv audit reported issues (no details available)"
        file, issue = result
        package = issue.get("package", "")
        fixed = ", ".join(issue.get("fix_versions", []))
        message = (
            f"{file} - {issue.get('code', '')}: **{package} {issue.get('version', '')}** "
            f"has a known vulnerability: {issue.get('message', '')}\n\n"
            f"Fixed in {fixed}. Upgrade with `uv lock --upgrade-package {package}`."
        )
        link = issue.get("link")
        return f"{message}\n\n{link}" if link else message
