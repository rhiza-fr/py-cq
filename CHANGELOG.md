# Changelog

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
