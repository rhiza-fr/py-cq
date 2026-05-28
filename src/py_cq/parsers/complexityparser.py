"""Provides a `ComplexityParser` that converts raw complexity-analysis output into structured `ToolResult` objects for downstream use."""

import json

from py_cq.localtypes import AbstractParser, RawResult, ToolResult
from py_cq.parsers.common import find_function_source, score_logistic_variant


class ComplexityParser(AbstractParser):
    """Parse raw output from a complexity analysis tool into structured results.

    This parser accepts a :class:`~tools.core.RawResult` containing the raw
    ``stdout`` of a static-analysis or profiling tool.  It validates the
    JSON payload, extracts per-file and per-function metrics, and returns a
    :class:`~tools.core.ToolResult` that holds the parsed data, a
    per-item details dictionary, and overall summary metrics such as the
    overall simplicity score.

    Example
    -------
    >>> parser = ComplexityParser()
    >>> raw = RawResult(stdout='{"main.py":[{"name":"foo","complexity":12,"rank":"B"}]}',
    ...                 return_code=0)
    >>> result = parser.parse(raw)
    >>> result.metrics['simplicity']
    0.4"""

    def parse(self, raw_result: RawResult) -> ToolResult:
        """Parse raw tool output into a structured :class:`~tools.core.ToolResult`.

        The method accepts a :class:`~tools.core.RawResult` that contains the raw
        ``stdout`` from a complexity analysis tool.  The ``stdout`` is expected to
        be a JSON string mapping file names to lists of function descriptors.
        Each descriptor should at least contain a ``name`` and a ``complexity``
        value, and may optionally include a ``rank``.  The parser converts each
        function into a *simplicity* score using the logistic variant
        (`score_logistic_variant`).  The overall simplicity score is the mean of
        all function scores.  The resulting :class:`~tools.core.ToolResult`
        holds the original raw result, a ``details`` dictionary keyed by file
        and function names (with simplicity and rank), and a ``metrics``
        dictionary that contains the overall simplicity value.  The tool's
        return code is also recorded in ``details['return_code']``.

        Args:
            raw_result (RawResult):
                The raw result from a complexity analysis tool.  It must expose a
                ``stdout`` attribute containing a JSON string that maps file
                names to lists of function descriptors, and a ``return_code``
                attribute.

        Returns:
            ToolResult: A structured result that includes the original raw result,
            per-file/function details with simplicity scores and ranks, and a
            metrics dictionary that holds the overall simplicity score.

        Raises:
            json.JSONDecodeError: If ``raw_result.stdout`` cannot be parsed as
                JSON.

        Example:
            >>> raw = RawResult(stdout='{"main.py": [{"name": "foo", "complexity": 12, "rank": "B"}]}', return_code=0)
            >>> parser = ComplexityParser()
            >>> result = parser.parse(raw)
            >>> result.metrics["simplicity"]
            0.4"""
        tr = ToolResult(raw=raw_result)
        try:
            data = json.loads(raw_result.stdout)
        except (json.JSONDecodeError, ValueError):
            tr.metrics["simplicity"] = 0.0
            return tr
        if not isinstance(data, dict):
            tr.metrics["simplicity"] = 0.0
            return tr
        score = 0
        num_items = 0
        max_complexity = 30
        for file, functions in data.items():
            file_name = file.replace("\\", "/")
            if file_name not in tr.details:
                tr.details[file_name] = {}
            for function in functions:
                num_items += 1
                function_score = score_logistic_variant(
                    function.get("complexity", max_complexity), max_complexity
                )
                score += function_score
                tr.details[file_name][function["name"]] = {
                    "simplicity": function_score,
                    "rank": function.get("rank", "F"),
                }
        tr.metrics["simplicity"] = score / num_items if num_items > 0 else 0.0
        return tr

    def format_llm_message(self, tr: ToolResult, *, context_lines: int = 15, limit: int = 1) -> str:
        worst_file = worst_func = worst_rank = None
        worst_score = 1.0
        for file, funcs in tr.details.items():
            if not isinstance(funcs, dict):
                continue
            for func_name, data in funcs.items():
                score = data.get("simplicity", 1.0)
                if score < worst_score:
                    worst_score = score
                    worst_file = file
                    worst_func = func_name
                    worst_rank = data.get("rank", "F")
        if worst_file is None or worst_func is None:
            if tr.metrics:
                metric_name, value = next(iter(tr.metrics.items()))
                return f"**{metric_name}** score: {value:.3f}"
            return "No complexity details available"
        source = find_function_source(worst_file, worst_func, max_lines=context_lines)
        header = f"`{worst_file}::{worst_func}` — cyclomatic complexity rank **{worst_rank}**"
        parts = [header]
        if source:
            parts.append(source)
        parts.append("Cyclomatic complexity is too high. Break this function into smaller, single-purpose helpers.")
        return "\n\n".join(parts)
