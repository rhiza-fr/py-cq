"""Parser that counts stdout lines matching a regex pattern."""

import functools
import re

from py_cq.localtypes import AbstractParser, RawResult, ToolResult
from py_cq.parsers.common import score_logistic_variant


class RegexCountParser(AbstractParser):
    """Score based on the number of stdout lines matching a regex.

    parser_config keys:
        pattern (str, required): regex pattern to match against each line.
        scale_factor (int, default 15): passed to score_logistic_variant.
    """

    @functools.cached_property
    def _pattern(self) -> re.Pattern:
        return re.compile(self.parser_config["pattern"])

    def parse(self, raw_result: RawResult) -> ToolResult:
        """
        Parses the raw result using a regex pattern and computes a score.
        """
        scale = self.parser_config.get("scale_factor", 15)
        lines = (raw_result.stdout or "").splitlines()
        matches = [ln for ln in lines if self._pattern.search(ln)]
        count = len(matches)
        score = score_logistic_variant(count, scale_factor=scale)
        return ToolResult(
            raw=raw_result,
            metrics={"violations": score},
            details={"count": count, "matches": matches},
        )

    def format_llm_message(self, tr: ToolResult, *, context_lines: int = 15, limit: int = 1) -> str:
        """Formats the LLM message with match details."""
        matches = tr.details.get("matches", [])
        if not matches:
            return "No violations found"
        shown = matches[:context_lines]
        return "\n".join(shown)
