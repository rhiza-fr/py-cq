"""Parses output from vulture dead-code detector into a standardized ToolResult.

Vulture is invoked with ``--min-confidence 60``, producing one text line
per unused symbol::

    src/foo.py:10: unused function 'bar' (60% confidence)

60% is the confidence vulture gives unused functions, classes, methods and
variables, so anything higher only reports unused imports and unreachable
code. At that level vulture cannot see dynamic use, so the LLM message for a
finding below 80% says how to keep the symbol instead of deleting it.

Typed fields in a class body (``name: type`` or ``name: type = value``) are
dropped: pydantic models, dataclasses, TypedDicts, NamedTuples and attrs
classes read them through the class, never by name, so vulture always
reports them as unused variables.

The parser counts violations and converts the count into a logistic-variant
score stored under the ``dead_code`` metric key.
"""

import ast
import re

from py_cq.localtypes import AbstractParser, RawResult, ToolResult
from py_cq.parsers.common import (
    extract_first_issue,
    format_source_context,
    resolve_path,
    score_logistic_variant,
)
from py_cq.source_file import get_source

_LINE_RE = re.compile(r"^(.+):(\d+): (unused \S+) '(.+)' \((\d+)% confidence\)$")

_CERTAIN = 80
_KEEP_HINT = (
    "\n\nRemove it if nothing uses it. If it is public API or is used dynamically,"
    ' keep it and add `"{name}"` to `ignore_names` under `[tool.vulture]` in'
    " `pyproject.toml`."
)


def _class_field_lines(path: str) -> set[int]:
    """Return line numbers of typed field declarations directly in a class body."""
    try:
        tree = get_source(path).tree
    except OSError:
        return set()
    if tree is None:
        return set()
    return {
        stmt.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        for stmt in node.body
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
    }


class VultureParser(AbstractParser):
    """Parses raw text output from ``vulture`` into a ToolResult."""

    def parse(self, raw_result: RawResult) -> ToolResult:
        """Parses the raw text output from vulture."""
        files: dict[str, list] = {}
        for line in (raw_result.stdout or "").splitlines():
            m = _LINE_RE.match(line)
            if m:
                path = m.group(1).replace("\\", "/")
                files.setdefault(path, []).append(
                    {
                        "line": int(m.group(2)),
                        "type": m.group(3),
                        "name": m.group(4),
                        "confidence": int(m.group(5)),
                    }
                )
        for path, issues in list(files.items()):
            if not any(i["type"] == "unused variable" for i in issues):
                continue
            fields = _class_field_lines(resolve_path(raw_result.project_path, path))
            kept = [
                i
                for i in issues
                if not (i["type"] == "unused variable" and i["line"] in fields)
            ]
            if kept:
                files[path] = kept
            else:
                del files[path]
        count = sum(len(v) for v in files.values())
        score = score_logistic_variant(count, scale_factor=15)
        return ToolResult(raw=raw_result, metrics={"dead_code": score}, details=files)

    def format_llm_message(
        self, tr: ToolResult, *, context_lines: int = 15, limit: int = 1
    ) -> str:
        """Formats the LLM message from the ToolResult."""
        result = extract_first_issue(tr.details)
        if result is None:
            return "vulture reported issues (no details available)"
        file, issue = result
        line = issue.get("line", "?")
        kind = issue.get("type", "unused")
        name = issue.get("name", "")
        confidence = issue.get("confidence", "?")
        message = f"{file}:{line} - **{kind}** `{name}` ({confidence}% confidence){format_source_context(file, line, count=context_lines)}"
        if isinstance(confidence, int) and confidence < _CERTAIN:
            message += _KEEP_HINT.format(name=name)
        return message
