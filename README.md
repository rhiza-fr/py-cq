# CQ - Code Quality Analysis Tool

A Python-based code quality analysis tool that runs multiple metrics and provides actionable feedback on code quality.

## What it does

CQ analyzes Python files and projects to provide comprehensive code quality metrics. It runs various analysis tools in parallel or sequentially and aggregates the results into a single quality score with detailed feedback.

## Usage

```bash
# Analyze a single Python file
cq run path/to/file.py

# Analyze a Python project (must contain pyproject.toml)
cq run path/to/project/

# Output results as JSON
cq run path/to/code --json

# Get only the final score
cq run path/to/code --score

# Run analysis tools in parallel for faster execution
cq run path/to/code --parallel

# Clear cached results before running
cq run path/to/code --clear-cache

# Specify output file for results
cq run path/to/code --out-file custom_results.json

# Set logging level
cq run path/to/code --log-level DEBUG
```

## Features

- **Multi-tool analysis**: Runs multiple code quality analysis tools
- **Parallel execution**: Can run tools in parallel for faster results
- **Caching**: Caches tool results to avoid re-running expensive analyses
- **Rich output**: Displays results in formatted tables with color-coded status indicators
- **Flexible output**: Can output as JSON, show only scores, or save to custom files
- **Help system**: Provides actionable suggestions based on analysis results
- **Project and file support**: Works with both individual Python files and full projects

## Output

The tool provides:
- Individual metric scores for each analysis tool
- Color-coded status indicators ( OK,   Warning, L Error)
- Overall quality score
- Actionable help suggestions based on the analysis results

Results are saved to `analysis_results.json` by default, or can be output directly to the console.