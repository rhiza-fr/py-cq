"""Parses output from interrogate into a standardized ToolResult.

Interrogate is invoked with ``-v --fail-under 0``, producing a table of
per-file docstring coverage on stdout::

    | src/foo.py  |  5 |  2 |  3 |  60% |
    | TOTAL       |  5 |  2 |  3 |  60.0% |

The parser extracts per-file coverage and the TOTAL row, storing the TOTAL
as the ``doc_coverage`` metric (0.0–1.0).
"""

import ast
import re
from pathlib import Path

from py_cq.localtypes import AbstractParser, RawResult, ToolResult

_ROW_RE = re.compile(r"^\|\s+(.+?)\s+\|\s+(\d+)\s+\|\s+(\d+)\s+\|\s+\d+\s+\|\s+(\d+(?:\.\d+)?)%\s*\|")
_CONTEXT_PATH_RE = re.compile(r'interrogate\s+"([^"]+)"')
_COVERAGE_FOR_RE = re.compile(r"Coverage for\s+(.+?)[\s=]*$")


def _missing_docstrings(file_path: Path) -> list[tuple[int, str, str]]:
    """Return (line, kind, source_line) for each node missing a docstring.

    kind is 'module', 'def', or 'class'. source_line is the verbatim text of
    the def/class line (for searching), or the first non-empty source line for
    the module.
    """
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except (OSError, SyntaxError):
        return []
    src_lines = source.splitlines()

    def src_line(lineno: int) -> str:
        return src_lines[lineno - 1].strip() if 0 < lineno <= len(src_lines) else ""

    def first_code_line() -> str:
        for ln in src_lines:
            stripped = ln.strip()
            if stripped and not stripped.startswith("#"):
                return stripped
        return ""

    results = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Module):
            if not ast.get_docstring(node):
                results.append((0, "module", first_code_line()))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not ast.get_docstring(node):
                results.append((node.lineno, "def", src_line(node.lineno)))
        elif isinstance(node, ast.ClassDef):
            if not ast.get_docstring(node):
                results.append((node.lineno, "class", src_line(node.lineno)))
    results.sort(key=lambda x: x[0])
    return results


def _is_file_empty(path: Path | None) -> bool:
    if path is None:
        return False
    try:
        return not path.read_text(encoding="utf-8").strip()
    except OSError:
        return False


def _resolve(context_path: str, rel_file: str) -> Path | None:
    """Return the first existing Path for rel_file, trying cwd then context_path."""
    direct = Path(rel_file)
    if direct.exists():
        return direct
    via_context = Path(context_path) / rel_file
    if via_context.exists():
        return via_context
    return None


class InterrogateParser(AbstractParser):
    """Parses raw output from ``interrogate -v`` into a ToolResult."""

    def parse(self, raw_result: RawResult) -> ToolResult:
        cm = _CONTEXT_PATH_RE.search(raw_result.command)
        context_path = cm.group(1) if cm else "."

        # Interrogate reports paths relative to the package root it discovers,
        # not relative to context_path. Parse the "Coverage for <dir>" header
        # to compute the prefix needed to make paths project-relative.
        prefix = ""
        for line in (raw_result.stdout or "").splitlines():
            hm = _COVERAGE_FOR_RE.search(line)
            if hm:
                coverage_root = hm.group(1).strip().rstrip("\\/")
                try:
                    rel = Path(coverage_root).resolve().relative_to(Path(context_path).resolve())
                    prefix = rel.as_posix()
                except ValueError:
                    pass
                break

        files: dict[str, dict] = {}
        for line in (raw_result.stdout or "").splitlines():
            m = _ROW_RE.match(line)
            if not m:
                continue
            name = m.group(1).strip().replace("\\", "/")
            total = int(m.group(2))
            miss = int(m.group(3))
            cover = float(m.group(4))
            if name != "TOTAL" and total > 0 and '.venv' not in name:
                file_key = f"{prefix}/{name}" if prefix else name
                files[file_key] = {
                    "total": total,
                    "missing": miss,
                    "coverage": cover / 100.0,
                }

        if self.parser_config.get("skip_empty_init", True):
            files = {
                f: d for f, d in files.items()
                if not (
                    Path(f).name == "__init__.py"
                    and _is_file_empty(_resolve(context_path, f))
                )
            }

        total_docs = sum(d["total"] for d in files.values())
        missing_docs = sum(d["missing"] for d in files.values())
        score = (total_docs - missing_docs) / total_docs if total_docs > 0 else 1.0
        return ToolResult(raw=raw_result, metrics={"doc_coverage": score}, details=files)

    def format_llm_message(self, tr: ToolResult, *, context_lines: int = 15, limit: int = 1) -> str:
        # Each call receives a single-file slice from _single_issue_slices
        files_with_missing = [(f, d) for f, d in tr.details.items() if isinstance(d, dict) and d.get("missing", 0) > 0]
        if not files_with_missing:
            score = tr.metrics.get("doc_coverage", 0)
            return f"**doc_coverage** score: {score:.3f}"

        m = _CONTEXT_PATH_RE.search(tr.raw.command)
        context_path = m.group(1) if m else "."

        rel_file, data = files_with_missing[0]
        miss = data.get("missing", 0)
        file_score = data.get("coverage", 0.0)
        resolved = _resolve(context_path, rel_file)
        nodes = _missing_docstrings(resolved) if resolved else []

        if not nodes:
            return f"{rel_file} — {file_score:.0%} doc coverage ({miss} undocumented)"

        lines = [f"{rel_file} — {file_score:.0%} doc coverage ({miss} missing). Add a docstring as the first statement of each:"]
        for lineno, kind, source_line in nodes:
            if kind == "module":
                before = f" (before `{source_line}`)" if source_line else ""
                lines.append(f"- module docstring at line 1{before}")
            else:
                lines.append(f"- line {lineno}: `{source_line}`")
        return "\n".join(lines)
