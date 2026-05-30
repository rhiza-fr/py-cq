"""Format the most important code quality defect as a markdown prompt for LLM consumption."""

import sys
from pathlib import Path
from typing import cast

from py_cq.localtypes import CombinedToolResults, Fingerprint, ToolConfig, ToolResult


def _severity(score: float, config: ToolConfig) -> int:
    """Return 0 (error), 1 (warning), or 2 (ok) for a given score and tool config."""
    if score < config.error_threshold:
        return 0
    if score < config.warning_threshold:
        return 1
    return 2


def _single_issue_slices(
    tr: ToolResult,
    limit: int,
    silence: list[str] | None = None,
    project_root: Path | None = None,
) -> list[ToolResult]:
    """Return up to `limit` ToolResults each containing one issue from tr.details.

    Returns empty list (not [tr]) when silence specs filter out all issues."""
    silence_set = set(silence or [])
    slices: list[ToolResult] = []
    has_list = any(isinstance(v, list) for v in tr.details.values())

    if has_list:
        for file, issues in tr.details.items():
            if isinstance(issues, list):
                for issue in issues:
                    candidate = ToolResult(raw=tr.raw, metrics=tr.metrics, details={file: [issue]}, project_path=tr.project_path)
                    if _fingerprint_from_slice(tr.raw.tool_name, candidate, project_root) in silence_set:
                        continue
                    slices.append(candidate)
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
            candidate = ToolResult(raw=tr.raw, metrics=tr.metrics, details={file: data}, project_path=tr.project_path)
            if _fingerprint_from_slice(tr.raw.tool_name, candidate, project_root) in silence_set:
                continue
            slices.append(candidate)
            if len(slices) >= limit:
                break
    return slices[:limit] or ([] if silence_set else [tr])


def _select_top_issue(
    tool_configs: dict,
    combined: CombinedToolResults,
    limit: int,
    silence: list[str],
    project_root: Path | None = None,
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
        slices = _single_issue_slices(candidate, limit, silence, project_root)
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


def _fingerprint_from_slice(tool_name: str, tr: ToolResult, project_root: Path | None = None) -> str:
    """Return fingerprint string for a single-issue ToolResult slice."""
    root = project_root.resolve() if project_root else None
    project_str = root.as_posix() if root else ""
    for file, issues in tr.details.items():
        if root:
            p = Path(file)
            resolved = (root / p).resolve() if not p.is_absolute() else p.resolve()
            try:
                path_str = resolved.relative_to(root).as_posix()
            except ValueError:
                path_str = resolved.as_posix()
        else:
            path_str = Path(file).as_posix()
        if isinstance(issues, list) and issues:
            first = issues[0]
            line = str(first.get("line", "")) if isinstance(first, dict) else ""
            code = first.get("code", "") if isinstance(first, dict) else ""
            fp = Fingerprint(tool=tool_name, project=project_str, path=path_str, line=line, code=code)
        elif isinstance(issues, dict):
            str_vals = [v for v in issues.values() if isinstance(v, str)]
            if str_vals and all(v not in ("FAILED", "ERROR") for v in str_vals):
                continue
            fp = Fingerprint(tool=tool_name, project=project_str, path=path_str)
        else:
            fp = Fingerprint(tool=tool_name, project=project_str, path="")
        return str(fp)
    return tool_name


def format_for_llm(
    tool_configs: dict,
    combined: CombinedToolResults,
    cq_invocation: str | None = None,
    context_lines: int = 15,
    hint: bool = False,
    limit: int = 1,
    silence: list[str] | None = None,
    project_root: Path | None = None,
) -> str:
    """Return a markdown prompt describing the top `limit` defects from the worst-scoring tool."""
    result = _select_top_issue(tool_configs, combined, limit, silence or [], project_root)
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
    project_root: Path | None = None,
) -> dict:
    """Like format_for_llm but returns a dict with id, file, project, and message for automation use."""
    message = format_for_llm(tool_configs, combined, cq_invocation, context_lines, hint, limit, silence, project_root)
    project = project_root.as_posix() if project_root else None
    result = _select_top_issue(tool_configs, combined, limit, silence or [], project_root)
    if result is None:
        return {"id": None, "file": None, "project": project, "message": message}
    worst, slices, _, _ = result
    issue_id = _fingerprint_from_slice(worst.raw.tool_name, slices[0], project_root)
    raw_file = next(iter(slices[0].details), "")
    if project_root and raw_file:
        try:
            file: str | None = Path(raw_file).resolve().relative_to(project_root).as_posix() or None
        except ValueError:
            file = Path(raw_file).as_posix() or None
    else:
        file = Path(raw_file).as_posix() or None
    return {"id": issue_id, "file": file, "project": project, "message": message}
