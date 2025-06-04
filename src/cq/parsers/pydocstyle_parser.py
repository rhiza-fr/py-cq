from cq.localtypes import AbstractParser, RawResult, ToolResult
from cq.parsers.common import inv_normalize


class PydocstyleParser(AbstractParser):
    def parse(self, raw_result: RawResult) -> ToolResult:
        # .\data\problems\travelling_salesman\ts_bad.py:1 at module level:
        #         D100: Missing docstring in public module
        # .\data\problems\travelling_salesman\ts_bad.py:13 in public function `find_nearest_city`:
        #         D200: One-line docstring should fit on one line with quotes (found 3)
        # .\data\problems\travelling_salesman\ts_bad.py:13 in public function `find_nearest_city`:
        #         D212: Multi-line docstring summary should start at the first line
        # .\data\problems\travelling_salesman\ts_bad.py:27 in public function `generate_tour`:
        #         D200: One-line docstring should fit on one line with quotes (found 3)
        # .\data\problems\travelling_salesman\ts_bad.py:27 in public function `generate_tour`:
        #         D212: Multi-line docstring summary should start at the first line
        # .\data\problems\travelling_salesman\ts_bad.py:48 in public function `main`:
        #         D103: Missing docstring in public function

        tr = ToolResult(raw=raw_result)
        if raw_result.stderr:  # normal for pydocstyle to return exit code 1, with stdout
            score = 0.0
            tr.details["stderr"] = raw_result.stderr
        else:
            MAX_DOCSTRING_ERRORS = 10
            lines = raw_result.stdout.splitlines()
            score = inv_normalize(len(lines) / 2, MAX_DOCSTRING_ERRORS)
        tr.metrics = {"docstyle": score}
        tr.details["parseme"] = raw_result.stdout  # TODO parse this
        tr.details["return_code"] = raw_result.return_code
        return tr
