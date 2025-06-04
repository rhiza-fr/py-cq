from cq.localtypes import AbstractParser, RawResult, ToolResult


class CompileParser(AbstractParser):
    def parse(self, raw_result: RawResult) -> ToolResult:
        
        # Listing '.\\src\\cq'...
        # Listing '.\\src\\cq\\parsers'...
        # Compiling '.\\data\\problems\\travelling_salesman\\ts_bad.py'...
        # Compiling '.\\data\\problems\\travelling_salesman\\ts_good.py'...
        # Compiling '.\\src\\cq\\__init__.py'...
        # Compiling '.\\src\\cq\\cli.py'...
        # Compiling '.\\src\\cq\\config.py'...
        # Compiling '.\\src\\cq\\execution_engine.py'...
        # Compiling '.\\src\\cq\\localtypes.py'...
        # Compiling '.\\src\\cq\\main.py'...
        # ***   File ".\data\problems\travelling_salesman\ts_bad.py", line 31
        #     error = {a = b}
        #              ^^^^^
        # SyntaxError: invalid syntax. Maybe you meant '==' or ':=' instead of '='?

        # Compiling '.\\src\\cq\\metric_aggregator.py'...
        # Compiling '.\\src\\cq\\parsers\\__init__.py'...
        # Compiling '.\\src\\cq\\parsers\\common.py'...
        # Compiling '.\\src\\cq\\parsers\\complexity_parser.p

        total_attempts = 0
        successful_compiles = 0
        failed_files: dict[str, str] = {}
        current_error = None
        
        # Process stdout first for successful compilations
        if raw_result.stdout:
            for line in raw_result.stdout.splitlines():
                if line.startswith("Compiling "):
                    total_attempts += 1
                    successful_compiles += 1
                elif line.startswith("***   File "):
                    # This indicates a compilation error
                    total_attempts += 1
                    successful_compiles -= 1  # undo previous increment
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
                    failed_files[current_error["file"]] = current_error["error"]
                    current_error = None

        # Process stderr for any additional errors
        if raw_result.stderr:
            for line in raw_result.stderr.splitlines():
                if "Error compiling" in line:
                    total_attempts += 1
                    parts = line.split("Error compiling ")
                    if len(parts) > 1:
                        file_path = parts[1].strip("'").strip()
                        failed_files[file_path] = line

        # Calculate score as ratio of successful compiles to total attempts
        score = successful_compiles / total_attempts if total_attempts > 0 else 1.0
        tr = ToolResult(raw=raw_result, metrics={"compile": score})
        
        if raw_result.stdout:
            tr.details["stdout"] = raw_result.stdout
        if raw_result.stderr:
            tr.details["stderr"] = raw_result.stderr
        if failed_files:
            tr.details["failed_files"] = failed_files
            
        tr.details["return_code"] = raw_result.return_code
        return tr
