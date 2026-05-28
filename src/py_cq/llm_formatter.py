"""Format the most important code quality defect as a markdown prompt for LLM consumption."""

import sys
from pathlib import Path
from typing import cast

from py_cq.localtypes import CombinedToolResults, ToolConfig, ToolResult


def _severity(score: float, config: ToolConfig) -> int:
    """Return 0 (error), 1 (warning), or 2 (ok) for a given score and tool config."""
    if score < config.error_threshold:
        return 0
    if score < config.warning_threshold:
        return 1
    return 2


def _parse_silence_spec(spec: str) -> tuple[str, int | None, str | None]:
    """Parse 'file[:line[:code]]' into (file, line, code).

    Uses rsplit to handle Windows paths (e.g. C:/foo/bar.py:10:E501).
    """
    parts = spec.rsplit(":", 2)
    file = parts[0]
    line = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
    code = parts[2] if len(parts) > 2 else None
    return file, line, code


def _is_silenced(file: str, issue: dict, specs: list[str]) -> bool:
    file_parts = Path(file.replace("\\", "/")).parts
    for spec in specs:
        spec_file, spec_line, spec_code = _parse_silence_spec(spec)
        spec_parts = Path(spec_file.replace("\\", "/")).parts
        n = len(spec_parts)
        if file_parts[-n:] != spec_parts:
            continue
        if spec_line is not None and issue.get("line") != spec_line:
            continue
        if spec_code is not None and issue.get("code") != spec_code:
            continue
        return True
    return False


def _single_issue_slices(tr: ToolResult, limit: int, silence: list[str] | None = None) -> list[ToolResult]:
    """Return up to `limit` ToolResults each containing one issue from tr.details.

    Returns empty list (not [tr]) when silence specs filter out all issues."""
    silence = silence or []
    slices: list[ToolResult] = []
    has_list = any(isinstance(v, list) for v in tr.details.values())
    if has_list:
        for file, issues in tr.details.items():
            if isinstance(issues, list):
                for issue in issues:
                    if silence and _is_silenced(file, issue, silence):
                        continue
                    slices.append(ToolResult(raw=tr.raw, metrics=tr.metrics, details={file: [issue]}))
                if len(slices) >= limit:
                    break
    else:
        # Non-list details: sort so files with failures (pytest-style) come first, then by coverage ascending
        def _dict_sort_key(v: object) -> tuple[int, float, float]:
            if not isinstance(v, dict):
                return (0, 0.0, 1.0)
            d = cast("dict[str, object]", v)
            failures = sum(1 for val in d.values() if isinstance(val, str) and val in ("FAILED", "ERROR"))
            cov_val = d.get("coverage", 0)
            coverage = float(cov_val) if isinstance(cov_val, (int, float, str)) else 0.0
            sm_val = d.get("smallness", 1.0)
            smallness = float(sm_val) if isinstance(sm_val, (int, float)) else 1.0
            return (-failures, coverage, smallness)

        items = sorted(tr.details.items(), key=lambda x: _dict_sort_key(x[1]))
        for file, data in items:
            if silence and _is_silenced(file, {}, silence):
                continue
            slices.append(ToolResult(raw=tr.raw, metrics=tr.metrics, details={file: data}))
            if len(slices) >= limit:
                break
    return slices[:limit] or ([] if silence else [tr])


def _select_top_issue(
    tool_configs: dict,
    combined: CombinedToolResults,
    limit: int,
    silence: list[str],
):
    """Return (worst, slices, config, parser) for the top failing tool, or None if all pass."""
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
    for candidate in failing:
        slices = _single_issue_slices(candidate, limit, silence)
        if slices:
            config = by_name[candidate.raw.tool_name]
            return candidate, slices, config, config.parser_class()
    return None


def _build_message(slices, parser, context_lines: int, limit: int, hint: bool, cq_invocation) -> str:
    parts = [parser.format_llm_message(s, context_lines=context_lines, limit=limit) for s in slices]
    n = len(parts)
    close = "Please fix only this issue." if n == 1 else f"Please fix these {n} issues."
    body = "\n\n---\n\n".join(parts) + f"\n\n{close}"
    if hint:
        if cq_invocation is None:
            cq_invocation = "cq " + " ".join(sys.argv[1:])
        body += f" After fixing, run `{cq_invocation}` to verify."
    return body


def _fingerprint_from_slice(tool_name: str, tr: ToolResult) -> str:
    """Return fingerprint as tool:file:line:code (line/code omitted when unavailable)."""
    for file, issues in tr.details.items():
        posix = Path(file).as_posix()
        if isinstance(issues, list) and issues:
            code = issues[0].get("code", "")
            line = issues[0].get("line", "")
            fp = f"{tool_name}:{posix}:{line}:{code}"
        elif isinstance(issues, dict):
            str_vals = [v for v in issues.values() if isinstance(v, str)]
            if str_vals and all(v not in ("FAILED", "ERROR") for v in str_vals):
                continue
            fp = f"{tool_name}:{posix}"
        else:
            fp = tool_name
        return fp.rstrip(":")
    return tool_name


def format_for_llm(
    tool_configs: dict,
    combined: CombinedToolResults,
    cq_invocation: str | None = None,
    context_lines: int = 15,
    hint: bool = False,
    limit: int = 1,
    silence: list[str] | None = None,
) -> str:
    """Return a markdown prompt describing the top `limit` defects from the worst-scoring tool."""
    result = _select_top_issue(tool_configs, combined, limit, silence or [])
    if result is None:
        return f"# No issues found\n\nOverall score: **{combined.score:.3f} / 1.0**"
    _, slices, _, parser = result
    return _build_message(slices, parser, context_lines, limit, hint, cq_invocation)


def format_for_llm_json(
    tool_configs: dict,
    combined: CombinedToolResults,
    cq_invocation: str | None = None,
    context_lines: int = 15,
    hint: bool = False,
    limit: int = 1,
    silence: list[str] | None = None,
) -> dict:
    """Like format_for_llm but returns a dict with id and file for automation use."""
    message = format_for_llm(tool_configs, combined, cq_invocation, context_lines, hint, limit, silence)
    result = _select_top_issue(tool_configs, combined, limit, silence or [])
    if result is None:
        return {"id": None, "file": None, "message": message}
    worst, slices, _, _ = result
    issue_id = _fingerprint_from_slice(worst.raw.tool_name, slices[0])
    file = Path(next(iter(slices[0].details), "")).as_posix() or None
    return {"id": issue_id, "file": file, "message": message}
