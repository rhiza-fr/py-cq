# Changelog

## [0.2.2]

### Fixed

- `coverage`: `.coverage` data file is now written to a temp path instead of the working directory, keeping the project tree clean. Each `run_tool` invocation gets an isolated path, so concurrent `cq` processes no longer collide on the same data file.

## [0.2.1] - 2026-06-01

### Added

- `cq is-fixed <id>` command — checks whether a specific fingerprinted issue is resolved without re-running all tools.
- `cq config set <key> <value>` subcommand for updating `pyproject.toml` tool config in-place.
- Python library API (`cq.check()`, `cq.is_fixed()`) mirroring the CLI for programmatic use.
- `-o llm-json` output mode returns a JSON object with `id`, `file`, `project`, and `message`. The `id` is a fingerprint (`tool::project::path::line::code`) that can be passed to `cq is-fixed <id>` (CLI) or `cq.is_fixed(id)` (library) to verify the issue is gone without re-running all tools.
- Tag-based cache eviction: cache entries are invalidated when tool configuration changes.
- `interrogate` now scans test files in addition to source files.

### Changed

- `-o llm` output no longer appends "After fixing, run cq again to verify" by default — this prevented agents from running cleanly in a pipe. Use `--hint` to restore the old behaviour.
- `interrogate` and `coverage` parsers now emit per-issue details with exact line numbers and codes, consistent with `ruff`/`ty` output. LLM output shows `file:line — code: message` with source context instead of a file-level summary. Multiple issues are reported separately, so each fix gets its own targeted prompt.
- Silence rules now use exact fingerprint matching instead of fuzzy path matching, eliminating false positives when paths partially overlap.
- `is_fixed` targets the specific affected file for faster re-checks when the fingerprint includes a path and code.
- Parallel execution now logs per-tool timing breakdown (e.g. `ruff=0.17s, ty=0.33s`).
- `bandit` now scans top-level directories explicitly, correctly applying named exclude paths.
- Single-file checks skip `pytest` and `coverage` (not applicable at file scope).
- Project-level tool flags from `[tool.cq]` in `pyproject.toml` are now respected at runtime.
- Replaced `config.yaml` with `config.toml`, dropping the `pyyaml` dependency.

### Fixed

- `bandit`: return a degraded score instead of crashing on invalid JSON output.
- `coverage`: skip pytest progress lines in reports to avoid parse errors.
- `ruff`: widened diagnostic code regex to match a broader range of rule codes.
- `HalsteadParser`: raised `MAX_FILE_VOLUME` to 3000 to handle larger files.

### Security

- Parser class loading now uses a safelist; built-in names cannot be overridden via config.
- Exclude paths and extra dependencies are shell-quoted before subprocess invocation; symlink traversal uses `follow_symlinks=False`.

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
