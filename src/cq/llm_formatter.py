"""Format the most important code quality defect as a markdown prompt for LLM consumption."""

import sys

from cq.localtypes import CombinedToolResults, ToolConfig


def format_for_llm(
    tool_configs: dict,
    combined: CombinedToolResults,
    cq_invocation: str | None = None,
) -> str:
    """Return a markdown prompt describing the single most important defect."""
    by_name = {tc.name: tc for tc in tool_configs.values()}

    failing = sorted(
        [tr for tr in combined.tool_results if tr.metrics and min(tr.metrics.values()) < 1.0],
        key=lambda tr: (
            by_name.get(tr.raw.tool_name, ToolConfig(name="", command="", parser_class=object, priority=99)).priority,
            min(tr.metrics.values()),  # worst score first within same priority
        ),
    )
    if not failing:
        return f"# No issues found\n\nOverall score: **{combined.score:.3f} / 1.0**"

    worst = failing[0]
    config = by_name[worst.raw.tool_name]
    defect_md = config.parser_class().format_llm_message(worst)
    if cq_invocation is None:
        cq_invocation = "cq " + " ".join(sys.argv[1:])
    return _render(combined.score, defect_md, worst.raw.command, cq_invocation)


def _clean_command(raw_command: str) -> str:
    """Strip the Python interpreter prefix, keeping just the module invocation."""
    if " -m " in raw_command:
        return raw_command.split(" -m ", 1)[1]
    return raw_command


def _render(score: float, defect_md: str, raw_command: str, cq_invocation: str) -> str:
    clean_cmd = _clean_command(raw_command)
    cmd_line = f"`{clean_cmd}` returned an error." if clean_cmd else "A static analysis tool returned an error."
    return (
        f"# Fix this code quality issue\n\n"
        f"{cmd_line}\n"
        f"Overall score: **{score:.2f} / 1.0**\n\n"
        f"## Issue\n\n"
        f"{defect_md}\n\n"
        f"Please fix only this issue. After fixing, run `{cq_invocation}` to verify."
    )
