"""Parser that scores a tool pass/fail based solely on its exit code."""

from py_cq.localtypes import AbstractParser, RawResult, ToolResult


class ExitCodeParser(AbstractParser):
    """Score 1.0 if the tool exited with code 0, else 0.0."""

    def parse(self, raw_result: RawResult) -> ToolResult:
        """Parse the tool result and return a score based on the exit code."""
        score = 1.0 if raw_result.return_code == 0 else 0.0
        return ToolResult(raw=raw_result, metrics={"exit_code": score})

    def format_llm_message(
        self, tr: ToolResult, *, context_lines: int = 15, limit: int = 1
    ) -> str:
        """Format the tool result as a string message for the LLM."""

        output = tr.raw.stdout.strip() or tr.raw.stderr.strip()
        lines = output.splitlines()[:context_lines]
        return (
            "\n".join(lines)
            if lines
            else "Tool exited with non-zero status (no output)"
        )
