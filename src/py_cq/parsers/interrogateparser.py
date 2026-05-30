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
from py_cq.parsers.common import extract_first_issue, format_issue_header, format_source_context

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
        """Return the stripped content of the source line at the given line number."""
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

        summaries: dict[str, dict] = {}
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
                summaries[file_key] = {"total": total, "missing": miss, "coverage": cover / 100.0}

        if self.parser_config.get("skip_empty_init", True):
            summaries = {
                f: d for f, d in summaries.items()
                if not (
                    Path(f).name == "__init__.py"
                    and _is_file_empty(_resolve(context_path, f))
                )
            }

        total_docs = sum(d["total"] for d in summaries.values())
        missing_docs = sum(d["missing"] for d in summaries.values())
        score = (total_docs - missing_docs) / total_docs if total_docs > 0 else 1.0

        # Build per-issue list details (sorted worst-first) so _fingerprint_from_slice
        # can produce a specific line+code fingerprint for is_fixed checks.
        files: dict[str, list] = {}
        for rel_file, summary in sorted(summaries.items(), key=lambda x: x[1]["coverage"]):
            if summary["missing"] == 0:
                continue
            resolved = _resolve(context_path, rel_file)
            nodes = _missing_docstrings(resolved) if resolved else []
            issues = []
            for lineno, kind, source_line in nodes:
                if kind == "module":
                    code, message = "D100", "missing module docstring"
                    lineno = 1
                elif kind == "class":
                    nm = re.search(r"class\s+(\w+)", source_line)
                    name = nm.group(1) if nm else source_line
                    code, message = "D101", f"missing docstring in class `{name}`"
                else:
                    nm = re.search(r"def\s+(\w+)", source_line)
                    name = nm.group(1) if nm else source_line
                    code, message = "D103", f"missing docstring in function `{name}`"
                issues.append({"line": lineno if lineno > 0 else 1, "code": code, "message": message})
            if issues:
                files[rel_file] = issues

        return ToolResult(raw=raw_result, metrics={"doc_coverage": score}, details=files)

    def format_llm_message(self, tr: ToolResult, *, context_lines: int = 15, limit: int = 1) -> str:
        result = extract_first_issue(tr.details)
        if result is None:
            score = tr.metrics.get("doc_coverage", 0)
            return f"**doc_coverage** score: {score:.3f}"

        m = _CONTEXT_PATH_RE.search(tr.raw.command)
        context_path = m.group(1) if m else "."

        rel_file, issue = result
        line = issue.get("line", 1)
        code = issue.get("code", "D100")
        message = issue.get("message", "missing docstring")

        resolved = _resolve(context_path, rel_file)
        file_str = str(resolved) if resolved else rel_file

        return format_issue_header(file_str, line, code, message) + format_source_context(file_str, line, count=context_lines)
