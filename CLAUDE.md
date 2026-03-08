# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CQ is a Python CLI tool for iterative, LLM-assisted code improvement. The primary use case is:

```bash
cq check -o llm   # returns the single most critical defect as markdown
```

The LLM fixes it, the user re-runs, and repeats until all tools pass. CQ runs
11 static analysis tools in execution order (compile → security → lint → types →
tests → coverage → complexity → dead code → style) and aggregates results into
a single score.

## Commands

```bash
# Run tests
uv run pytest

# Run a single test
uv run pytest tests/test_common.py::test_score_logistic_variant

# Run the CLI
uv run cq check              # table output, current directory
uv run cq check -o llm       # LLM markdown, primary use case
uv run cq check -o score     # numeric score
uv run cq check path/to/project/

# Lint
uv run ruff check src/
```

## Architecture

**Pipeline flow:** CLI (`cli.py`) → tool registry → execution engine → parsers → metric aggregator → output

- **`cli.py`**: Typer app with a single `check` command. Output mode selected via `--output`/`-o` enum (`table`, `score`, `json`, `llm`). Runs tools in parallel by default. Reads `[tool.cq]` from the target project's `pyproject.toml` and applies overrides before running.
- **`tool_registry.py`**: Loads `src/cq/config/config.yaml` at import time via `importlib.resources`, dynamically imports parser classes, builds a `dict[str, ToolConfig]` registry.
- **`config/config.yaml`** (at `src/cq/config/config.yaml`): Declares each analysis tool: shell command template (with `{context_path}` placeholder), parser class name, order, warning/error thresholds. Tools are listed and executed in order.
- **`execution_engine.py`**: Runs shell commands via `subprocess.run`, caches results with `diskcache` using a content-based hash. Parallel execution via `ThreadPoolExecutor`; results are sorted by order before returning.
- **`parsers/`**: Each parser subclasses `AbstractParser` (from `localtypes.py`), implementing `parse(RawResult) -> ToolResult` and optionally `format_llm_message(ToolResult) -> str`. Parser module names must match the lowercase parser class name (e.g., `PytestParser` → `pytestparser.py`).
- **`localtypes.py`**: Core dataclasses — `ToolConfig`, `RawResult`, `ToolResult`, `CombinedToolResults`, and `AbstractParser` ABC.
- **`metric_aggregator.py`**: Wraps results into `CombinedToolResults`, which computes an overall score as the average of per-tool mean metrics.
- **`llm_formatter.py`**: Selects the worst-scoring tool by severity tier then order, formats its top defect as markdown for LLM consumption.

## Adding a New Analysis Tool

1. Add tool entry in `config/config.yaml` with command template, parser name, order, and thresholds.
2. Create `src/cq/parsers/<parsername>.py` with a class matching the `parser` field in YAML.
3. The parser must subclass `AbstractParser` and implement `parse(RawResult) -> ToolResult`.
