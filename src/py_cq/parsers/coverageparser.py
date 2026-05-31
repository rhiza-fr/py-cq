"""Parses raw coverage tool output into structured ToolResult instances with per-function granularity."""

import ast
import logging
from pathlib import Path

from py_cq.localtypes import AbstractParser, RawResult, ToolResult
from py_cq.parsers.common import find_function_source, resolve_path

log = logging.getLogger("cq")


def _parse_line_ranges(s: str) -> set[int]:
    """Parse a comma-separated string of line ranges and individual lines.

    Example: "1, 3-5, 10" -> {1, 3, 4, 5, 10}
    """
    result: set[int] = set()
    for part in s.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            try:
                result.update(range(int(lo), int(hi) + 1))
            except ValueError:
                pass
        elif part.isdigit():
            result.add(int(part))
    return result


def _get_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Return the signature of the function definition as a string."""
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    args = ast.unparse(node.args)
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"{prefix} {node.name}({args}){returns}"


def _extract_functions(file: str, missing_lines_str: str) -> list[tuple[str, int, str]]:
    """Return (name, lineno, signature) for functions whose bodies overlap with the missing line ranges."""
    try:
        source = Path(file).read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except (OSError, SyntaxError, ValueError):
        return []
    missing = _parse_line_ranges(missing_lines_str)
    seen: set[str] = set()
    result: list[tuple[str, int, str]] = []
    for node in sorted(ast.walk(tree), key=lambda n: getattr(n, "lineno", 0)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", node.lineno)
            if missing & set(range(node.lineno, end + 1)) and node.name not in seen:
                seen.add(node.name)
                result.append((node.name, node.lineno, _get_signature(node)))
    return result


def _find_test_file(source_file: str) -> str | None:
    """Return the test file path for source_file if a tests/ directory exists nearby."""
    candidate_name = f"test_{Path(source_file).stem}.py"
    try:
        for ancestor in Path(source_file).parents:
            try:
                tests_dir = ancestor / "tests"
                if tests_dir.is_dir():
                    return str(tests_dir / candidate_name).replace("\\", "/")
            except (OSError, ValueError):
                pass
    except (OSError, ValueError):
        pass
    return None


class CoverageParser(AbstractParser):
    """Parser for coverage results."""
    def parse(self, raw_result: RawResult) -> ToolResult:
        """Parse the coverage result."""
        tr = ToolResult(raw=raw_result, project_path=raw_result.project_path)
        lines = raw_result.stdout.splitlines()
        base_dir = raw_result.project_path

        file_data: dict[str, dict] = {}
        for line in lines:
            if "[" in line:
                continue
            parts = line.split()
            if len(parts) < 4 or not parts[3].endswith("%"):
                continue
            file_name = parts[0]
            try:
                coverage_pct = float(parts[3].rstrip("%")) / 100.0
            except ValueError:
                log.warning("Error parsing coverage percentage from line: %s", line)
                continue
            if file_name == "TOTAL":
                tr.metrics["coverage"] = coverage_pct
            else:
                try:
                    missing = int(parts[2])
                except (ValueError, IndexError):
                    missing = None
                missing_lines = " ".join(parts[4:]) if len(parts) > 4 else None
                file_data[file_name.replace("\\", "/")] = {
                    "coverage": coverage_pct,
                    "missing": missing,
                    "missing_lines": missing_lines,
                }

        # Build list-based details sorted worst-coverage-first so _single_issue_slices
        # picks the most urgent file and function first.
        details: dict[str, list] = {}
        for file_name, data in sorted(file_data.items(), key=lambda x: x[1].get("coverage", 1.0)):
            if data.get("missing") == 0:
                continue
            missing_lines_str = data.get("missing_lines")
            coverage_pct = data["coverage"]
            missing_count = data["missing"]
            resolved = resolve_path(base_dir, file_name)
            if missing_lines_str:
                funcs = _extract_functions(resolved, missing_lines_str)
                if funcs:
                    details[file_name] = [
                        {"code": name, "line": lineno, "signature": sig,
                         "file_coverage": coverage_pct, "missing": missing_count}
                        for name, lineno, sig in funcs
                    ]
                    continue
            # Fallback when --show-missing wasn't used or AST parsing failed
            details[file_name] = [{"code": None, "line": None, "missing": missing_count,
                                    "missing_lines": missing_lines_str, "file_coverage": coverage_pct}]

        tr.details = details
        return tr

    def format_llm_message(self, tr: ToolResult, *, context_lines: int = 15, limit: int = 1) -> str:
        for file, issues in tr.details.items():
            if not isinstance(issues, list) or not issues:
                continue
            issue = issues[0]
            if not isinstance(issue, dict):
                continue
            code = issue.get("code")
            line = issue.get("line")
            missing = issue.get("missing")
            file_coverage = issue.get("file_coverage", 0.0)
            missing_lines = issue.get("missing_lines")
            try:
                resolved_file = resolve_path(tr.project_path, file)
            except (OSError, ValueError):
                resolved_file = file

            parts: list[str] = []
            if code and line:
                parts.append(f"{file}:{line} - {code} is missing tests")
                fn_src = find_function_source(resolved_file, code)
                if fn_src:
                    parts.append(fn_src)
            else:
                pct = f"{file_coverage:.0%} " if isinstance(file_coverage, float) and file_coverage else ""
                miss_info = f"{missing} uncovered lines" if missing else "uncovered"
                parts.append(f"{file} - {pct}coverage ({miss_info})")
                if missing_lines:
                    parts.append(f"  missing lines: {missing_lines}")

            test_file = _find_test_file(file)
            if test_file:
                try:
                    resolved_test = resolve_path(tr.project_path, test_file)
                    last_line = len(Path(resolved_test).read_text(encoding="utf-8").splitlines())
                except (OSError, ValueError):
                    last_line = None
                location = f"{test_file} after line {last_line}" if last_line else test_file
                parts.append(f"\nAdd tests to: {location}")

            return "\n".join(parts)
        return ""
