from cq.localtypes import AbstractParser, RawResult, ToolResult


class CoverageParser(AbstractParser):
    def parse(self, raw_result: RawResult) -> ToolResult:
        # Simplified parsing - replace with actual logic
        tr = ToolResult(raw=raw_result)
        tr.metrics["coverage"] = 0.0
        # data\problems\travelling_salesman\ts_good.py      37     26    30%
        # TOTAL                                             37     26    30%
        lines = raw_result.stdout.splitlines()
        coverage_lines = [line for line in lines if line.endswith("%")]
        # print(f"Coverage lines found: {coverage_lines}")
        details = {}
        for line in coverage_lines:
            parts = line.split()
            if len(parts) == 4:
                file_name = parts[0]
                try:
                    coverage_percentage = float(parts[2]) / 100.0
                except ValueError:
                    print(f"Error parsing coverage percentage from line: {line}")
                    coverage_percentage = 0.0
                if file_name == "TOTAL":
                    tr.metrics["coverage"] = coverage_percentage
                else:
                    details[file_name.replace("\\", "/")] = coverage_percentage
        tr.details = details
        tr.details["return_code"] = raw_result.return_code
        return tr
