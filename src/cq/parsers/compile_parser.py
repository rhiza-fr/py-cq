from cq.localtypes import AbstractParser, RawResult, ToolResult


class CompileParser(AbstractParser):
    def parse(self, raw_result: RawResult) -> ToolResult:
        score = 1.0 if raw_result.return_code == 0 else 0.0

        tr = ToolResult(raw=raw_result, metrics={"compile": score})
        if raw_result.stdout:
            tr.details["stdout"] = raw_result.stdout
        if raw_result.stderr:
            tr.details["stderr"] = raw_result.stderr
        tr.details["return_code"] = raw_result.return_code
        return tr
