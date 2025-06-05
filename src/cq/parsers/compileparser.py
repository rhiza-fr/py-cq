from cq.localtypes import AbstractParser, RawResult, ToolResult
from cq.parsers.common import score_logistic_variant


class CompileParser(AbstractParser):
    def parse(self, raw_result: RawResult) -> ToolResult:
        # Listing '.\\src\\cq'...
        # Listing '.\\src\\cq\\parsers'...
        # Compiling '.\\data\\problems\\travelling_salesman\\ts_bad.py'...
        # Compiling '.\\src\\cq\\main.py'...
        # ***   File ".\data\problems\travelling_salesman\ts_bad.py", line 31
        #     error = {a = b}
        #              ^^^^^
        # SyntaxError: invalid syntax. Maybe you meant '==' or ':=' instead of '='?

        # Compiling '.\\src\\cq\\metric_aggregator.py'...

        compilations = 0
        failed_files: dict[str, str] = {}
        current_error = None

        # Process stdout first for successful compilations
        if raw_result.stdout:
            for line in raw_result.stdout.splitlines():
                if line.startswith("Compiling "):
                    compilations += 1
                elif line.startswith("***   File "):
                    # This indicates a compilation error
                    file_path = line.split('"')[1]
                    current_error = {"file": file_path, "error": line}
                elif current_error and line.strip():
                    # Append additional error context
                    current_error["error"] += "\n" + line
                elif line.startswith("Listing "):
                    # Skip directory listings
                    continue
                elif current_error and not line.strip():
                    # Empty line ends the error block
                    failed_files[current_error["file"].replace("\\", "/")] = current_error[
                        "error"
                    ].replace("\\", "/")
                    current_error = None

        # Calculate score as ratio of successful compiles to total attempts
        failure_ratio = len(failed_files) / compilations if compilations > 0 else 0.0
        score = score_logistic_variant(failure_ratio, scale_factor=0.25)
        # score = (compilations - len(failed_files)) / compilations if compilations > 0 else 0.0

        # I know raw should raw but meh!!!
        # for sanities sake remove all the Listing lines ... wtf? python/windows
        raw_result.stdout = "\n".join(
            [
                line.replace("\\\\", "/")
                for line in raw_result.stdout.splitlines()
                if not line.startswith("Listing")
            ]
        )
        tr = ToolResult(raw=raw_result, metrics={"compile": score})

        if failed_files:
            tr.details["failed_files"] = failed_files

        tr.details["return_code"] = raw_result.return_code
        return tr
