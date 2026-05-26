"""Format the most important code quality defect as a markdown prompt for LLM consumption."""

import sys

from py_cq.localtypes import CombinedToolResults, ToolConfig, ToolResult


def _severity(score: float, config: ToolConfig) -> int:
    """Return 0 (error), 1 (warning), or 2 (ok) for a given score and tool config."""
    if score < config.error_threshold:
        return 0
    if score < config.warning_threshold:
        return 1
    return 2


def _single_issue_slices(tr: ToolResult, limit: int) -> list[ToolResult]:
    """Return up to `limit` ToolResults each containing one issue from tr.details."""
    slices: list[ToolResult] = []
    has_list = any(isinstance(v, list) for v in tr.details.values())
    if has_list:
        for file, issues in tr.details.items():
            if isinstance(issues, list):
                for issue in issues:
                    slices.append(ToolResult(raw=tr.raw, metrics=tr.metrics, details={file: [issue]}))
                if len(slices) >= limit:
                    break
    else:
        # Non-list details (e.g. interrogate per-file stats): one slice per entry, sorted by coverage
        items = sorted(tr.details.items(), key=lambda x: x[1].get("coverage", 0.0) if isinstance(x[1], dict) else 0)
        for file, data in items[:limit]:
            slices.append(ToolResult(raw=tr.raw, metrics=tr.metrics, details={file: data}))
    return slices[:limit] or [tr]


def format_for_llm(
    tool_configs: dict,
    combined: CombinedToolResults,
    cq_invocation: str | None = None,
    context_lines: int = 15,
    hint: bool = False,
    limit: int = 1,
) -> str:
    """Return a markdown prompt describing the top `limit` defects from the worst-scoring tool."""
    by_name = {tc.name: tc for tc in tool_configs.values()}

    failing = sorted(
        [
            tr for tr in combined.tool_results
            if tr.metrics and (cfg := by_name.get(tr.raw.tool_name)) and min(tr.metrics.values()) < cfg.warning_threshold
        ],
        key=lambda tr: (
            _severity(min(tr.metrics.values()), by_name[tr.raw.tool_name]),
            by_name[tr.raw.tool_name].order,
            min(tr.metrics.values()),
        ),
    )
    if not failing:
        return f"# No issues found\n\nOverall score: **{combined.score:.3f} / 1.0**"

    worst = failing[0]
    config = by_name[worst.raw.tool_name]
    parser = config.parser_class()

    slices = _single_issue_slices(worst, limit)
    parts = [parser.format_llm_message(s, context_lines=context_lines, limit=limit) for s in slices]
    n = len(parts)
    defect_md = "\n\n---\n\n".join(parts)
    close = "Please fix only this issue." if n == 1 else f"Please fix these {n} issues."
    body = f"{defect_md}\n\n{close}"
    if hint:
        if cq_invocation is None:
            cq_invocation = "cq " + " ".join(sys.argv[1:])
        body += f" After fixing, run `{cq_invocation}` to verify."
    return body
