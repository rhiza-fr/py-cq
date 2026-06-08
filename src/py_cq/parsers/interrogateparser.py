"""Parses output from interrogate into a standardized ToolResult.

Interrogate is invoked with ``-v --fail-under 0``, producing a table of
per-file docstring coverage on stdout::

    | src/foo.py  |  5 |  2 |  3 |  60% |
    | TOTAL       |  5 |  2 |  3 |  60.0% |

The parser extracts per-file coverage and the TOTAL row, storing the TOTAL
as the ``doc_coverage`` metric (0.0-1.0).
"""

import ast
import re
import tomllib
from pathlib import Path

from py_cq.localtypes import AbstractParser, RawResult, ToolResult
from py_cq.parsers.common import (
    extract_first_issue,
    format_issue_header,
    format_source_context,
)
from py_cq.source_file import get_source

_SKIP_PARAMS = {"self", "cls"}


def _format_missing_docstring(file_str: str, line: int, code: str, message: str) -> str:
    base = format_issue_header(file_str, line, code, message) + format_source_context(
        file_str, line
    )

    if code == "D100":
        return base + "\n\nInsert a module-level docstring as the very first statement in the file."

    try:
        tree = get_source(file_str).tree
    except OSError:
        tree = None
    if tree is None:
        return base + "\n\nInsert a docstring as the first statement in the body."

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.lineno == line:
            insert_line = node.body[0].lineno
            return (
                base
                + f"\n\nInsert a docstring on line {insert_line} (first line of the class body)."
                + "\n\nA good class docstring describes the class purpose in one sentence."
            )
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.lineno == line
        ):
            insert_line = node.body[0].lineno
            params = [a.arg for a in node.args.args if a.arg not in _SKIP_PARAMS]
            returns = ast.unparse(node.returns) if node.returns else None

            hint = f"\n\nInsert a docstring on line {insert_line} (first line of the function body)."
            hint += "\n\nA good one-line docstring describes what the function does (not how)."

            indent = "    "
            if returns:
                hint += f' Return annotation is `{returns}` - start the docstring with a verb like "Return ...".'
                hint += f'\n\nExample:\n```python\n{indent}"""Return the <value> for <reason>."""\n```'
            else:
                hint += f'\n\nExample:\n```python\n{indent}"""Do <action> and return <result>."""\n```'

            if params:
                hint += f"\n\nDocument non-obvious parameters: {', '.join(f'`{p}`' for p in params)}."

            return base + hint

    return base + "\n\nInsert a docstring as the first statement in the body."

_ROW_RE = re.compile(
    r"^\|\s+(.+?)\s+\|\s+(\d+)\s+\|\s+(\d+)\s+\|\s+\d+\s+\|\s+(\d+(?:\.\d+)?)%\s*\|"
)
_CONTEXT_PATH_RE = re.compile(r'interrogate\s+"([^"]+)"')
_COVERAGE_FOR_RE = re.compile(r"Coverage for\s+(.+?)[\s=]*$")


def _load_interrogate_cfg(context_path: str) -> dict:
    """Read [tool.interrogate] from the nearest pyproject.toml."""
    p = Path(context_path).resolve()
    for candidate in [p, *p.parents]:
        pyproject = (candidate if candidate.is_dir() else candidate.parent) / "pyproject.toml"
        if pyproject.exists():
            try:
                data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
                return data.get("tool", {}).get("interrogate", {})
            except Exception:
                return {}
    return {}


def _skip_node(name: str, cfg: dict) -> bool:
    """Return True if interrogate would skip this name given cfg."""
    is_magic = name.startswith("__") and name.endswith("__")
    is_private = name.startswith("__") and not name.endswith("__")
    is_semiprivate = name.startswith("_") and not name.startswith("__")
    if name == "__init__" and cfg.get("ignore-init-method"):
        return True
    if is_magic and cfg.get("ignore-magic"):
        return True
    if is_private and cfg.get("ignore-private"):
        return True
    if is_semiprivate and cfg.get("ignore-semiprivate"):
        return True
    return False


def _missing_docstrings(file_path: Path, cfg: dict | None = None) -> list[tuple[int, str, str]]:
    """Return (line, kind, source_line) for each node missing a docstring.

    kind is 'module', 'def', or 'class'. source_line is the verbatim text of
    the def/class line (for searching), or the first non-empty source line for
    the module.
    """
    try:
        sf = get_source(str(file_path))
        tree = sf.tree
    except OSError:
        return []
    if tree is None:
        return []
    src_lines = sf.text.splitlines()

    def src_line(lineno: int) -> str:
        """Return the stripped content of the source line at the given line number."""
        return src_lines[lineno - 1].strip() if 0 < lineno <= len(src_lines) else ""

    def first_code_line() -> str:
        """Return the first non-empty, non-comment line of the source."""
        for ln in src_lines:
            stripped = ln.strip()
            if stripped and not stripped.startswith("#"):
                return stripped
        return ""

    effective_cfg = cfg or {}
    results = []
    if not sf.module_has_docstring:
        results.append((0, "module", first_code_line()))
    for d in sf.definitions:
        if d.has_docstring or _skip_node(d.name, effective_cfg):
            continue
        kind = "def" if d.kind == "function" else "class"
        results.append((d.lineno, kind, src_line(d.lineno)))
    results.sort(key=lambda x: x[0])
    return results


def _is_file_empty(path: Path | None) -> bool:
    """Check if the file is empty."""
    if path is None:
        return False
    try:
        return not path.read_text(encoding="utf-8").strip()
    except OSError:
        return False


def _resolve(context_path: str, rel_file: str) -> Path | None:
    """Return the first existing Path for rel_file, trying context_path then cwd."""
    via_context = Path(context_path) / rel_file
    if via_context.exists():
        return via_context
    # When context_path is a file, interrogate reports only the basename.
    # Try the parent directory so "dig.py" resolves against "D:/.../dig.py".
    via_parent = Path(context_path).parent / rel_file
    if via_parent.exists():
        return via_parent
    direct = Path(rel_file)
    if direct.exists():
        return direct
    return None


class InterrogateParser(AbstractParser):
    """Parses raw output from ``interrogate -v`` into a ToolResult."""

    def parse(self, raw_result: RawResult) -> ToolResult:
        cm = _CONTEXT_PATH_RE.search(raw_result.command)
        context_path = cm.group(1) if cm else "."
        interrogate_cfg = _load_interrogate_cfg(context_path)

        # Interrogate reports paths relative to the package root it discovers,
        # not relative to context_path. Parse the "Coverage for <dir>" header
        # to compute the prefix needed to make paths project-relative.
        prefix = ""
        for line in (raw_result.stdout or "").splitlines():
            hm = _COVERAGE_FOR_RE.search(line)
            if hm:
                coverage_root = hm.group(1).strip().rstrip("\\/")
                try:
                    rel = (
                        Path(coverage_root)
                        .resolve()
                        .relative_to(Path(context_path).resolve())
                    )
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
            if name != "TOTAL" and total > 0 and ".venv" not in name:
                file_key = f"{prefix}/{name}" if prefix else name
                summaries[file_key] = {
                    "total": total,
                    "missing": miss,
                    "coverage": cover / 100.0,
                }

        if self.parser_config.get("skip_empty_init", True):
            summaries = {
                f: d
                for f, d in summaries.items()
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
        for rel_file, summary in sorted(
            summaries.items(), key=lambda x: x[1]["coverage"]
        ):
            if summary["missing"] == 0:
                continue
            resolved = _resolve(context_path, rel_file)
            nodes = _missing_docstrings(resolved, interrogate_cfg) if resolved else []
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
                issues.append(
                    {
                        "line": lineno if lineno > 0 else 1,
                        "code": code,
                        "message": message,
                    }
                )
            if issues:
                files[rel_file] = issues

        return ToolResult(
            raw=raw_result, metrics={"doc_coverage": score}, details=files
        )

    def format_llm_message(
        self, tr: ToolResult, *, context_lines: int = 15, limit: int = 1
    ) -> str:
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

        return _format_missing_docstring(file_str, line, code, message)
