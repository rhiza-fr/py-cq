"""Utility functions for normalising numeric values and scoring error magnitudes.

This module provides two small helpers that are often used when working with
performance metrics or error scores:

* :func:`inv_normalize` - Inversely normalises a value relative to a maximum
  reference, yielding a float in the interval [0,\u202f1].
* :func:`score_logistic_variant` - Maps an error magnitude to a bounded score
  using a logistic-style curve, with optional parameters controlling the scale
  and steepness of the transition.

Both functions return a float and can be used directly in downstream analytics,
visualisation or decision-making pipelines."""

import json
import re
from pathlib import Path


def read_source_lines(file_path: str, line: int, count: int = 5) -> str:
    """Return up to `count` source lines starting at the given 1-based line number."""
    try:
        all_lines = (
            Path(file_path).read_text(encoding="utf-8", errors="replace").splitlines()
        )
        start = max(0, line - 1)
        return "\n".join(all_lines[start : start + count])
    except (OSError, ValueError):
        return ""


def format_source_context(
    file: str, line: int | str, context: int = 3, count: int = 8
) -> str:
    """Return a fenced python code block for the source around `line`, or '' if unavailable.

    Stops before spilling into the next top-level ``def`` or ``class`` definition.
    """
    if not isinstance(line, int):
        return ""
    context_start = max(1, line - context)
    raw_lines = read_source_lines(file, context_start, count=count).splitlines()
    if not raw_lines:
        return ""
    error_offset = line - context_start  # 0-based index of the error line in raw_lines
    collected = []
    for i, rline in enumerate(raw_lines):
        if i > error_offset and (
            rline.startswith("def ")
            or rline.startswith("async def ")
            or rline.startswith("class ")
        ):
            break
        collected.append(f"{context_start + i}: {rline}")
    src = "\n".join(collected)
    return f"\n```python\n{src}\n```"


_PYTHON_KEYWORDS = frozenset(
    [
        "if",
        "elif",
        "else",
        "for",
        "while",
        "with",
        "assert",
        "return",
        "raise",
        "import",
        "from",
        "class",
        "def",
        "lambda",
        "yield",
        "del",
        "pass",
        "break",
        "continue",
        "not",
        "and",
        "or",
        "in",
        "is",
        "print",
        "super",
        "type",
        "len",
        "range",
    ]
)


def extract_callee_name(source_line: str) -> str | None:
    """Extract the primary callee function name from a source line, or None.

    Prefers the RHS of an assignment so that ``result = func(...)`` returns
    ``func`` rather than the variable on the left.  Python keywords and
    built-ins listed in ``_PYTHON_KEYWORDS`` are excluded.
    """
    stripped = source_line.strip()
    rhs = stripped
    if "=" in stripped and not stripped.startswith(("assert", "return")):
        rhs = stripped.split("=", 1)[1].strip()
    m = re.search(r"\b([a-zA-Z_]\w*)\s*\(", rhs)
    if m and m.group(1) not in _PYTHON_KEYWORDS and len(m.group(1)) > 1:
        return m.group(1)
    return None


def _find_project_root(hint_file: str) -> Path:
    root = Path(hint_file).resolve().parent
    current = root
    for _ in range(8):
        if (current / "pyproject.toml").exists() or (current / "setup.py").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return root


_SKIP_DIRS = {
    ".venv",
    "venv",
    "__pycache__",
    ".git",
    "node_modules",
    ".tox",
    "dist",
    "build",
}


def find_in_project(
    func_name: str, hint_file: str, max_lines: int = 10
) -> tuple[str, str]:
    """Find func_name definition in project files; same file first, then project-wide.

    Returns ``(file_path, code_block)`` for the first match, or ``("", "")`` if not found.
    """
    result = find_function_source(hint_file, func_name, max_lines=max_lines)
    if result:
        return hint_file, result
    root = _find_project_root(hint_file)
    for py_file in sorted(root.rglob("*.py")):
        if any(part in _SKIP_DIRS for part in py_file.parts):
            continue
        if py_file.resolve() == Path(hint_file).resolve():
            continue
        r = find_function_source(str(py_file), func_name, max_lines=max_lines)
        if r:
            return str(py_file), r
    return "", ""


def _relative_path(path: str) -> str:
    """Return path relative to project root if possible, otherwise absolute. Forward slashes."""
    try:
        resolved = Path(path).resolve()
    except (OSError, ValueError):
        return path.replace("\\", "/")
    try:
        return resolved.relative_to(_find_project_root(path)).as_posix()
    except ValueError:
        return resolved.as_posix()


def format_issue_header(file: str, line: int, code: str, message: str) -> str:
    """Return a clean single-line issue header: path:line - CODE: message."""
    return f"{_relative_path(file)}:{line} - {code}: {message}"


def format_callee_context(func_name: str, hint_file: str, max_lines: int = 10) -> str:
    """Return a labelled callee definition block, or '' if not found in project.

    Output format::

        Callee `func_name` - `relative/path/to/file.py`
        ```python
        N: def func_name(...):
        ...
        ```
    """
    callee_file, code_block = find_in_project(func_name, hint_file, max_lines=max_lines)
    if not code_block:
        return ""
    m = re.search(r"```python\n(\d+):", code_block)
    line_ref = f":{m.group(1)}" if m else ""
    return f"\n`{func_name}` is defined at: `{_relative_path(callee_file)}{line_ref}`{code_block}"


def enclosing_function_range(file: str, line: int) -> tuple[int, int] | None:
    """Return (start_line, end_line) 1-based for the function enclosing `line`, or None."""
    try:
        all_lines = Path(file).read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError):
        return None
    if line < 1 or line > len(all_lines):
        return None
    target_idx = line - 1
    target_indent = len(all_lines[target_idx]) - len(all_lines[target_idx].lstrip())
    def_re = re.compile(r"^(\s*)(?:async\s+)?def\s+")
    start_idx = baseline_indent = None
    for i in range(target_idx - 1, -1, -1):
        m = def_re.match(all_lines[i])
        if m:
            indent = len(m.group(1))
            if indent < target_indent:
                start_idx, baseline_indent = i, indent
                break
    if start_idx is None or baseline_indent is None:
        return None
    end_idx = start_idx
    in_body = ":" in all_lines[start_idx].split("#")[0]
    for i, ln in enumerate(all_lines[start_idx + 1 :], start=start_idx + 1):
        stripped = ln.lstrip()
        if not in_body:
            if ":" in ln.split("#")[0]:
                in_body = True
            end_idx = i
        else:
            if stripped and len(ln) - len(stripped) <= baseline_indent:
                break
            end_idx = i
    return (start_idx + 1, end_idx + 1)


def find_enclosing_function(file: str, line: int, max_lines: int = 50) -> str:
    """Return a fenced python block for the function enclosing 1-based `line`, or '' if not found."""
    r = enclosing_function_range(file, line)
    if r is None:
        return ""
    start_line, end_line = r
    try:
        all_lines = Path(file).read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError):
        return ""
    start_idx = start_line - 1
    collected = list(all_lines[start_idx : min(end_line, start_idx + max_lines)])
    while collected and not collected[-1].strip():
        collected.pop()
    numbered = "\n".join(f"{start_line + i}: {ln}" for i, ln in enumerate(collected))
    return f"\n```python\n{numbered}\n```"


def find_function_source(file: str, func_name: str, max_lines: int = 15) -> str:
    """Return a fenced python block for the body of func_name, or '' if unavailable."""
    try:
        all_lines = Path(file).read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError):
        return ""
    pattern = re.compile(rf"^(\s*)(?:async\s+)?def\s+{re.escape(func_name)}\s*\(")
    match_result: tuple[int, int] | None = None
    for i, line in enumerate(all_lines):
        m = pattern.match(line)
        if m:
            match_result = (i, len(m.group(1)))
            break
    if match_result is None:
        return ""
    start_idx, baseline_indent = match_result
    collected = [all_lines[start_idx]]
    in_docstring = False
    docstring_marker: str | None = None
    past_docstring = False
    for line in all_lines[start_idx + 1 :]:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if stripped and indent <= baseline_indent:
            break
        if not past_docstring:
            if not in_docstring:
                quote = next(
                    (q for q in ('"""', "'''") if stripped.startswith(q)), None
                )
                if quote:
                    in_docstring = quote not in stripped[3:]
                    past_docstring = not in_docstring
                    docstring_marker = quote
                    continue
                past_docstring = bool(stripped)
            else:
                if docstring_marker and docstring_marker in stripped:
                    in_docstring = False
                    past_docstring = True
                continue
        collected.append(line)
        if len(collected) >= max_lines:
            break
    while collected and not collected[-1].strip():
        collected.pop()
    numbered = "\n".join(f"{start_idx + 1 + i}: {ln}" for i, ln in enumerate(collected))
    return f"\n```python\n{numbered}\n```"


def resolve_path(base: str, rel_file: str) -> str:
    """Return (base / rel_file) as a posix string; return rel_file unchanged if absolute or base is empty."""
    if not base or not rel_file:
        return rel_file
    try:
        p = Path(rel_file)
        if p.is_absolute():
            return rel_file
        return (Path(base) / rel_file).as_posix()
    except (OSError, ValueError):
        return rel_file


def parse_json_dict(stdout: str) -> dict | None:
    """Parse stdout as a JSON object; return None if invalid or not a dict."""
    try:
        data = json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def extract_first_issue(details: dict) -> tuple[str, dict] | None:
    """Return (file, issue) from the first list-typed entry in details, or None."""
    if not details:
        return None
    file, issues = next(iter(details.items()))
    if not isinstance(issues, list) or not issues:
        return None
    issue = issues[0]
    return (file, issue) if isinstance(issue, dict) else None


def inv_normalize(value: float, max_value: float) -> float:
    """Returns the inverse normalized value of `value` relative to `max_value`.

    When *max_value* is zero the result is defined as 1.0 (no deviation from a
    zero-sized reference).
    """
    if max_value == 0:
        return 1.0
    return (max_value - min(value, max_value)) / max_value


def score_logistic_variant(
    errors, scale_factor: float = 30, steepness: float = 2
) -> float:
    """Calculate a logistic-variant score from an error value.

    The score is always in the range ``[0.0, 1.0]`` and decreases monotonically
    as the magnitude of the error increases. Negative errors are treated as
    zero.  A special case occurs when ``scale_factor`` is ``0``: the method
    returns ``1.0`` only when the error is exactly zero; otherwise it returns
    ``0.0``.

    The logistic function is computed as::

        1 / (1 + (errors / scale_factor) ** steepness)

    To avoid numerical overflow, the intermediate term is capped at
    ``float('inf')`` when ``errors / scale_factor`` exceeds
    ``709 / steepness`` (the largest value that can be exponentiated
    without raising an :class:`OverflowError`).

    Args:
        errors (float): The error magnitude to score.  Negative values are
            treated as zero.
        scale_factor (float, optional): Scaling factor applied to the error.
            Defaults to ``30``.  When ``0``, the special case described above
            applies.
        steepness (float, optional): Exponent controlling the steepness of
            the logistic curve. Defaults to ``2``.

    Returns:
        float: A score between ``0.0`` and ``1.0`` representing the logistic
            mapping of the input error.  The function safely handles large
            error values by capping the intermediate calculation to infinity.

    Example:
        >>> score_logistic_variant(5, scale_factor=10, steepness=2)
        0.9090909090909091
        >>> score_logistic_variant(-3)
        1.0
        >>> score_logistic_variant(10, scale_factor=0)
        0.0"""
    if errors < 0:
        errors = 0
    if scale_factor == 0:
        return 1.0 if errors == 0 else 0.0
    try:
        # Handle case where errors/scale_factor is very large, to avoid overflow
        base = errors / scale_factor
        if base > 709 / steepness:  # exp(709) is near max float
            term = float("inf")
        else:
            term = base**steepness
    except OverflowError:  # pragma: no cover
        return 0.0  # Score becomes 0 if term is too large
    return 1.0 / (1.0 + term)
