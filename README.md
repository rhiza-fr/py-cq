# CQ - Python Code Quality Analysis Tool

Python Code Quality Analysis Tool - feed the results from 11 CQ tools straight into an LLM. The primary workflow is:

```bash
cq check -o llm   # get the single most critical defect as markdown
```

Feed that output to an LLM, apply the fix, repeat until the score is clean.

## Install

```bash
uv tool install python-code-quality

# or
git pull https://github.com/rhiza-fr/py-cq.git
cd py-cq
uv tool install .
```

## Tools

CQ runs these tools in *parallel*:

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

# Run sequentially (1 worker) instead of in parallel
cq check --workers 1

# Clear cached results before running
cq check --clear-cache

# Save table output to a custom file
cq check --out-file custom_results.json

# Show effective tool configuration (thresholds, enabled/disabled status)
cq config
cq config path/to/project/
```

## Output

```bash
> cq check .
```

```python
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━┓
┃ Tool             ┃     Time ┃                    Metric ┃ Score   ┃ Status   ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━┩
│ compile          │    0.42s │                   compile │ 1.000   │ OK       │
│ bandit           │    0.56s │                  security │ 1.000   │ OK       │
│ ruff             │    0.17s │                      lint │ 1.000   │ OK       │
│ ty               │    0.33s │                type_check │ 1.000   │ OK       │
│ pytest           │    0.91s │                     tests │ 1.000   │ OK       │
│ coverage         │    1.26s │                  coverage │ 0.910   │ OK       │
│ radon cc         │    0.32s │                simplicity │ 0.982   │ OK       │
│ radon mi         │    0.38s │           maintainability │ 0.869   │ OK       │
│ radon hal        │    0.30s │             file_bug_free │ 0.928   │ OK       │
│ radon hal        │          │            file_smallness │ 0.851   │ OK       │
│ radon hal        │          │        functions_bug_free │ 0.913   │ OK       │
│ radon hal        │          │       functions_smallness │ 0.724   │ OK       │
│ vulture          │    0.32s │                 dead_code │ 1.000   │ OK       │
│ interrogate      │    0.36s │              doc_coverage │ 1.000   │ OK       │
│                  │          │                     Score │ 0.965   │          │
└──────────────────┴──────────┴───────────────────────────┴─────────┴──────────┘
```
```bash
> cq check . -o score
```
```python
0.9662730667181059 # this is designed to approach but not reach 1.0
```

```bash
> cq check . -o llm
```

```md
`data/problems/travelling_salesman/ts_bad.py:21` — **F841**: Local variable `unused_variable` is assigned to but never used

18:     min_dist = float("inf")
19:     nearest_city = None
20:     for city in cities:
21:         unused_variable = 67
22:         dist = calc_dist(current_city, city)
23:         if dist < min_dist:
24:             min_dist = dist
25:             nearest_city = city

Please fix only this issue. After fixing, run `cq check . -o llm` to verify.
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

## Tools

Many thanks to all the wonderful maintainers of :

- [compileall](https://docs.python.org/3/library/compileall.html)
- [bandit](https://github.com/PyCQA/bandit)
- [ruff](https://github.com/astral-sh/ruff)
- [ty](https://github.com/astral-sh/ty)
- [pytest](https://github.com/pytest-dev/pytest)
- [coverage.py](https://github.com/nedbat/coveragepy)
- [radon](https://github.com/rubik/radon)
- [vulture](https://github.com/jendrikseipp/vulture)
- [interrogate](https://github.com/econchick/interrogate)
