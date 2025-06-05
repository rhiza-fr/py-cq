import json

from cq.localtypes import AbstractParser, RawResult, ToolResult
from cq.parsers.common import score_logistic_variant


class ComplexityParser(AbstractParser):
    def parse(self, raw_result: RawResult) -> ToolResult:
        # Simplified parsing - replace with actual logic
        # radon cc --json <path_to_file>
        # {".\\data\\problems\\travelling_salesman\\ts_good.py": [
        #    {"type": "function", "rank": "A", "name": "nearest_neighbor", "complexity": 4, "col_offset": 0, "lineno": 9, "endline": 39, "closures": []}, ... ]}

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
                if function == "error":
                    tr.details[file_name]["error"] = {
                        "simplicity": 0,
                        "rank": "F",
                        "message": functions["error"],
                    }
                    break
                num_items += 1
                if file_name not in tr.details:
                    tr.details[file_name] = {}
                function_score = score_logistic_variant(
                    function.get("complexity", max_complexity), max_complexity
                )
                score += function_score
                tr.details[file_name][function["name"]] = {
                    "simplicity": function_score,
                    "rank": function.get("rank", "F"),
                }

        tr.metrics["simplicity"] = score / num_items if num_items > 0 else 0.0
        tr.details["return_code"] = raw_result.return_code
        return tr
