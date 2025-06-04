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

        print(raw_result)
        success = True
        failed_files: dict[str, str] = {}
        
        # this error parsing is wrong. See the comment above
        # Successfull compilation is marked with "Compiling"
        # Skipped directories are marked "Listing" and can be ignored
        # Failed compilation is marked *** File "filename", line linenumber
        # .... then more error help until the end or the next Compiling or Listing or errror
        
        if raw_result.stderr:
            # Parse compileall error output
            for line in raw_result.stderr.splitlines():
                if "Error compiling" in line:
                    success = False
                    parts = line.split("Error compiling ")
                    if len(parts) > 1:
                        file_path = parts[1].strip("'").strip()
                        failed_files[file_path] = line

        score = 1.0 if success else 0.0
        tr = ToolResult(raw=raw_result, metrics={"compile": score})
        
        if raw_result.stdout:
            tr.details["stdout"] = raw_result.stdout
        if raw_result.stderr:
            tr.details["stderr"] = raw_result.stderr
        if failed_files:
            tr.details["failed_files"] = failed_files
            
        tr.details["return_code"] = raw_result.return_code
        return tr
