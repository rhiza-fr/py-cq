"""Utilities for parsing Halstead-based metrics.

This module implements :class:`HalsteadParser`, an ``AbstractParser`` that
converts the JSON output from Halstead metric tools into a
``ToolResult``.  It extracts bug estimates and program volume, applies
maximum thresholds, and aggregates file- and function-level metrics."""

import json

from cq.localtypes import AbstractParser, RawResult, ToolResult
from cq.parsers.common import score_logistic_variant


class HalsteadParser(AbstractParser):
    """Parses Halstead metric output and converts it into a `ToolResult`.

    Implements the `AbstractParser` interface for tools that emit
    Halstead-based JSON.  The `parse` method consumes a `RawResult`,
    extracts per-file and per-function metrics, applies the configured
    maximum bug and volume thresholds, and aggregates the results.
    The helper `extract_bugs_and_volume` performs the core calculation of
    bug-free and smallness scores.

    The parser also records the tool's return code and any errors in the
    result details."""

    def parse(self, raw_result: RawResult) -> ToolResult:
        """Parses Halstead tool JSON output and returns a ToolResult.

        The method reads ``raw_result.stdout``—a JSON string containing
        per-file and per-function Halstead metrics. For each file it
        populates a ``ToolResult`` detail entry with bug-free and
        smallness scores. If a file contains an ``error`` key, the
        associated metrics are set to zero and the error message is
        stored. File-level and function-level thresholds are applied
        when computing metrics via :meth:`extract_bugs_and_volume`.

        After processing all entries, aggregate metrics
        (``file_bug_free``, ``file_smallness``,
        ``functions_bug_free``, ``functions_smallness``) are calculated
        from the minimum values observed. The tool's return code is also
        recorded in the ``ToolResult`` details.

        Args:
            raw_result (RawResult): The raw output from a Halstead
                analysis tool. Its ``stdout`` attribute must contain a
                JSON string with the expected structure.

        Returns:
            ToolResult: A populated ``ToolResult`` instance with
                detailed per-file and per-function metrics, aggregate
                metrics, and the tool's return code.

        Raises:
            json.JSONDecodeError: If the ``stdout`` cannot be parsed as
                JSON."""
        # radon hal -f --json .\data\problems\travelling_salesman\ts_bad.py
        # {".\\data\\problems\\travelling_salesman\\ts_bad.py":
        #  {"total": {"h1": 6, "h2": 18, "N1": 13, "N2": 22, "vocabulary": 24, "length": 35, "calculated_length": 90.56842503028855, "volume": 160.4736875252405, "difficulty": 3.6666666666666665, "effort": 588.4035209258818, "time": 32.68908449588233, "bugs": 0.05349122917508017},
        #   "functions": {"calc_dist": {"h1": 3, "h2": 9, "N1": 5, "N2": 10, "vocabulary": 12, "length": 15, "calculated_length": 33.28421251514428, "volume": 53.77443751081735, "difficulty": 1.6666666666666667, "effort": 89.62406251802892, "time": 4.9791145843349405, "bugs": 0.017924812503605784}, "find_nearest_city": {"h1": 1, "h2": 2, "N1": 1, "N2": 2, "vocabulary": 3, "length": 3, "calculated_length": 2.0, "volume": 4.754887502163469, "difficulty": 0.5, "effort": 2.3774437510817346, "time": 0.1320802083934297, "bugs": 0.0015849625007211565}, "generate_tour": {"h1": 2, "h2": 5, "N1": 6, "N2": 8, "vocabulary": 7, "length": 14, "calculated_length": 13.60964047443681, "volume": 39.302968908806456, "difficulty": 1.6, "effort": 62.884750254090335, "time": 3.493597236338352, "bugs": 0.01310098963626882}, "main": {"h1": 0, "h2": 0, "N1": 0, "N2": 0, "vocabulary": 0, "length": 0, "calculated_length": 0, "volume": 0, "difficulty": 0, "effort": 0, "time": 0.0, "bugs": 0.0}}}
        tr = ToolResult(raw=raw_result)
        MAX_FILE_BUGS = 1
        MAX_FILE_VOLUME = 2000
        MAX_FUNCTION_BUGS = 0.2
        MAX_FUNCTION_VOLUME = 300
        min_file_nb = 1.0
        min_file_sm = 1.0
        min_function_nb = 1.0
        min_function_sm = 1.0
        data = json.loads(raw_result.stdout)
        for file, values in data.items():
            file_name = file.replace("\\", "/")
            if file_name not in tr.details:
                tr.details[file_name] = {
                    "bug_free": 0.0,
                    "smallness": 0.0,
                    "functions": {},
                }
            if "error" in values:
                min_file_nb = 0.0
                min_file_sm = 0.0
                min_function_nb = 0.0
                min_function_sm = 0.0
                tr.details[file_name]["error"] = values["error"]
            if "total" in values:
                nb, sm = self.extract_bugs_and_volume(
                    values.get("total", {}), MAX_FILE_BUGS, MAX_FILE_VOLUME
                )
                min_file_nb = min(nb, min_file_nb)
                min_file_sm = min(sm, min_file_sm)
                tr.details[file_name]["bug_free"] = nb
                tr.details[file_name]["smallness"] = sm
                tr.details[file_name]["bugs"] = values["total"].get("bugs", 0)
                tr.details[file_name]["volume"] = values["total"].get("volume", 0)
            if "functions" in values:
                for function, function_values in values["functions"].items():
                    nb, sm = self.extract_bugs_and_volume(
                        function_values, MAX_FUNCTION_BUGS, MAX_FUNCTION_VOLUME
                    )
                    min_function_nb = min(nb, min_function_nb)
                    min_function_sm = min(sm, min_function_sm)
                    tr.details[file_name]["functions"][function] = {
                        "no_bugs": nb,
                        "smallness": sm,
                        "bugs": function_values.get("bugs", 0),
                        "volume": function_values.get("volume", 0),
                    }
        tr.metrics = {
            "file_bug_free": min_file_nb,
            "file_smallness": min_file_sm,
            "functions_bug_free": min_function_nb,
            "functions_smallness": min_function_sm,
        }
        return tr

    def format_llm_message(self, tr: ToolResult) -> str:
        """Return the worst Halstead offender as an actionable defect description."""
        if not tr.metrics:
            return "No Halstead details available"

        metric_name, score = min(tr.metrics.items(), key=lambda x: x[1])
        is_function_metric = metric_name.startswith("functions_")
        is_bug_metric = "bug_free" in metric_name

        worst_file = None
        worst_function = None
        worst_score = 1.0
        worst_bugs = None
        worst_volume = None

        for file_name, file_data in tr.details.items():
            if is_function_metric:
                for func_name, func_data in file_data.get("functions", {}).items():
                    s = func_data.get("no_bugs" if is_bug_metric else "smallness", 1.0)
                    if s < worst_score:
                        worst_score = s
                        worst_file = file_name
                        worst_function = func_name
                        worst_bugs = func_data.get("bugs")
                        worst_volume = func_data.get("volume")
            else:
                s = file_data.get("bug_free" if is_bug_metric else "smallness", 1.0)
                if s < worst_score:
                    worst_score = s
                    worst_file = file_name
                    worst_bugs = file_data.get("bugs")
                    worst_volume = file_data.get("volume")

        if worst_file is None:
            return f"**{metric_name}** score: {score:.3f}"

        location = f"`{worst_file}` — function `{worst_function}`" if worst_function else f"`{worst_file}`"
        if is_bug_metric:
            detail = f" (Halstead bug estimate: {worst_bugs:.3f})" if worst_bugs is not None else ""
            return (
                f"{location} has high estimated bug density{detail}\n\n"
                f"Reduce complexity by extracting helper functions or simplifying logic."
            )
        else:
            detail = f" (volume: {worst_volume:.0f})" if worst_volume is not None else ""
            return (
                f"{location} is too large{detail}\n\n"
                f"Split into smaller functions or modules."
            )

    def extract_bugs_and_volume(
        self, values: dict, max_bugs: float, max_volume: float
    ) -> tuple[float, float]:
        """Calculates bug-free and smallness scores from Halstead metrics using logistic scoring."""
        no_bugs_score = score_logistic_variant(values.get("bugs", max_bugs), max_bugs)
        smallness_score = score_logistic_variant(
            values.get("volume", max_volume), max_volume
        )
        return (no_bugs_score, smallness_score)
