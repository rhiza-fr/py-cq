import json

from cq.localtypes import AbstractParser, RawResult, ToolResult


class MaintainabilityParser(AbstractParser):
    def parse(self, raw_result: RawResult) -> ToolResult:
        # Simplified parsing - replace with actual logic
        # radon mi -s --json <path_to_file>
        # {".\\data\\problems\\travelling_salesman\\ts_good.py": {"mi": 73.77377419557578, "rank": "A"}}

        tr = ToolResult(raw=raw_result)
        data = json.loads(raw_result.stdout)
        num_items = 0
        score = 0
        for file, values in data.items():
            if "error" in values:
                tr.details[file.replace("\\", "/")] = {
                    "mi": 0.0,
                    "rank": "F",
                    "error": values["error"],
                }
            if "mi" in values:
                file_score = values["mi"] / 100.0  # Normalize to 0-1 range
                score += file_score
                num_items += 1
                tr.details[file.replace("\\", "/")] = {"mi": file_score, "rank": values["rank"]}
        tr.metrics["maintainability"] = score / num_items if num_items > 0 else 0.0
        tr.details["return_code"] = raw_result.return_code
        return tr
