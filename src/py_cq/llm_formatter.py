"""Format the most important code quality defect as a markdown prompt for LLM consumption."""

import sys

from py_cq.localtypes import CombinedToolResults, ToolConfig


def _severity(score: float, config: ToolConfig) -> int:
    """Return 0 (error), 1 (warning), or 2 (ok) for a given score and tool config."""
    if score < config.error_threshold:
        return 0
    if score < config.warning_threshold:
        return 1
    return 2


def format_for_llm(
    tool_configs: dict,
    combined: CombinedToolResults,
    cq_invocation: str | None = None,
) -> str:
    """Return a markdown prompt describing the single most important defect."""
    by_name = {tc.name: tc for tc in tool_configs.values()}

    failing = sorted(
        [
            tr for tr in combined.tool_results
            if tr.metrics and (cfg := by_name.get(tr.raw.tool_name)) and min(tr.metrics.values()) < cfg.warning_threshold
        ],
        key=lambda tr: (
            _severity(min(tr.metrics.values()), by_name[tr.raw.tool_name]),
            by_name[tr.raw.tool_name].priority,
            min(tr.metrics.values()),
        ),
    )
    if not failing:
        return f"# No issues found\n\nOverall score: **{combined.score:.3f} / 1.0**"

    worst = failing[0]
    config = by_name[worst.raw.tool_name]
    defect_md = config.parser_class().format_llm_message(worst)
    if cq_invocation is None:
        cq_invocation = "cq " + " ".join(sys.argv[1:])
    return (
        f"{defect_md}\n\n"
        f"Please fix only this issue. After fixing, run `{cq_invocation}` to verify."
    )
