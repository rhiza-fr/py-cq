# Multi-Language Awareness Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restructure `config.yaml` to be language-keyed and add language detection so cq prints a clear message for non-Python projects instead of confusing errors.

**Architecture:** Rename `tools:` → `python:` in `config.yaml` and update `tool_registry.py` to read from that key. Add a `language_detector.py` module that maps file markers to language names. Update the CLI to resolve language (via `--language` flag or auto-detection), run the Python fast path unchanged, and print an informative message for recognised non-Python projects.

**Tech Stack:** Python 3.12+, uv, pytest, typer, existing `py_cq` codebase.

---

### Task 1: Rename `tools:` → `python:` in config.yaml and update tool_registry

**Files:**
- Modify: `src/py_cq/config/config.yaml`
- Modify: `src/py_cq/tool_registry.py`

**Step 1: Write the failing test**

Add to `tests/test_tool_registry.py` (create if it doesn't exist):

```python
"""Tests for tool_registry."""
from py_cq.tool_registry import tool_registry


def test_registry_loads_python_tools():
    """Tool registry loads tools from the python: block."""
    assert "ruff" in tool_registry
    assert "pytest" in tool_registry
    assert "bandit" in tool_registry


def test_registry_tools_have_required_fields():
    for name, tc in tool_registry.items():
        assert tc.command, f"{name} has no command"
        assert tc.parser_class is not None, f"{name} has no parser_class"
        assert isinstance(tc.order, int), f"{name} order must be int"
```

**Step 2: Run to verify current state passes**

```bash
uv run pytest tests/test_tool_registry.py -v
```

Expected: PASS (baseline before the change).

**Step 3: Rename key in config.yaml**

In `src/py_cq/config/config.yaml`, change the first line:

```yaml
# before
tools:

# after
python:
```

**Step 4: Run to verify it now fails**

```bash
uv run pytest tests/test_tool_registry.py -v
```

Expected: FAIL — registry is empty because `tool_registry.py` still reads `config["tools"]`.

**Step 5: Update tool_registry.py**

In `src/py_cq/tool_registry.py`, change line 19:

```python
# before
for tool_id, tool_data in config["tools"].items():

# after
for tool_id, tool_data in config["python"].items():
```

**Step 6: Run to verify it passes**

```bash
uv run pytest tests/test_tool_registry.py -v
```

Expected: PASS.

**Step 7: Run full suite**

```bash
uv run pytest
```

Expected: all pass — no other code references `config["tools"]` directly.

**Step 8: Commit**

```bash
git add src/py_cq/config/config.yaml src/py_cq/tool_registry.py tests/test_tool_registry.py
git commit -m "refactor: rename config.yaml top-level key from tools to python"
```

---

### Task 2: Implement language detector

**Files:**
- Create: `src/py_cq/language_detector.py`
- Create: `tests/test_language_detector.py`

**Step 1: Write the failing tests**

Create `tests/test_language_detector.py`:

```python
"""Tests for language_detector."""
import pytest
from pathlib import Path
from py_cq.language_detector import detect_language


def test_python_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    assert detect_language(tmp_path) == "python"


def test_python_setup_py(tmp_path):
    (tmp_path / "setup.py").write_text("")
    assert detect_language(tmp_path) == "python"


def test_python_requirements(tmp_path):
    (tmp_path / "requirements.txt").write_text("")
    assert detect_language(tmp_path) == "python"


def test_typescript_tsconfig(tmp_path):
    (tmp_path / "tsconfig.json").write_text("{}")
    assert detect_language(tmp_path) == "typescript"


def test_typescript_package_json(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    assert detect_language(tmp_path) == "typescript"


def test_rust_cargo(tmp_path):
    (tmp_path / "Cargo.toml").write_text("")
    assert detect_language(tmp_path) == "rust"


def test_go_mod(tmp_path):
    (tmp_path / "go.mod").write_text("")
    assert detect_language(tmp_path) == "go"


def test_ruby_gemfile(tmp_path):
    (tmp_path / "Gemfile").write_text("")
    assert detect_language(tmp_path) == "ruby"


def test_java_pom(tmp_path):
    (tmp_path / "pom.xml").write_text("")
    assert detect_language(tmp_path) == "java"


def test_java_gradle(tmp_path):
    (tmp_path / "build.gradle").write_text("")
    assert detect_language(tmp_path) == "java"


def test_dotnet_csproj(tmp_path):
    (tmp_path / "app.csproj").write_text("")
    assert detect_language(tmp_path) == "dotnet"


def test_unknown_returns_none(tmp_path):
    assert detect_language(tmp_path) is None


def test_python_wins_over_typescript(tmp_path):
    """Python takes priority when both markers are present."""
    (tmp_path / "pyproject.toml").write_text("")
    (tmp_path / "package.json").write_text("{}")
    assert detect_language(tmp_path) == "python"


def test_file_input_checks_parent(tmp_path):
    """When given a file path, checks the parent directory."""
    (tmp_path / "pyproject.toml").write_text("")
    py_file = tmp_path / "foo.py"
    py_file.write_text("")
    assert detect_language(py_file) == "python"


def test_file_input_no_markers(tmp_path):
    f = tmp_path / "foo.txt"
    f.write_text("")
    assert detect_language(f) is None
```

**Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_language_detector.py -v
```

Expected: FAIL — module not found.

**Step 3: Implement**

Create `src/py_cq/language_detector.py`:

```python
"""Detect the primary language of a project from its file markers."""

from pathlib import Path

# Ordered: first match wins. Python is listed first so it takes priority.
_MARKERS: list[tuple[str, list[str]]] = [
    ("python", ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile"]),
    ("typescript", ["tsconfig.json", "package.json"]),
    ("rust", ["Cargo.toml"]),
    ("go", ["go.mod"]),
    ("ruby", ["Gemfile"]),
    ("java", ["pom.xml", "build.gradle"]),
    ("dotnet", []),  # glob-based, handled separately
]

_DOTNET_SUFFIXES = {".csproj", ".sln"}


def detect_language(path: Path) -> str | None:
    """Return the detected language for a project path, or None if unrecognised.

    If path is a file, the parent directory is checked."""
    directory = path if path.is_dir() else path.parent
    for language, markers in _MARKERS:
        if language == "dotnet":
            if any(f.suffix in _DOTNET_SUFFIXES for f in directory.iterdir() if f.is_file()):
                return "dotnet"
        else:
            if any((directory / marker).exists() for marker in markers):
                return language
    return None
```

**Step 4: Run to verify they pass**

```bash
uv run pytest tests/test_language_detector.py -v
```

Expected: PASS.

**Step 5: Run full suite**

```bash
uv run pytest
```

Expected: all pass.

**Step 6: Commit**

```bash
git add src/py_cq/language_detector.py tests/test_language_detector.py
git commit -m "feat: add language detector from project file markers"
```

---

### Task 3: Add `--language` flag and language routing to CLI

**Files:**
- Modify: `src/py_cq/cli.py`
- Modify: `tests/test_cli.py`

**Step 1: Write the failing tests**

Add to `tests/test_cli.py`:

```python
def test_check_typescript_project_prints_message(tmp_path):
    """A TypeScript project prints a clear message and exits 0."""
    (tmp_path / "package.json").write_text("{}")
    result = runner.invoke(app, ["check", str(tmp_path)])
    assert result.exit_code == 0
    assert "typescript" in result.output.lower()
    assert "not yet available" in result.output.lower()


def test_check_rust_project_prints_message(tmp_path):
    (tmp_path / "Cargo.toml").write_text("")
    result = runner.invoke(app, ["check", str(tmp_path)])
    assert result.exit_code == 0
    assert "rust" in result.output.lower()


def test_check_language_flag_overrides_detection(tmp_path):
    """--language typescript on an empty dir prints the message (no auto-detect needed)."""
    result = runner.invoke(app, ["check", str(tmp_path), "--language", "typescript"])
    assert result.exit_code == 0
    assert "typescript" in result.output.lower()


def test_check_language_flag_python_runs_normally(project_dir):
    """--language python still runs the Python fast path."""
    tr = _fake_tr()
    combined = _fake_combined(str(project_dir))
    with patch("py_cq.cli.run_tools", return_value=[tr]), \
         patch("py_cq.cli.aggregate_metrics", return_value=combined):
        result = runner.invoke(app, ["check", str(project_dir), "--language", "python", "-o", "score"])
    assert result.exit_code == 0
    assert "0.9" in result.output


def test_check_unknown_dir_still_errors(tmp_path):
    """A directory with no recognised markers still produces an error."""
    result = runner.invoke(app, ["check", str(tmp_path)])
    assert result.exit_code != 0
```

**Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_cli.py::test_check_typescript_project_prints_message tests/test_cli.py::test_check_rust_project_prints_message tests/test_cli.py::test_check_language_flag_overrides_detection tests/test_cli.py::test_check_language_flag_python_runs_normally tests/test_cli.py::test_check_unknown_dir_still_errors -v
```

Expected: FAIL — no `--language` flag, no routing logic.

**Step 3: Implement**

In `src/py_cq/cli.py`, add the import near the top:

```python
from py_cq.language_detector import detect_language
```

Add `--language` option to the `check` command signature (after the `workers` parameter):

```python
language: str | None = typer.Option(
    None, "--language", "-l", help="Override language detection (e.g. python, typescript, rust)"
),
```

Replace the existing path validation block in `check` (lines 126–134):

```python
    path_obj = Path(path)
    if not path_obj.exists():
        raise typer.BadParameter(f"Path does not exist: {path}")

    resolved_language = language or detect_language(path_obj)

    if resolved_language != "python":
        if resolved_language is not None:
            console.print(
                f"[yellow]{resolved_language.capitalize()} project detected. "
                "Non-Python language support is not yet available.[/yellow]"
            )
            raise typer.Exit(0)
        # Unknown: fall through to Python-specific validation for a helpful error
        if path_obj.is_file():
            if path_obj.suffix != ".py":
                raise typer.BadParameter(f"File must be a Python file (.py): {path}")
        elif path_obj.is_dir():
            if not (path_obj / "pyproject.toml").exists():
                raise typer.BadParameter(f"Directory must contain pyproject.toml: {path}")
    else:
        if path_obj.is_file():
            if path_obj.suffix != ".py":
                raise typer.BadParameter(f"File must be a Python file (.py): {path}")
        elif path_obj.is_dir():
            if not (path_obj / "pyproject.toml").exists():
                raise typer.BadParameter(f"Directory must contain pyproject.toml: {path}")
```

**Step 4: Run to verify the new tests pass**

```bash
uv run pytest tests/test_cli.py -v
```

Expected: all pass.

**Step 5: Run full suite**

```bash
uv run pytest
```

Expected: all pass.

**Step 6: Type check and lint**

```bash
uv run ty check
uv run ruff check src/
```

Expected: no errors.

**Step 7: Commit**

```bash
git add src/py_cq/cli.py tests/test_cli.py
git commit -m "feat: add --language flag and non-Python project detection"
```

---

### Task 4: Final verification

**Step 1: Full test suite**

```bash
uv run pytest
```

Expected: all pass.

**Step 2: Smoke test — Python project (fast path unchanged)**

```bash
uv run cq check . -o score
```

Expected: numeric score, same as before.

**Step 3: Smoke test — non-Python project**

```bash
mkdir /tmp/ts-test && echo '{}' > /tmp/ts-test/package.json
uv run cq check /tmp/ts-test
```

Expected: `"Typescript project detected. Non-Python language support is not yet available."`, exit 0.

**Step 4: Smoke test — explicit language flag**

```bash
uv run cq check /tmp/ts-test --language typescript
```

Expected: same message, exit 0.
