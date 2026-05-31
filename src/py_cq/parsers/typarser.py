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

from py_cq.localtypes import AbstractParser, RawResult, ToolResult
from py_cq.parsers.common import extract_first_issue, find_enclosing_function, format_issue_header, format_source_context, resolve_path, score_logistic_variant

_DIAG_RE = re.compile(r"^(.+):(\d+):\d+:\s+(error|warning)\[([^\]]+)\] (.+)$")
_EXPECTED_FOUND_RE = re.compile(r"Expected `([^`]+)`, found `([^`]+)`")


def _format_invalid_argument_type(file: str, line: int, message: str) -> str:
    """Format a ty 'invalid-argument-type' diagnostic for LLM consumption.

    Includes hint text when ty reports ``Unknown`` as the found type.

    Args:
        file: Resolved file path.
        line: Line number of the diagnostic.
        message: The diagnostic message from ty.

    Returns:
        Markdown-formatted issue report with fix hints.
    """
    display_msg = re.sub(r": (Expected `)", r":\n\1", message)
    base = format_issue_header(file, line, "invalid-argument-type", display_msg) + format_source_context(file, line)
    m = _EXPECTED_FOUND_RE.search(message)
    if not m or "Unknown" not in m.group(2):
        return base
    enclosing = find_enclosing_function(file, line)
    note = "\n\n`Unknown` means ty cannot infer this argument's type - the variable has no annotation."
    if enclosing:
        note += f" Trace the argument back to its source and annotate its type:{enclosing}"
    else:
        note += " Annotate the variable's type or cast the argument explicitly."
    return base + note


_TYPE_NAME_RE = re.compile(r"Object of type `([^`]+)` is not callable")
_MODULE_RE = re.compile(r"Submodule `([^`]+)`")
_IMPORT_MODULE_RE = re.compile(r"Cannot resolve imported module `([^`]+)`")


def _format_call_non_callable(file: str, line: int, message: str) -> str:
    """Format a ty 'call-non-callable' diagnostic for LLM consumption.

    Provides fix advice about incomplete type stubs and Callable annotations.

    Args:
        file: Resolved file path.
        line: Line number of the diagnostic.
        message: The diagnostic message from ty.

    Returns:
        Markdown-formatted issue report with fix hints.
    """
    base = format_issue_header(file, line, "call-non-callable", message) + format_source_context(file, line, context=3, count=8)
    m = _TYPE_NAME_RE.search(message)
    type_name = f"`{m.group(1)}`" if m else "this type"
    return base + (
        f"\n\nty cannot see a `__call__` declaration on {type_name} - common when a library's "
        f"type stubs are incomplete. Fix: annotate the variable as `Callable[..., <ReturnType>]`, "
        f"or suppress with `# type: ignore[call-non-callable]` if the call is correct at runtime."
    )


def _format_possibly_missing_submodule(file: str, line: int, message: str) -> str:
    """Format a ty 'possibly-missing-submodule' diagnostic for LLM consumption.

    Advises adding an explicit import for the submodule before attribute access.

    Args:
        file: Resolved file path.
        line: Line number of the diagnostic.
        message: The diagnostic message from ty.

    Returns:
        Markdown-formatted issue report with fix hints.
    """
    base = format_issue_header(file, line, "possibly-missing-submodule", message) + format_source_context(file, line, context=1, count=3)
    m = _MODULE_RE.search(message)
    submodule = m.group(1) if m else "the submodule"
    return base + f"\n\nFix: add `import <package>.{submodule}` before accessing it as an attribute."


def _format_unresolved_import(file: str, line: int, message: str) -> str:
    """Format a ty 'unresolved-import' diagnostic for LLM consumption.

    Advises checking whether the module was renamed, deleted, or needs installation.

    Args:
        file: Resolved file path.
        line: Line number of the diagnostic.
        message: The diagnostic message from ty.

    Returns:
        Markdown-formatted issue report with fix hints.
    """
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
        return ToolResult(raw=raw_result, metrics={"type_check": score}, details=files,
                          project_path=raw_result.project_path)

    def format_llm_message(self, tr: ToolResult, *, context_lines: int = 15, limit: int = 1) -> str:
        """Return a markdown description of the most important ty defect.

        Delegates to a custom formatter when the code has a registered handler
        in ``_CUSTOM_FORMAT`` (e.g. ``call-non-callable``, ``invalid-argument-type``),
        otherwise falls back to the standard header + source context format.

        Args:
            tr: The parsed tool result containing details and raw output.
            context_lines: Number of source context lines to show.
            limit: Maximum number of issues to display (unused - always 1).

        Returns:
            Markdown-formatted issue description.
        """
        result = extract_first_issue(tr.details)
        if result is None:
            return "ty reported issues (no details available)"
        file, issue = result
        line = issue.get("line", "?")
        code = issue.get("code", "")
        message = issue.get("message", "")
        resolved_file = resolve_path(tr.project_path, file)
        fmt_fn = _CUSTOM_FORMAT.get(code)
        if fmt_fn and isinstance(line, int):
            return fmt_fn(resolved_file, line, message)
        return format_issue_header(resolved_file, line, code, message) + format_source_context(resolved_file, line, count=context_lines)
