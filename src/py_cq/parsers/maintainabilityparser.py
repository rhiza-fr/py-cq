"""Module providing a concrete parser for maintainability analysis tools.

The `MaintainabilityParser` implements the `AbstractParser` interface to
convert raw JSON output from a maintainability tool into a
`ToolResult` structure that other components of the framework can consume."""

import json

from py_cq.localtypes import AbstractParser, RawResult, ToolResult
from py_cq.parsers.common import score_logistic_variant


class MaintainabilityParser(AbstractParser):
    """Parses maintainability metrics from raw tool output into :class:`ToolResult` objects.

    This parser consumes the JSON produced by a maintainability analysis tool on
    ``stdout``. For each file it extracts the maintainability index (`mi`) and
    rank, converts the index into a normalized score using
    :func:`score_logistic_variant`, aggregates per-file scores, and returns a
    :class:`ToolResult` containing an overall maintainability metric and
    detailed per-file information.

    It implements the :meth:`parse` method required by :class:`AbstractParser`
    and is intended for use by the framework to transform raw results into a
    structured format."""

    def parse(self, raw_result: RawResult) -> ToolResult:
        """Parses maintainability metrics from a raw tool result.

        The parser expects the tool to output JSON on ``stdout`` where each key is a file name mapping to a dictionary that contains at least an ``mi`` value (maintainability index) and a ``rank`` string.  If a file entry contains an ``error`` key, that file is recorded with a zero score and the error message.

        For each file with a valid ``mi`` value the method converts the raw maintainability index into a score using :func:`score_logistic_variant`, aggregates the scores, and stores per-file details.  The overall maintainability metric for the tool is then calculated as the average score across all processed files.

        Args:
            raw_result (RawResult): The raw result object produced by the underlying maintainability tool.
                It must provide a ``stdout`` attribute containing a JSON string and a ``return_code`` attribute.

        Returns:
            ToolResult: A structured result object containing:
                * ``metrics['maintainability']`` - the average score of all processed files (or ``0.0`` if none were processed).
                * ``details`` - a mapping from each file name (converted to use forward slashes) to a dictionary with keys ``mi``, ``rank``, and optionally ``error``.
                * ``details['return_code']`` - the tool's exit code."""
        tr = ToolResult(raw=raw_result)
        try:
            data = json.loads(raw_result.stdout)
        except (json.JSONDecodeError, ValueError):
            tr.metrics["maintainability"] = 0.0
            return tr
        if not isinstance(data, dict):
            tr.metrics["maintainability"] = 0.0
            return tr
        num_items = 0
        score = 0
        for file, values in data.items():
            if "error" in values:
                tr.details[file.replace("\\", "/")] = {
                    "mi": 0.0,
                    "rank": "F",
                    "error": values["error"],
                }
            elif "mi" in values:
                file_score = score_logistic_variant(100 - values["mi"], 85)
                score += file_score
                num_items += 1
                tr.details[file.replace("\\", "/")] = {
                    "mi": file_score,
                    "rank": values["rank"],
                }
        tr.metrics["maintainability"] = score / num_items if num_items > 0 else 0.0
        return tr
