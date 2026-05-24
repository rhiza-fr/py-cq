# Changelog

## [Unreleased]

### Changed

- `-o llm` output no longer appends "After fixing, run cq again to verify" by default — this prevented agents from running cleanly in a pipe. Use `--hint` to restore the old behaviour.

## [0.1.16] - 2026-04-27

### Fixed

- Harden parsers against malformed input.
- Extend `ValueError` guard to `find_function_source` and handle compile edge cases.
- Fix output formatting.

### Changed

- Achieve 100% line and branch test coverage.
- Remove low-value hypothesis tests from scoring and aggregator.

## [0.1.15] - 2026-03-31

### Added

- `--version` flag to print the current CQ version.

### Changed

- LLM output now shows the callee context for cleaner defect reporting.
- Type fixes and demo script improvements.

## [0.1.14] - 2026-03-30

### Added

- `--exclude <path1,path2>` flag to exclude paths from all tools for a single run.
- `exclude = [...]` key in `[tool.cq]` pyproject.toml config for persistent exclusions (merged with CLI flag).

## [0.1.13] - 2026-03-30

### Added

- `--only <tool1,tool2>` flag to run only the specified tools without touching `pyproject.toml`.
- `--skip <tool1,tool2>` flag to exclude specific tools for a single run.

## [0.1.12] - 2026-03-27

### Fixed

- Skip `--with <dep>` flags for extra deps already installed in the project's `.venv`, avoiding redundant installs and version conflicts.

## [0.1.11] - prior release
