# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CQ is a Python CLI tool for iterative, LLM-assisted code improvement. The primary use case is:

```bash
cq check -o llm   # returns the single most critical defect as markdown
```

The LLM fixes it, the user re-runs, and repeats until all tools pass. CQ runs
11 static analysis tools in execution order (compile → lint → types → security →
tests → coverage → dead code → docstrings → complexity) and aggregates results
into a single score.

## CLI Usage

```bash
cq check .                 # Table overview of scores
cq check . -o llm          # Top defect as markdown for LLMs (primary use case)
cq check . -o score        # Numeric score only (for CI gates)
cq check . -o json         # Detailed parsed JSON output
cq check . -o raw          # Raw tool output for debug
cq check path/to/file.py   # Single file (skips pytest and coverage)
cq check . --only ruff,ty  # Run only specific tools
cq check . --skip bandit   # Skip specific tools
cq check . --workers 1     # Run sequentially
cq check . --clear-cache   # Clear cached results before running
cq config path/to/project/ # Show effective tool configuration
```

**Exit codes:** exits with `1` if any tool metric falls below its `error_threshold`.

```bash
cq check . && deploy        # block deploy on errors
cq check . -o score         # print score, exit 1 on errors
```

**LLM loop:**
```bash
cq check . -o llm | claude -p "fix this"
```

**Stop hook** (`.claude/settings.json`) — auto-checks after each session:
```json
{
  "hooks": {
    "Stop": [{"matcher": "", "hooks": [{"type": "command", "command": "cq check . -o score && echo 'CQ: all clear' || cq check . -o llm"}]}]
  }
}
```

**Slash command** (`.claude/commands/cq-fix.md`) — manual invocation via `/cq-fix`:
```markdown
$(cq check . -o llm)
```

## Dev Commands

```bash
# Run tests
uv run pytest

# Run a single test
uv run pytest tests/test_common.py::test_score_logistic_variant

# Lint
uv run ruff check src/
```

## Architecture

**Pipeline flow:** CLI (`cli.py`) → tool registry → execution engine → parsers → metric aggregator → output

- **`cli.py`**: Typer app with a single `check` command. Output mode selected via `--output`/`-o` enum (`table`, `score`, `json`, `llm`). Runs tools in parallel by default. Reads `[tool.cq]` from the target project's `pyproject.toml` and applies overrides before running.
- **`tool_registry.py`**: Loads `src/py_cq/config/config.toml` at import time via `importlib.resources`, dynamically imports parser classes, builds a `dict[str, ToolConfig]` registry.
- **`config/config.toml`** (at `src/py_cq/config/config.toml`): Declares each analysis tool under a per-language section (`[python.<tool>]`): shell command template (with `{context_path}` placeholder), parser class name, order, warning/error thresholds. Tools are listed and executed in order.
- **`execution_engine.py`**: Runs shell commands via `subprocess.run`, caches results with `diskcache` using a content-based hash. Parallel execution via `ThreadPoolExecutor`; results are sorted by order before returning.
- **`parsers/`**: Each parser subclasses `AbstractParser` (from `localtypes.py`), implementing `parse(RawResult) -> ToolResult` and optionally `format_llm_message(ToolResult) -> str`. Parser module names must match the lowercase parser class name (e.g., `PytestParser` → `pytestparser.py`).
- **`localtypes.py`**: Core dataclasses — `ToolConfig`, `RawResult`, `ToolResult`, `CombinedToolResults`, and `AbstractParser` ABC.
- **`metric_aggregator.py`**: Wraps results into `CombinedToolResults`, which computes an overall score as the average of per-tool mean metrics.
- **`llm_formatter.py`**: Selects the worst-scoring tool by severity tier then order, formats its top defect as markdown for LLM consumption.

## Adding a New Analysis Tool

1. Add a `[python.<tool>]` entry in `config/config.toml` with command template, parser name, order, and thresholds.
2. Create `src/py_cq/parsers/<parsername>.py` with a class matching the `parser` field in the TOML.
3. The parser must subclass `AbstractParser` and implement `parse(RawResult) -> ToolResult`.
