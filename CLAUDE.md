# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CQ is a Python CLI tool that analyzes code quality by running multiple static analysis tools (pytest, coverage, pydocstyle, radon metrics), parsing their output, and aggregating results into a single score with rich terminal output.

## Commands

```bash
# Run tests
uv run pytest

# Run a single test
uv run pytest tests/test_common.py::test_score_logistic_variant

# Run the CLI
uv run cq run path/to/file.py
uv run cq run path/to/project/

# Lint
uv run ruff check src/
```

## Architecture

**Pipeline flow:** CLI (`cli.py`) → tool registry → execution engine → parsers → metric aggregator → output

- **`cli.py`**: Typer app with a single `run` command. Validates input, orchestrates the pipeline, formats output as Rich tables.
- **`tool_registry.py`**: Loads `config/tools.yaml` at import time, dynamically imports parser classes, builds a `dict[str, ToolConfig]` registry.
- **`config/tools.yaml`**: Declares each analysis tool: shell command template (with `{context_path}` placeholder), parser class name, priority, warning/error thresholds.
- **`execution_engine.py`**: Runs shell commands via `subprocess.run`, caches results with `cachier` using a content-based hash. Supports parallel execution via `ThreadPoolExecutor`.
- **`parsers/`**: Each parser subclasses `AbstractParser` (from `localtypes.py`), implementing `parse(RawResult) -> ToolResult` and optionally `provide_help(ToolResult) -> str`. Parser module names must match the lowercase parser class name (e.g., `PytestParser` → `pytestparser.py`).
- **`localtypes.py`**: Core dataclasses — `ToolConfig`, `RawResult`, `ToolResult`, `CombinedToolResults`, and `AbstractParser` ABC.
- **`metric_aggregator.py`**: Wraps results into `CombinedToolResults`, which computes an overall score as the average of per-tool mean metrics.
- **`help_engine.py`**: Collects `provide_help()` output from each parser to generate actionable suggestions.

## Adding a New Analysis Tool

1. Add tool entry in `config/tools.yaml` with command template, parser name, priority, and thresholds.
2. Create `src/cq/parsers/<parsername>.py` with a class matching the `parser` field in YAML.
3. The parser must subclass `AbstractParser` and implement `parse(RawResult) -> ToolResult`.
