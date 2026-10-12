"""Parses output from ruff format --check into a standardized ToolResult.

The concise output format is one line per unformatted file::

    <file>:<line>:<col>: unformatted: File would be reformatted

followed by a summary line such as
``2 files would be reformatted, 30 files already formatted`` or
``32 files already formatted``.

The score is the fraction of checked files that are already formatted."""

import re

from py_cq.localtypes import AbstractParser, RawResult, ToolResult
from py_cq.parsers.common import extract_first_issue

_FILE_RE = re.compile(r"^(.+):\d+:\d+: unformatted: ")
_FORMATTED_RE = re.compile(r"(\d+) files? already formatted")


class RuffFormatParser(AbstractParser):
    """Parses ``ruff format --check --output-format concise`` output into a ToolResult."""

    def parse(self, raw_result: RawResult) -> ToolResult:
        """Collect unformatted files and score the fraction already formatted."""
        stdout = raw_result.stdout or ""
        # One issue per file, with no line: the line ruff reports is the first
        # diff hunk, which would make the fingerprint unstable across edits.
        files: dict[str, list] = {}
        for line in stdout.splitlines():
            m = _FILE_RE.match(line)
            if m:
                files[m.group(1).replace("\\", "/")] = [{}]
        m = _FORMATTED_RE.search(stdout)
        formatted = int(m.group(1)) if m else 0
        total = formatted + len(files)
        score = formatted / total if total else 1.0
        return ToolResult(raw=raw_result, metrics={"formatted": score}, details=files)

    def format_llm_message(
        self, tr: ToolResult, *, context_lines: int = 15, limit: int = 1
    ) -> str:
        """Ask for the formatter to be run rather than a hand edit."""
        result = extract_first_issue(tr.details)
        if result is None:
            return "ruff format reported issues (no details available)"
        file, _ = result
        return (
            f"{file} - **not formatted**. Run the formatter, do not edit by hand:\n\n"
            f"```bash\nruff format {file}\n```\n\n"
            "Other files may also need formatting; `ruff format .` fixes them all."
        )
