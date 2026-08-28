# Changelog

## [0.3.0] - 2026-08-28

### Changed

- **Dependency upgrades change what `cq check` reports.** `ruff` moves `0.15.16 -> 0.16.5` and `ty` moves `0.0.44 -> 0.0.75`; `pytest`, `hypothesis`, `radon` and `vulture` also move up. **Ruff 0.16 enables 413 rules by default, where 0.15 enabled roughly 60** (`E4`, `E7`, `E9`, `F`). Whole linters that were previously off - `B`, `S`, `SIM`, `PLW`, `RUF`, `UP`, `PYI`, `FURB`, `DTZ`, `TRY` and more - now fire. cq runs `ruff` from its own environment, so **upgrading cq is enough to make a project that scored clean on 0.2.3 drop below the `ruff` error threshold of `0.9` with no source change.** Expect a batch of new lint findings on the first run after upgrading, and budget a cleanup pass. Projects that pin their own `[tool.ruff] lint.select` are unaffected, since cq respects the target project's ruff config.
- `ruff` is now upper-capped at `<0.17`. Its default rule set is not stable across minor versions, and cq resolves ruff from its own environment, so an unbounded requirement lets a ruff release change every user's lint score without a cq release. The cap is to be raised deliberately, with a changelog note each time.
- The `uv_build` build backend is upper-capped at `<0.13.0` for the same reason, so a breaking backend release cannot break the source distribution build without a deliberate bump here.

### Added

- `cache_invariant = "ast"` tool config field. Tools declaring it key their cache on a docstring-invariant AST hash, so `pytest`, `coverage`, `compile` and `vulture` skip re-execution on comment- and docstring-only edits. `ty` and `bandit` deliberately opt out, since `# type: ignore` and `# nosec` comments change their results.
- `skip_if` tool config field. `coverage` now starts in parallel with `pytest` and is cancelled if `pytest` fails, scoring `0%` from a synthetic empty result instead of paying for a second test run.

### Performance

- Shared `SourceFile` cache (`source_file.py`): each file is read and parsed once per run rather than once per parser. Warm-run `coverage` parsing drops 87ms -> 37ms and `interrogate` 99ms -> 49ms.
- The context AST hash is computed once, eagerly, in the main thread instead of racing per-worker.
- Combined, a green cold run on this repo drops from 10.5s to 7.1s.

### Fixed

- Lint cleanup under the new ruff defaults: narrowed blind `except Exception` handlers in `cli.py` and `interrogateparser.py` to the exceptions actually raised, added explicit `check=False` to `subprocess.run` calls, flattened nested conditionals, and annotated the deliberate top-level exception guards in `execution_engine.py`.
- README and CLAUDE.md documented a `config/config.yaml` that has not existed since the move to `src/py_cq/config/config.toml`, listed the last five tools in the wrong execution order, and embedded a stale YAML copy of the default config.

## [0.2.3] - 2026-06-06

### Added

- `--order severity|phase` flag for `-o llm`/`-o llm-json`. The default `severity` selects the top issue by `(severity, tool-order)`; `phase` instead returns the first issue of the earliest non-clean phase in dependency order, triggering on the first phase below its `warning_threshold` independent of threshold tuning.

### Changed

- `coverage` now returns `0%` and skips re-execution when `pytest` fails. A new `skip_if` tool config field lets `coverage` wait on `pytest`'s result in parallel mode and parse a synthetic empty result instead of re-invoking `pytest`; all other tools stay fully parallel.

### Fixed

- Silence re-run: when early-exit stops at a phase whose only issues are silenced, all tools are re-run so later-phase issues can surface.
- `context_hash` now includes `pyproject.toml`, `uv.lock`, and `.python-version` in the file signature, so dependency changes invalidate the cache.
- `HalsteadParser`: files reported with an `error` key now zero all metric scores instead of leaving a perfect score, so unparseable files are penalised.
- `complexityparser`: guard against non-list function values before iterating.
- `ruffparser`: skip appending enclosing-function context when it is already present in the base message.

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
