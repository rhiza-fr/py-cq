# CQ - Python Code Quality Analysis Tool

Feed the results from 11+ code quality tools to an LLM. Minimal tokens.

Why? It removes the mental burden of understanding all these tools and parsing their results.

The primary workflow is:

```bash
# get the single most critical defect as markdown
cq check . -o llm
```

```python
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
Feed to an LLM with edit tools and repeat until there are no issues, e.g.

```python
cq check . -o llm | claude -p "fix this"
# or
cq check . -o llm | ollama run gpt-oss:20b "Explain how to fix this"
```


## Install

```bash
# install the `cq` command line tool from PyPi
uv tool install python-code-quality

# or, clone it then install 
git clone https://github.com/rhiza-fr/py-cq.git
cd py-cq
uv tool install .
```

## Tools

These tools are run in **parallel** except:
When running '-o llm', we run sequentially and exit early at the first error.

| Order | Tool | Measures |
|----------|------|----------|
| 1 | compileall | Syntax errors |
| 2 | ruff | Lint / style |
| 3 | ty | Type errors |
| 4 | bandit | Security vulnerabilities |
| 5 | pytest | Test pass rate |
| 6 | coverage | Test coverage |
| 7 | radon cc | Cyclomatic complexity |
| 8 | radon mi | Maintainability index |
| 9 | radon hal | Halstead volume / bug estimate |
| 10 | vulture | Dead code |
| 11 | interrogate | Docstring coverage |

Diskcache is used to cache tool output for lightning fast re-runs. Sane defaults: <100 Mb, <5 days, No pickle risk.


## Usage

```bash
cq check .                 # Table overview of scores for humans
cq check . -o llm          # Top defect as markdown for LLMs
cq check . -o score        # Numeric score only for CI
cq check . -o json         # Detailed parsed JSON output for jq
cq check . -o raw          # Raw tool output for debug
cq check path/to/file.py   # Just one file (skips pytest and coverage)
cq check . --workers 1     # Run sequentially if you like things slow
cq check . --clear-cache   # Clear cached results before running (rarely needed)
cq config path/to/project/ # Show effective tool configuration
```

**Exit codes:** `cq check` exits with code `1` if any tool metric falls below its `error_threshold`, making it suitable as a CI gate:

```bash
cq check . && deploy        # block deploy on errors
cq check . -o score         # print score, exit 1 on errors
```

## Table output

```bash
> cq check .
```

```python
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━┓
┃ Tool             ┃     Time ┃                    Metric ┃ Score   ┃ Status   ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━┩
│ compile          │    0.42s │                   compile │ 1.000   │ OK       │
│ ruff             │    0.17s │                      lint │ 1.000   │ OK       │
│ ty               │    0.33s │                type_check │ 1.000   │ OK       │
│ bandit           │    0.56s │                  security │ 1.000   │ OK       │
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

## Single score output
```bash
> cq check . -o score
```
```python
0.9662730667181059 # this is designed to approach but not reach 1.0
```

## Json output
```bash
> cq check . -o json
```

```json
[
  {
    "tool_name": "compile",
    "metrics": {
      "compile": 1.0
    },
    "details": {},
    "duration_s": 0.05611889995634556
  }
  ...
]
```

## Raw output
```bash
> cq check . -o raw
```

```json
[
  {
    "tool_name": "compile",
    "command": "D:\\ai\\py-cq\\.venv\\Scripts\\python.exe -m compileall -r 10 -j 8 . -x .*venv",
    "stdout": "",
    "stderr": "",
    "return_code": 0,
    "timestamp": "2026-02-20 10:01:22"
  }
  ...
]
```

## Configuration

Add a `[tool.cq]` section to your project's `pyproject.toml`:

```toml
[tool.cq]
# Skip tools that are slow or not relevant to your project
disable = ["coverage", "interrogate"]

# Lines of source context shown around each defect in LLM output (default: 15)
context_lines = 15

# Override warning/error thresholds per tool
[tool.cq.thresholds.coverage]
warning = 0.9
error = 0.7
```

Tool IDs match the keys in `config/config.yaml`: `compile`, `ruff`, `ty`, `bandit`, `pytest`, `coverage`, `radon-cc`, `radon-mi`, `radon-hal`, `vulture`, `interrogate`.


### Default config

```yaml
tools:

  compile:
    command: "{python} -m compileall -r 10 -j 8 {context_path} -x .*venv"
    parser: "CompileParser"
    order: 1
    warning_threshold: 0.9999
    error_threshold: 0.9999

  ruff:
    command: "{python} -m ruff check --output-format concise --no-cache {context_path}"
    parser: "RuffParser"
    order: 2
    warning_threshold: 0.9999
    error_threshold: 0.9

  ty:
    command: "{python} -m ty check --output-format concise --color never {context_path}"
    parser: "TyParser"
    order: 3
    warning_threshold: 0.9999
    error_threshold: 0.8
    run_in_target_env: true
    extra_deps:
      - ty

  bandit:
    command: "{python} -m bandit -r {context_path} -f json -q -s B101 --severity-level medium --exclude {input_path_posix}/.venv,{input_path_posix}/tests"
    parser: "BanditParser"
    order: 4
    warning_threshold: 0.9999
    error_threshold: 0.8

  pytest:
    command: "{python} -m pytest -v {context_path}"
    parser: "PytestParser"
    order: 5
    warning_threshold: 1.0
    error_threshold: 1.0
    run_in_target_env: true

  coverage:
    command: "{python} -m coverage run --omit=*/tests/*,*/test_*.py -m pytest {context_path} && {python} -m coverage report --omit=*/tests/*,*/test_*.py"
    parser: "CoverageParser"
    order: 6
    warning_threshold: 0.9
    error_threshold: 0.5
    run_in_target_env: true
    extra_deps:
      - coverage
      - pytest

  radon-cc:
    command: "{python} -m radon cc --json {context_path}"
    parser: "ComplexityParser"
    order: 7
    warning_threshold: 0.6
    error_threshold: 0.4

  radon-mi:
    command: "{python} -m radon mi -s --json {context_path}"
    parser: "MaintainabilityParser"
    order: 8
    warning_threshold: 0.6
    error_threshold: 0.4

  radon-hal:
    command: "{python} -m radon hal -f --json {context_path}"
    parser: "HalsteadParser"
    order: 9
    warning_threshold: 0.5
    error_threshold: 0.3

  vulture:
    command: "{python} -m vulture {context_path} --min-confidence 80 --exclude .venv,dist,.*_cache,docs,.git"
    parser: "VultureParser"
    order: 10
    warning_threshold: 0.9999
    error_threshold: 0.8

  interrogate:
    command: "{python} -m interrogate {context_path} -v --fail-under 0"
    parser: "InterrogateParser"
    order: 11
    warning_threshold: 0.8
    error_threshold: 0.3

```

## Respect

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
- [diskcache](https://github.com/grantjenks/python-diskcache)
- [typer](https://github.com/fastapi/typer)
