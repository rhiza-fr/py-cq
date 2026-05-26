"""Parses output from the ty type checker into a standardized ToolResult.

This module defines :class:`TyParser`, an implementation of
:class:`~.AbstractParser` that converts the raw stdout produced by
``ty check --output-format concise`` into a :class:`~.ToolResult`.

The concise output format is one diagnostic per line::

    <file>:<line>:<col>: <severity>[<code>] <message>

followed by a summary line ``Found N diagnostic`` or ``All checks passed!``.
Errors count more heavily than warnings toward the score."""

import re
from collections.abc import Callable
from pathlib import Path

from py_cq.localtypes import AbstractParser, RawResult, ToolResult
from py_cq.parsers.common import find_enclosing_function, format_issue_header, format_source_context, score_logistic_variant

_DIAG_RE = re.compile(r"^(.+):(\d+):\d+:\s+(error|warning)\[([^\]]+)\] (.+)$")
_EXPECTED_FOUND_RE = re.compile(r"Expected `([^`]+)`, found `([^`]+)`")
_CONTEXT_PATH_RE = re.compile(r'ty check[^"]*"([^"]+)"')
_DIRECTORY_RE = re.compile(r'--directory\s+"([^"]+)"')


def _resolve(context_path: str, rel_file: str) -> str:
    """Return the best resolvable path for rel_file, trying cwd, context_path, and its absolute form."""
    if Path(rel_file).exists():
        return rel_file
    for base in (Path(context_path), Path(context_path).resolve()):
        via = base / rel_file
        if via.exists():
            return str(via)
    return rel_file


def _format_invalid_argument_type(file: str, line: int, message: str) -> str:
    display_msg = re.sub(r": (Expected `)", r":\n\1", message)
    base = format_issue_header(file, line, "invalid-argument-type", display_msg) + format_source_context(file, line)
    m = _EXPECTED_FOUND_RE.search(message)
    if not m or "Unknown" not in m.group(2):
        return base
    enclosing = find_enclosing_function(file, line)
    note = "\n\n`Unknown` means ty cannot infer this argument's type — the variable has no annotation."
    if enclosing:
        note += f" Trace the argument back to its source and annotate its type:{enclosing}"
    else:
        note += " Annotate the variable's type or cast the argument explicitly."
    return base + note


_TYPE_NAME_RE = re.compile(r"Object of type `([^`]+)` is not callable")
_MODULE_RE = re.compile(r"Submodule `([^`]+)`")
_IMPORT_MODULE_RE = re.compile(r"Cannot resolve imported module `([^`]+)`")


def _format_call_non_callable(file: str, line: int, message: str) -> str:
    base = format_issue_header(file, line, "call-non-callable", message) + format_source_context(file, line, context=3, count=8)
    m = _TYPE_NAME_RE.search(message)
    type_name = f"`{m.group(1)}`" if m else "this type"
    return base + (
        f"\n\nty cannot see a `__call__` declaration on {type_name} — common when a library's "
        f"type stubs are incomplete. Fix: annotate the variable as `Callable[..., <ReturnType>]`, "
        f"or suppress with `# type: ignore[call-non-callable]` if the call is correct at runtime."
    )


def _format_possibly_missing_submodule(file: str, line: int, message: str) -> str:
    base = format_issue_header(file, line, "possibly-missing-submodule", message) + format_source_context(file, line, context=1, count=3)
    m = _MODULE_RE.search(message)
    submodule = m.group(1) if m else "the submodule"
    return base + f"\n\nFix: add `import <package>.{submodule}` before accessing it as an attribute."


def _format_unresolved_import(file: str, line: int, message: str) -> str:
    base = format_issue_header(file, line, "unresolved-import", message) + format_source_context(file, line, context=1, count=3)
    m = _IMPORT_MODULE_RE.search(message)
    module = f"`{m.group(1)}`" if m else "the module"
    return base + (
        f"\n\n{module} cannot be found. Check whether it has been renamed or deleted. "
        f"If it is no longer needed, remove the import. "
        f"If the module exists but is not installed, add it to your dependencies."
    )


_CUSTOM_FORMAT: dict[str, Callable[[str, int, str], str]] = {
    "call-non-callable": _format_call_non_callable,
    "invalid-argument-type": _format_invalid_argument_type,
    "possibly-missing-submodule": _format_possibly_missing_submodule,
    "unresolved-import": _format_unresolved_import,
}


class TyParser(AbstractParser):
    """Parses raw output from ``ty check`` into a structured ToolResult."""

    def parse(self, raw_result: RawResult) -> ToolResult:
        files: dict[str, list] = {}
        seen: set[tuple[str, int, str]] = set()
        weighted = 0
        for line in (raw_result.stdout or "").splitlines():
            m = _DIAG_RE.match(line)
            if m:
                path = m.group(1).replace("\\", "/")
                lineno = int(m.group(2))
                code = m.group(4)
                severity = m.group(3)
                key = (path, lineno, code)
                if key in seen:
                    continue
                seen.add(key)
                files.setdefault(path, []).append({
                    "line": lineno,
                    "code": code,
                    "severity": severity,
                    "message": m.group(5),
                })
                weighted += 3 if severity == "error" else 1

        score = score_logistic_variant(weighted, scale_factor=10)
        return ToolResult(raw=raw_result, metrics={"type_check": score}, details=files)

    def format_llm_message(self, tr: ToolResult, *, context_lines: int = 15, limit: int = 1) -> str:
        if not tr.details:
            return "ty reported issues (no details available)"
        file, issues = next(iter(tr.details.items()))
        if not isinstance(issues, list) or not issues:
            return "ty reported issues (no details available)"
        issue = issues[0]
        if not isinstance(issue, dict):
            return "ty reported issues (no details available)"
        line = issue.get("line", "?")
        code = issue.get("code", "")
        message = issue.get("message", "")
        cmd = tr.raw.command
        m_ctx = _CONTEXT_PATH_RE.search(cmd)
        context_path = m_ctx.group(1) if m_ctx else "."
        if context_path == ".":
            m_dir = _DIRECTORY_RE.search(cmd)
            if m_dir:
                context_path = m_dir.group(1)
        resolved_file = _resolve(context_path, file)
        fmt_fn = _CUSTOM_FORMAT.get(code)
        if fmt_fn and isinstance(line, int):
            return fmt_fn(resolved_file, line, message)
        return format_issue_header(resolved_file, line, code, message) + format_source_context(resolved_file, line, count=context_lines)
