# CQ - Code Quality Analysis Tool

CQ is a Python CLI tool for iterative, LLM-assisted code improvement. The primary workflow is:

```bash
cq check -o llm   # get the single most critical defect as markdown
```

Feed that output to an LLM, apply the fix, repeat until the score is clean.

## Tools

CQ runs these tools in priority order, in parallel:

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

## LLM workflow

`-o llm` selects the single worst-scoring tool and formats its top defect as
concise markdown. The LLM fixes it, you re-run `cq check -o llm`, and repeat
until all tools are green. Priority order ensures the most critical category
(security, type errors, failing tests) is fixed before cosmetic ones.
