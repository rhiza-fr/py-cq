# Design: Pytest Context & Configurable Context Lines

Date: 2026-03-08

## Problem

The pytest parser's `format_llm_message` returns only:

```
`tests/test_foo.py::test_bar` — test **FAILED**
```

This gives the LLM no information about what the test does or why it failed. Additionally, context window sizes for all parsers are hardcoded (`count=8` in `format_source_context`), with no way to tune them per project.

## Design

### 1. Config: `context_lines`

Add a single global `context_lines` integer to `[tool.cq]` in `pyproject.toml`:

```toml
[tool.cq]
context_lines = 20  # default: 15
```

- `load_user_config` reads `user_cfg.get("context_lines", 15)` and returns it alongside existing config.
- The value is passed from `cli.py` → `format_for_llm` → each parser's `format_llm_message` as a new optional parameter `context_lines=15`.
- `AbstractParser.format_llm_message(tr, context_lines=15)` — default keeps existing behaviour.
- Existing parsers (ruff, ty, bandit, vulture, compile) pass `count=context_lines` to `format_source_context` instead of the hardcoded `8`.

### 2. New helper: `find_function_source`

Added to `common.py`:

```python
def find_function_source(file: str, func_name: str, max_lines: int = 15) -> str
```

- Scans the file for `def {func_name}(` or `async def {func_name}(`.
- Records the indent level of that line as the baseline.
- Reads subsequent lines until indent drops back to baseline (or a blank/decorator at baseline), or `max_lines` is reached.
- Returns a numbered fenced `python` block (same format as `format_source_context`), or `""` on failure.

### 3. `PytestParser.format_llm_message`

New output format for a failing test:

```
`tests/test_foo.py::test_bar` — test **FAILED**

```python
42: def test_bar():
43:     result = my_func(bad_input)
44:     assert result == expected
```

```
AssertionError: assert 'wrong' == 'expected'
```
```

Implementation:
- Use `find_function_source(file, test_name, max_lines=context_lines)` for the function body.
- Extract the failure section from `tr.raw.stdout` by finding `__ test_bar __` and capturing lines until the next `___` separator, truncated at `context_lines` lines.
- Both blocks are included only when non-empty.

### 4. Truncation

All context blocks are capped at `context_lines`. No separate knobs.

## Files Changed

- `src/py_cq/parsers/common.py` — add `find_function_source`
- `src/py_cq/parsers/pytestparser.py` — update `format_llm_message`
- `src/py_cq/parsers/banditparser.py`, `ruffparser.py`, `typarser.py`, `vultureparser.py`, `compileparser.py` — pass `count=context_lines` to `format_source_context`
- `src/py_cq/config/__init__.py` (or equivalent) — expose `context_lines` from `load_user_config`
- `src/py_cq/llm_formatter.py` — pass `context_lines` through to `format_llm_message`
- `src/py_cq/cli.py` — read `context_lines` from user config and pass to formatter
