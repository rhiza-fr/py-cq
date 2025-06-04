from pathlib import Path
from typing import Dict
from cq.localtypes import AbstractParser, RawResult, ToolResult


class CompileParser(AbstractParser):
    def parse(self, raw_result: RawResult) -> ToolResult:
        # For projects, compileall returns 0 even if some files fail
        # So we need to parse the output to determine success
        success = True
        failed_files: Dict[str, str] = {}
        
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
