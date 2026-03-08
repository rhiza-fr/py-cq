# Multi-Language Awareness Design

**Date:** 2026-03-08
**Status:** Approved

## Goal

Remove structural barriers that would prevent cq from supporting non-Python projects in future, while keeping Python as the fast path and avoiding untestable scope.

## What Changes

### 1. `config.yaml` restructure

Rename the top-level `tools:` key to `python:`. No other sections added yet.

```yaml
# before
tools:
  ruff: { ... }

# after
python:
  ruff: { ... }
```

Tool registry reads from the `python:` block. Zero behaviour change for existing users.

### 2. Language detection

Priority order:
1. `--language` CLI flag (explicit override)
2. Auto-detected from file markers in the target directory

File markers:

| Language | Marker files |
|---|---|
| python | `pyproject.toml`, `setup.py`, `setup.cfg`, `requirements.txt`, `Pipfile` |
| typescript | `package.json`, `tsconfig.json` |
| javascript | `package.json` |
| rust | `Cargo.toml` |
| go | `go.mod` |
| ruby | `Gemfile` |
| java | `pom.xml`, `build.gradle` |
| dotnet | `*.csproj`, `*.sln` |

Detection picks the first marker found. If multiple match (e.g. a Python project with a `package.json`), priority follows the table order above, with `python` highest.

### 3. Behaviour by detected language

- **python** → current behaviour, unchanged
- **recognised non-Python** → print a clear message and exit 0:
  `"<Language> project detected. Non-Python language support is not yet available."`
- **unrecognised** → current error behaviour (no known marker found)

### 4. No config discovery for non-Python languages

Non-Python projects do not read a project config file. Language detection alone is sufficient for now.

## What Does Not Change

- Python input validation (`.py` file check, `pyproject.toml` directory check)
- `{python}` command template placeholder
- `run_in_target_env` / `extra_deps` mechanism
- User-defined tools via `[tool.cq.tools]`
- All existing parsers and scoring

## Out of Scope

- Built-in tool definitions for non-Python languages
- Config file reading for non-Python projects (`Cargo.toml`, `package.json`, etc.)
- Installing or managing non-Python toolchains

## Files Affected

| File | Change |
|---|---|
| `src/py_cq/config/config.yaml` | Rename `tools:` → `python:` |
| `src/py_cq/tool_registry.py` | Read from `python:` key |
| `src/py_cq/cli.py` | Add `--language` flag; add language detection; route non-Python to message |
| `tests/test_cli.py` | Tests for language detection and non-Python message |
