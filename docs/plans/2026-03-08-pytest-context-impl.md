# Pytest Context & Configurable context_lines Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add function body + failure output to pytest's LLM message, and make context window size configurable via `[tool.cq] context_lines` in `pyproject.toml`.

**Architecture:** Add `find_function_source` to `common.py`; thread `context_lines` from `load_user_config` → `cli.py` → `format_for_llm` → `format_llm_message`; update `PytestParser.format_llm_message` to show function body and failure excerpt; update existing parsers to use `context_lines` instead of hardcoded `8`.

**Tech Stack:** Python, pytest, typer, tomllib (stdlib)

---

### Task 1: Add `find_function_source` to `common.py`

**Files:**
- Modify: `src/py_cq/parsers/common.py`
- Test: `tests/test_common.py`

**Step 1: Write the failing test**

Add to `tests/test_common.py`:

```python
from py_cq.parsers.common import find_function_source

def test_find_function_source_basic(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text(
        "def unrelated():\n"
        "    pass\n"
        "\n"
        "def test_bar():\n"
        "    x = 1\n"
        "    assert x == 1\n"
        "\n"
        "def after():\n"
        "    pass\n"
    )
    result = find_function_source(str(f), "test_bar", max_lines=10)
    assert "def test_bar" in result
    assert "assert x == 1" in result
    assert "def after" not in result
    assert "```python" in result


def test_find_function_source_truncates(tmp_path):
    f = tmp_path / "foo.py"
    lines = ["def test_long():\n"] + [f"    x = {i}\n" for i in range(20)]
    f.write_text("".join(lines))
    result = find_function_source(str(f), "test_long", max_lines=5)
    assert result.count("\n") <= 7  # fences + 5 lines


def test_find_function_source_not_found(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text("def other(): pass\n")
    assert find_function_source(str(f), "missing", max_lines=10) == ""


def test_find_function_source_missing_file():
    assert find_function_source("/nonexistent/foo.py", "test_x", max_lines=10) == ""


def test_find_function_source_async(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text("async def test_async():\n    await something()\n")
    result = find_function_source(str(f), "test_async", max_lines=10)
    assert "async def test_async" in result
```

**Step 2: Run to verify failure**

```bash
cd /d/ai/py-cq && uv run pytest tests/test_common.py::test_find_function_source_basic -v
```
Expected: `ImportError` or `AttributeError` — `find_function_source` doesn't exist yet.

**Step 3: Implement `find_function_source` in `common.py`**

Add after `format_source_context`:

```python
def find_function_source(file: str, func_name: str, max_lines: int = 15) -> str:
    """Return a fenced python block for the body of func_name, or '' if unavailable."""
    from pathlib import Path
    try:
        all_lines = Path(file).read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    import re
    pattern = re.compile(rf"^(\s*)(?:async\s+)?def\s+{re.escape(func_name)}\s*\(")
    start_idx = None
    baseline_indent = None
    for i, line in enumerate(all_lines):
        m = pattern.match(line)
        if m:
            start_idx = i
            baseline_indent = len(m.group(1))
            break
    if start_idx is None:
        return ""
    collected = [all_lines[start_idx]]
    for line in all_lines[start_idx + 1 :]:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if stripped and indent <= baseline_indent:
            break
        collected.append(line)
        if len(collected) >= max_lines:
            break
    numbered = "\n".join(f"{start_idx + 1 + i}: {l}" for i, l in enumerate(collected))
    return f"\n```python\n{numbered}\n```"
```

**Step 4: Run all new tests**

```bash
uv run pytest tests/test_common.py -v
```
Expected: all pass.

**Step 5: Commit**

```bash
git add src/py_cq/parsers/common.py tests/test_common.py
git commit -m "feat: add find_function_source helper to common.py"
```

---

### Task 2: Thread `context_lines` from config to `format_llm_message`

**Files:**
- Modify: `src/py_cq/llm_formatter.py`
- Modify: `src/py_cq/localtypes.py` (signature of `format_llm_message`)
- Modify: `src/py_cq/cli.py`
- Test: `tests/test_llm_formatter.py`

**Step 1: Check the existing llm_formatter test**

```bash
uv run pytest tests/test_llm_formatter.py -v
```
Baseline — all should pass before changes.

**Step 2: Update `AbstractParser.format_llm_message` signature in `localtypes.py`**

Find the method at line ~127 and change:

```python
def format_llm_message(self, tr: ToolResult) -> str:
```
to:
```python
def format_llm_message(self, tr: ToolResult, context_lines: int = 15) -> str:
```

**Step 3: Update `format_for_llm` in `llm_formatter.py`**

Change the signature and the call:

```python
def format_for_llm(
    tool_configs: dict,
    combined: CombinedToolResults,
    cq_invocation: str | None = None,
    context_lines: int = 15,
) -> str:
```

Change line 41:
```python
    defect_md = config.parser_class().format_llm_message(worst, context_lines=context_lines)
```

**Step 4: Read `context_lines` from user config in `cli.py`**

In the `check` command, after `load_user_config`:

```python
user_cfg = load_user_config(path_obj)
context_lines: int = int(user_cfg.get("context_lines", 15))
effective_registry = _apply_user_config(tool_registry, user_cfg)
```

Then pass it to `format_for_llm`:
```python
console.print(format_for_llm(effective_registry, combined_metrics, context_lines=context_lines))
```

**Step 5: Run tests to verify nothing broke**

```bash
uv run pytest tests/test_llm_formatter.py tests/test_cli.py -v
```
Expected: all pass (signatures are backward-compatible with defaults).

**Step 6: Commit**

```bash
git add src/py_cq/localtypes.py src/py_cq/llm_formatter.py src/py_cq/cli.py
git commit -m "feat: thread context_lines config param to format_llm_message"
```

---

### Task 3: Update existing parsers to use `context_lines`

**Files:**
- Modify: `src/py_cq/parsers/banditparser.py`
- Modify: `src/py_cq/parsers/ruffparser.py`
- Modify: `src/py_cq/parsers/typarser.py`
- Modify: `src/py_cq/parsers/vultureparser.py`
- Modify: `src/py_cq/parsers/compileparser.py`

Each of these calls `format_source_context(file, line)` with the hardcoded default `count=8`.

**Step 1: Update each parser's `format_llm_message` signature and call**

For each parser, change:
```python
def format_llm_message(self, tr: ToolResult) -> str:
```
to:
```python
def format_llm_message(self, tr: ToolResult, context_lines: int = 15) -> str:
```

And change `format_source_context(file, line)` to `format_source_context(file, line, count=context_lines)`.

For `compileparser.py` the call is:
```python
format_source_context(file, line) or (...)
```
→
```python
format_source_context(file, line, count=context_lines) or (...)
```

**Step 2: Run the parser tests**

```bash
uv run pytest tests/test_parser_bandit.py tests/test_parser_ruff.py tests/test_parser_ty.py tests/test_parser_vulture.py tests/test_parser_compile.py -v
```
Expected: all pass.

**Step 3: Commit**

```bash
git add src/py_cq/parsers/banditparser.py src/py_cq/parsers/ruffparser.py src/py_cq/parsers/typarser.py src/py_cq/parsers/vultureparser.py src/py_cq/parsers/compileparser.py
git commit -m "feat: pass context_lines to format_source_context in all parsers"
```

---

### Task 4: Improve `PytestParser.format_llm_message`

**Files:**
- Modify: `src/py_cq/parsers/pytestparser.py`
- Test: `tests/test_parser_pytest.py`

**Step 1: Write failing tests for the new format_llm_message**

Add to `tests/test_parser_pytest.py`:

```python
import textwrap
from conftest import raw

PYTEST_WITH_FAILURE = """\
tests/test_foo.py::test_bar FAILED    [100%]

=================================== FAILURES ===================================
________________________________ test_bar ________________________________

    def test_bar():
>       assert 1 == 2
E       AssertionError: assert 1 == 2

tests/test_foo.py:5: AssertionError
=========================== short test summary info ============================
FAILED tests/test_foo.py::test_bar - AssertionError: assert 1 == 2
"""

def test_format_llm_message_includes_failure_output(tmp_path):
    test_file = tmp_path / "tests" / "test_foo.py"
    test_file.parent.mkdir()
    test_file.write_text("def test_bar():\n    assert 1 == 2\n")
    stdout = PYTEST_WITH_FAILURE.replace("tests/test_foo.py", str(test_file))
    tr = PytestParser().parse(raw(stdout, return_code=1))
    # Patch detail key to match tmp_path
    msg = PytestParser().format_llm_message(tr, context_lines=15)
    assert "FAILED" in msg
    assert "AssertionError" in msg


def test_format_llm_message_includes_function_body(tmp_path):
    test_file = tmp_path / "tests" / "test_foo.py"
    test_file.parent.mkdir()
    test_file.write_text("def test_bar():\n    assert 1 == 2\n")
    stdout = f"{test_file}::test_bar FAILED    [100%]\n"
    tr = PytestParser().parse(raw(stdout, return_code=1))
    msg = PytestParser().format_llm_message(tr, context_lines=15)
    assert "def test_bar" in msg


def test_format_llm_message_no_body_fallback(tmp_path):
    """When test file doesn't exist, still returns something useful."""
    tr = PytestParser().parse(raw(
        "tests/nonexistent.py::test_missing FAILED    [100%]\n", return_code=1
    ))
    msg = PytestParser().format_llm_message(tr, context_lines=15)
    assert "FAILED" in msg
```

**Step 2: Run to verify failure**

```bash
uv run pytest tests/test_parser_pytest.py::test_format_llm_message_includes_function_body -v
```
Expected: FAIL — current implementation doesn't include function body.

**Step 3: Implement the new `format_llm_message`**

Replace the existing method in `pytestparser.py`:

```python
def format_llm_message(self, tr: ToolResult, context_lines: int = 15) -> str:
    """Return the first failing test with function body and failure output."""
    from py_cq.parsers.common import find_function_source
    for file, tests in tr.details.items():
        if not isinstance(tests, dict):
            continue
        for test_name, status in tests.items():
            if status != "FAILED":
                continue
            header = f"`{file}::{test_name}` — test **FAILED**"
            body = find_function_source(file, test_name, max_lines=context_lines)
            failure = _extract_failure(tr.raw.stdout, test_name, max_lines=context_lines)
            parts = [header]
            if body:
                parts.append(body)
            if failure:
                parts.append(failure)
            return "\n".join(parts)
    return "pytest reported failures (no details available)"
```

Add the helper `_extract_failure` as a module-level function in `pytestparser.py`:

```python
def _extract_failure(stdout: str, test_name: str, max_lines: int) -> str:
    """Extract the failure section for test_name from pytest stdout."""
    lines = stdout.splitlines()
    # Find the header line like "_______ test_name _______"
    start = None
    for i, line in enumerate(lines):
        if test_name in line and line.strip().startswith("_"):
            start = i + 1
            break
    if start is None:
        return ""
    collected = []
    for line in lines[start:]:
        if line.strip().startswith("_") or line.strip().startswith("="):
            break
        collected.append(line)
        if len(collected) >= max_lines:
            break
    text = "\n".join(collected).strip()
    return f"\n```\n{text}\n```" if text else ""
```

**Step 4: Run all pytest parser tests**

```bash
uv run pytest tests/test_parser_pytest.py -v
```
Expected: all pass.

**Step 5: Run the full test suite**

```bash
uv run pytest
```
Expected: all pass.

**Step 6: Commit**

```bash
git add src/py_cq/parsers/pytestparser.py tests/test_parser_pytest.py
git commit -m "feat: add function body and failure output to pytest LLM message"
```

---

### Task 5: Final verification

**Step 1: Run full test suite + type check**

```bash
uv run pytest && uv run ty check src/
```
Expected: all tests pass, no type errors.

**Step 2: Smoke test with real output**

```bash
uv run cq check . -o llm
```
Verify the output looks reasonable (no crashes, markdown is well-formed).

**Step 3: Commit if any fixups needed, then done**
