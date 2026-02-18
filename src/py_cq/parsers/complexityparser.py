"""Provides a `ComplexityParser` that converts raw complexity-analysis output into structured `ToolResult` objects for downstream use."""

import json

from py_cq.localtypes import AbstractParser, RawResult, ToolResult
from py_cq.parsers.common import score_logistic_variant


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
        data = json.loads(raw_result.stdout)
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
