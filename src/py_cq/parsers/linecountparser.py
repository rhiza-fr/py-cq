"""Parser that scores a tool by counting non-empty output lines as violations."""

from py_cq.localtypes import AbstractParser, RawResult, ToolResult
from py_cq.parsers.common import score_logistic_variant


class LineCountParser(AbstractParser):
    """Score based on number of non-empty stdout lines.

    parser_config keys:
        scale_factor (int, default 15): passed to score_logistic_variant.
    """

    def parse(self, raw_result: RawResult) -> ToolResult:
        lines = [ln for ln in (raw_result.stdout or "").splitlines() if ln.strip()]
        count = len(lines)
        scale = self.parser_config.get("scale_factor", 15)
        score = score_logistic_variant(count, scale_factor=scale)
        return ToolResult(raw=raw_result, metrics={"violations": score}, details={"lines": lines})

    def format_llm_message(self, tr: ToolResult, *, context_lines: int = 15, limit: int = 1) -> str:
        lines = tr.details.get("lines", [])
        if not lines:
            return "No violations found"
        shown = lines[:context_lines]
        return "\n".join(shown)
