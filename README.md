# CQ - Code Quality Analysis Tool

CQ is a Python CLI tool for iterative, LLM-assisted code improvement. The primary workflow is:

```bash
cq check -o llm   # get the single most critical defect as markdown
```

Feed that output to an LLM, apply the fix, repeat until the score is clean.

## Install

```bash
uv tool install py-cq
```

## Tools

CQ runs these tools in parallel:

| Priority | Tool | Measures |
|----------|------|----------|
| 1 | compileall | Syntax errors |
| 2 | bandit | Security vulnerabilities |
| 3 | ruff | Lint / style |
| 4 | ty | Type errors |
| 5 | pytest | Test pass rate |
| 6 | coverage | Test coverage |
| 7 | radon cc | Cyclomatic complexity |
| 8 | radon mi | Maintainability index |
| 9 | radon hal | Halstead volume / bug estimate |
| 10 | vulture | Dead code |
| 11 | interrogate | Docstring coverage |

## Usage

```bash
# LLM workflow: get the top defect as markdown (primary use case)
cq check -o llm

# Rich table with all metrics (default, also saves .cq.json)
cq check

# Numeric score only — useful in CI or scripts
cq check -o score

# Full JSON output
cq check -o json

# Explicit path (defaults to current directory)
cq check path/to/project/
cq check path/to/file.py

# Run sequentially instead of in parallel
cq check --sequential

# Clear cached results before running
cq check --clear-cache

# Save table output to a custom file
cq check --out-file custom_results.json
```

## Output

```bash
cq check .
┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┓
┃ Tool               ┃                          Metric ┃ Score     ┃ Status    ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━┩
│ compile            │                         compile │ 1.000     │ OK        │
│ bandit             │                        security │ 1.000     │ OK        │
│ ruff               │                            lint │ 1.000     │ OK        │
│ ty                 │                      type_check │ 1.000     │ OK        │
│ pytest             │                           tests │ 1.000     │ OK        │
│ coverage           │                        coverage │ 0.930     │ OK        │
│ radon cc           │                      simplicity │ 0.983     │ OK        │
│ radon mi           │                 maintainability │ 0.871     │ OK        │
│ radon hal          │                   file_bug_free │ 0.915     │ OK        │
│ radon hal          │                  file_smallness │ 0.828     │ OK        │
│ radon hal          │              functions_bug_free │ 0.913     │ OK        │
│ radon hal          │             functions_smallness │ 0.724     │ OK        │
│ vulture            │                       dead_code │ 1.000     │ OK        │
│ interrogate        │                    doc_coverage │ 1.000     │ OK        │
│                    │                           Score │ 0.966     │           │
└────────────────────┴─────────────────────────────────┴───────────┴───────────┘

cq check -o score
0.9662730667181059 # this is designed to approach but not reach 1.0
```

## Configuration

Add a `[tool.cq]` section to your project's `pyproject.toml`:

```toml
[tool.cq]
# Skip tools that are slow or not relevant to your project
disable = ["coverage", "interrogate"]

# Override warning/error thresholds per tool
[tool.cq.thresholds.coverage]
warning = 0.9
error = 0.7
```

Tool IDs match the keys in `config/tools.yaml`: `compilation`, `bandit`, `ruff`, `ty`, `pytest`, `coverage`, `complexity`, `maintainability`, `halstead`, `vulture`, `interrogate`.

## LLM workflow

`-o llm` selects the single worst-scoring tool and formats its top defect as
concise markdown. The LLM fixes it, you re-run `cq check -o llm`, and repeat
until all tools are green. Priority order ensures the most critical category
(security, type errors, failing tests) is fixed before cosmetic ones.
