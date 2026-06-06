"""Parses output from ruff check into a standardized ToolResult.

This module defines :class:`RuffParser`, an implementation of
:class:`~.AbstractParser` that converts the raw stdout produced by
``ruff check --output-format concise`` into a :class:`~.ToolResult`.

The concise output format is one violation per line::

    <file>:<line>:<col>: <CODE> <message>

followed by a summary line ``Found N error.`` or ``All checks passed!``."""

import re
from collections.abc import Callable
from pathlib import Path

from py_cq.localtypes import AbstractParser, RawResult, ToolResult
from py_cq.parsers.common import (
    enclosing_function_range,
    extract_first_issue,
    find_enclosing_function,
    format_issue_header,
    format_source_context,
    score_logistic_variant,
)

_DIAG_RE = re.compile(r"^(.+):(\d+):(\d+): ([A-Z]{1,5}\d+) (.+)$")
_VARNAME_RE = re.compile(r"[`'](\w+)[`']")


def _format_F841(file: str, line: int, message: str) -> str:
    """Unused variable: show source context, then report same-function references or advise deletion."""
    base = format_issue_header(file, line, "F841", message) + format_source_context(
        file, line
    )
    m = _VARNAME_RE.search(message)
    if not m:
        return base
    var = m.group(1)
    try:
        lines = Path(file).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return base
    func_range = enclosing_function_range(file, line)
    var_re = re.compile(rf"\b{re.escape(var)}\b")
    refs = [
        i + 1
        for i, ln in enumerate(lines)
        if i + 1 != line
        and var_re.search(ln)
        and (func_range is None or func_range[0] <= i + 1 <= func_range[1])
    ]
    if refs and len(var) > 1:
        ref_str = ", ".join(str(r) for r in refs[:8])
        return (
            base
            + f"\n\n`{var}` is also referenced at line(s): {ref_str}. Determine whether this assignment should feed into those uses or is redundant."
        )
    return (
        base
        + f"\n\n`{var}` is not referenced anywhere else in this function. Delete line {line}."
    )


def _format_F541(file: str, line: int, message: str) -> str:
    """Format F541 error message."""
    base = format_issue_header(file, line, "F541", message) + format_source_context(
        file, line
    )
    return base + "\n\nFix: remove the `f` prefix from this string literal."


def _file_refs(file: str, name: str, exclude_line: int) -> list[tuple[int, str]]:
    """Return (line_no, stripped_text) for every line in file containing `name` as a word."""
    try:
        lines = Path(file).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    name_re = re.compile(rf"\b{re.escape(name)}\b")
    return [
        (i + 1, ln.strip())
        for i, ln in enumerate(lines)
        if i + 1 != exclude_line and name_re.search(ln)
    ]


def _format_F401(file: str, line: int, message: str) -> str:
    """Unused import: warn if name appears elsewhere (string annotations, __all__), else confirm safe delete."""
    autofixable = "[*]" in message
    clean_message = re.sub(r"^\[\*\]\s*", "", message)
    base = format_issue_header(
        file, line, "F401", clean_message
    ) + format_source_context(file, line)
    m = re.search(r"`([^`]+)`", clean_message)
    if not m:
        return base
    # "typing.Optional" -> bound name is "Optional"; "os" -> "os"
    name = m.group(1).split(".")[-1]
    refs = _file_refs(file, name, exclude_line=line)
    if refs:
        ref_lines = "\n".join(f"  line {line_no}: {txt}" for line_no, txt in refs[:6])
        return (
            base
            + f"\n\n`{name}` appears elsewhere in this file - verify these are not active uses before deleting:\n{ref_lines}"
        )
    suffix = " Auto-fixable: `ruff check --fix`." if autofixable else ""
    return base + f"\n\nNo other uses found. Delete this import.{suffix}"


def _format_F821(file: str, line: int, message: str) -> str:
    """Undefined name: show enclosing function and all in-file references to help diagnose the gap."""
    base = format_issue_header(file, line, "F821", message) + format_source_context(
        file, line
    )
    m = re.search(r"`(\w+)`", message)
    if not m:
        return base
    name = m.group(1)
    refs = _file_refs(file, name, exclude_line=line)
    enclosing = find_enclosing_function(file, line)
    if refs:
        ref_lines = "\n".join(f"  line {line_no}: {txt}" for line_no, txt in refs[:8])
        base += f"\n\nOther references to `{name}` in this file:\n{ref_lines}"
    else:
        base += f"\n\n`{name}` is not imported or defined anywhere else in this file."
    if enclosing and enclosing not in base:
        base += f"\n\nEnclosing function:{enclosing}"
    return base


def _format_E701(file: str, line: int, message: str) -> str:
    base = format_issue_header(file, line, "E701", message) + format_source_context(
        file, line, context=2, count=4
    )
    return base + "\n\nFix: split the second statement onto its own line."


def _format_E721(file: str, line: int, message: str) -> str:
    base = format_issue_header(file, line, "E721", message) + format_source_context(
        file, line, context=2, count=4
    )
    return base + (
        "\n\nFix: if comparing a type-holding variable against a type literal, use `is` "
        "(e.g. `output_type is str`). If checking the type of a value, use `isinstance()` "
        "(e.g. `isinstance(x, str)`)."
    )


_CUSTOM_FORMAT: dict[str, Callable[[str, int, str], str]] = {
    "E701": _format_E701,
    "E721": _format_E721,
    "F401": _format_F401,
    "F541": _format_F541,
    "F821": _format_F821,
    "F841": _format_F841,
}


class RuffParser(AbstractParser):
    """Parses raw output from ``ruff check`` into a structured ToolResult."""

    def parse(self, raw_result: RawResult) -> ToolResult:
        """Parse concise ruff output and return a ToolResult.

        Args:
            raw_result: Raw output from ``ruff check --output-format concise``.

        Returns:
            ToolResult with a ``lint`` metric in [0, 1] and per-file violations in details.
        """
        files: dict[str, list] = {}
        for line in (raw_result.stdout or "").splitlines():
            m = _DIAG_RE.match(line)
            if m:
                path = m.group(1).replace("\\", "/")
                files.setdefault(path, []).append(
                    {
                        "line": int(m.group(2)),
                        "col": int(m.group(3)),
                        "code": m.group(4),
                        "message": m.group(5),
                    }
                )
        score = score_logistic_variant(
            sum(len(v) for v in files.values()), scale_factor=20
        )
        return ToolResult(raw=raw_result, metrics={"lint": score}, details=files)

    def format_llm_message(
        self, tr: ToolResult, *, context_lines: int = 15, limit: int = 1
    ) -> str:
        """Return the first lint violation as a defect description."""
        result = extract_first_issue(tr.details)
        if result is None:
            return "ruff reported issues (no details available)"
        file, issue = result
        line = issue.get("line", "?")
        code = issue.get("code", "")
        message = issue.get("message", "")
        fmt_fn = _CUSTOM_FORMAT.get(code)
        if fmt_fn and isinstance(line, int):
            return fmt_fn(file, line, message)
        return format_issue_header(file, line, code, message) + format_source_context(
            file, line, count=context_lines
        )
