# Changelog

## [0.4.2] - 2026-11-16

### Added

- GitHub Action (`action.yml`): `uses: rhiza-fr/py-cq@v0.4.2` runs cq as a CI gate. The job summary shows the score table and, on failure, up to `limit` issues (default 3) from the first failing tool. It installs `uv` when missing, installs Kingfisher by default, and works on Gitea Actions.
- pre-commit hook (`.pre-commit-hooks.yaml`), id `cq`: runs `cq check . -o llm` and blocks the commit when the gate fails.
- `llms.txt` describing the agent fix loop.

### Fixed

- The relative-path test in `test_llm_formatter.py` built the native path with a hardcoded backslash, which is only a separator on Windows, so CI failed on Linux. It now uses `os.sep`.
- `cq --help` and `cq check --help` say 14 tools, not 13.
- `ruff` F821 (undefined name) messages no longer repeat the enclosing function when the source context already shows all of it. The check compared the two code blocks as whole strings, and the context window almost always covers extra lines, so the function was shown twice.
- README: the Claude Code stop hook example now exits `2` and writes the fix prompt to stderr, which is what makes Claude receive it and keep working. The old example always exited `0`, so Claude never saw the prompt. The slash command example uses the `` !`cq check . -o llm` `` syntax, since `$(...)` is not expanded.

### Changed

- README restructured for first-time users: requirements (Python 3.12+, `uv`), a quick start with sample `-o llm` output, the `--limit`, `--silence` and `--order` flags, and `cq config` in place of a stale copy of the default `config.toml`.

## [0.4.1] - 2026-11-16

### Removed

- `radon-hal` metrics `file_smallness` and `functions_smallness`. Radon estimates bugs as volume / 3000, and the bug and volume limits had the same ratio (1 bug or 3000 volume per file, 0.2 bugs or 600 volume per function), so each was always equal to its `*_bug_free` partner. `file_bug_free` and `functions_bug_free` remain. The overall score does not change, since it averages each tool's metrics before averaging tools.

### Fixed

- Tools now run with the target project's root as their working directory. Before, they ran from wherever `cq` was started, so a tool that reads its configuration from the current directory used the wrong one. Running `cq check ../other` from another project made ruff take its Python target version from that other project's `requires-python`, which hid syntax errors that only exist on the target's older Python versions, and vulture ignored the target's `[tool.vulture]` settings. Cached results now include the working directory, so results from older runs are not reused.
- `vulture` no longer reports typed fields in a class body (`name: type` or `name: type = value`) as unused variables. Pydantic models, dataclasses, TypedDicts, NamedTuples and attrs classes read these fields through the class, never by name, so at `--min-confidence 60` every field of every model was reported. Untyped class attributes and typed variables outside a class body are still reported.
- `ruff` syntax errors (`invalid-syntax`) are reported. The parser only recognised rule codes such as `F401`, so syntax errors were dropped from both the score and the LLM output. They are now counted and come first in the LLM output, since other findings in a file that does not parse are unreliable.
- `compile` runs again. The `compileall` exclude pattern `.*venv|\.claude` was not quoted, so the shell read `|` as a pipe and `compileall` never ran: since 0.2.1 every project scored 1.0 on `compile` whatever its syntax errors. The pattern is now quoted. A `compileall` run that exits non-zero without reporting a file error now scores 0.0 and shows the tool's output, instead of passing.
- `pytest` counts tests inside classes. Result lines such as `tests/test_x.py::TestClass::test_y FAILED` did not match the parser, so every class-based test was dropped and a run with failing class tests could score 1.0. The LLM message finds the failure section (which pytest titles `TestClass.test_y`) and shows the method body.
- `pytest` no longer counts skipped tests (`SKIPPED`) or expected failures (`XFAIL`) as failures, so a green run with skipped tests scores 1.0 instead of failing the gate. An unexpected pass (`XPASS`) counts as a pass.
- `pytest` and `coverage` honour the project's `testpaths`. cq passed the target path to pytest explicitly, and pytest ignores `testpaths` when given a path, so it collected every test directory (for example benchmark suites that need other packages). The path is now omitted when the target is the project directory.
- `coverage` reports only files inside the target project. Editable path dependencies outside it were measured and reported too, which lowered the score and pointed the LLM at another repository. Files that are never imported are still not added at 0%.
- LLM messages show file paths relative to the project root. Most tools printed absolute paths (`D:/ai/proj/src/...`) when cq ran from outside the project.
- Long pytest assertion lines are shortened. pytest prints whole values in assertion lines and repeats them in `+  where` lines, so one failing string comparison could put several KB of the same text in the LLM message. Lines over about 400 characters keep their first 240 and last 120 characters.
- An issue reported on a decorator line now shows the decorated function in the code excerpt, instead of stopping before its `def`.
- `vulture` keeps the project's own `[tool.vulture]` settings. cq passed `--ignore-decorators` and `--exclude` on the command line, and vulture lets the command line replace the `ignore_decorators` and `exclude` lists in the project's config instead of adding to them. cq's framework decorators are now matched in the parser, and the project's `exclude` patterns are appended to cq's defaults.
- `vulture` reports fewer false positives. It no longer reports functions registered with `@*.template_filter`, `@*.context_processor`, `@tool` or `@*.tool`; mock setup attributes (`return_value`, `side_effect`, `__enter__`, `__exit__`); `mock_*` parameters added by `@patch`; pydantic's `model_config`; enum members, which are looked up by value; or the parameters of `__exit__` and `__aexit__`.
- `interrogate` skips a `test/` directory as well as `tests/`, and `skip_empty_init` treats an `__init__.py` that holds only comments as empty.
- `radon-hal` no longer scores files radon cannot parse. A syntax error set both Halstead metrics to 0.0 and the LLM message called it high estimated bug density. The file is now recorded with its error and left out of the scores, as `radon-mi` already did; `compile` and `ruff` report the syntax error.
- cq no longer prints `SyntaxWarning`s (such as invalid escape sequences) from the target project's source files.

## [0.4.0] - 2026-11-15

### Added

- Tool count is now 14: `kingfisher` and `uv-audit` take orders 5 and 6, and `pytest` through `ruff-format` move down two places (7 to 14).
- `kingfisher` tool (order 5, after `bandit`): scans the working tree for hardcoded secrets with [Kingfisher](https://github.com/mongodb/kingfisher) and reports them under the `secrets` metric. Any finding fails the gate (thresholds `0.9999`). Kingfisher is a 41 MB native binary, so it is not a cq dependency: install it once with `uv tool install kingfisher-bin`. When it is not on the `PATH` the tool is skipped with a warning. It runs with `--no-validate --no-update-check` (no network), `--redact` (the secret never reaches the cache or the output) and `--git-history none` (working tree only). The LLM message gives file, line and rule but no source excerpt, so the plaintext secret is not sent to the LLM. A `kingfisher:ignore` comment on the line silences a test fixture or false positive.
- `uv-audit` tool (order 6, after `kingfisher`): runs `uv audit` against `uv.lock` and reports known vulnerabilities in locked dependencies under the `dependencies` metric. Only advisories with a fix version count, and the same vulnerability listed by several advisory databases counts once. The LLM message names the package, the fixed versions and the `uv lock --upgrade-package` command. It is skipped with a warning when `uv`, `uv.lock` or the network is unavailable, and when checking a single file. `uv audit` is still experimental in uv, so its output format may change.
  - **`cq check` now makes a network request by default**: `uv audit` queries the OSV advisory database. Turn it off with `--skip uv-audit` or `disable = ["uv-audit"]` under `[tool.cq]`.
  - **It can fail the gate with no source change.** One or two fixable vulnerabilities are a warning; three or more fall below the `0.8` error threshold and `cq check` exits `1`.
  - Results are cached like every other tool (up to 5 days), so a newly published advisory can take that long to appear on an unchanged project.

### Changed

- **`vulture` now reports unused functions, classes, methods and variables.** It ran at `--min-confidence 80`, which only reports unused imports and unreachable code, so dead functions were never found. It now runs at `--min-confidence 60`. **Expect new `dead_code` findings on the first run after upgrading.** Vulture cannot see dynamic use at this level, so common framework decorators (typer/click commands, web routes, pytest fixtures, validators, hook implementations) are ignored, and the LLM message for a finding below 80% confidence says how to keep a symbol through `ignore_names` under `[tool.vulture]` instead of deleting it.

### Removed

- `gate_strict` tool config field. Nothing ever read it, so `gate_strict = false` on the radon tools and `ruff-format` had no effect. Those tools stay out of the way of CI through their low `error_threshold` values, as before. A `gate_strict` key in a user-defined tool is ignored.

### Fixed

- `coverage` no longer collapses when the target project runs its tests in parallel with pytest-xdist (`-n` in its pytest `addopts`). `coverage run -m pytest` only measured the controller process, not the xdist workers, so a project at 92% coverage scored 17% and failed the gate. The coverage tool now runs pytest through a small script, `py_cq/runners/pytest_serial.py`, that adds `-n 0` when xdist is installed, keeping the coverage run in one process. The `pytest` tool still runs in parallel when the project asks for it. User-defined tools can use the script through the new `{pytest_serial}` command placeholder.
- `interrogate` no longer counts tests in docstring coverage. cq's own `-e .claude` replaced any exclude set in the project's `pyproject.toml`, and relative excludes resolved against cq's working directory, so tests could not be left out. The exclude is now anchored to the target path, matching `bandit` and `coverage`.
- `ruff` and `ruff-format` no longer scan `.venv` when the target project is not a git repository. Both commands passed `--exclude`, which replaces ruff's default exclude list instead of adding to it, so virtualenv files were linted, dragged the score down and could be reported as the top defect. They now pass `--extend-exclude`, for the built-in `.claude` exclusion and for user excludes.
- README no longer claims the cache carries "no pickle risk". cq stores results as JSON and never writes pickles, but `diskcache` will still unpickle an entry that someone with write access to `~/.cache/cq` plants there (CVE-2025-69872, no fixed release yet).
- A tool run that fails with no output (tool not on `PATH`, or offline) is no longer cached. Before, installing `kingfisher` or reconnecting for `uv-audit` had no effect for up to 5 days, until the project's files changed or the cache was cleared.

## [0.3.1] - 2026-10-12

### Added

- `ruff-format` tool (order 12): reports the fraction of files already formatted by `ruff format`. Ordered last and non-strict, so formatting never outranks real defects or blocks CI by default. Markdown files are ignored. Output from `ruff < 0.16` is parsed as well.

### Fixed

- Docs and help text: tool count is 12 everywhere, `cq config` usage shows `--path`, `-o` help lists `raw` and `llm-json`, and the README table output includes `ruff-format`.

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
