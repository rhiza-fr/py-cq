from cq.localtypes import AbstractParser, RawResult, ToolResult
from cq.parsers.common import score_logistic_variant


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
        MAX_DOCSTRING_ERRORS = 60
        lines = raw_result.stdout.splitlines()
        errors = len(lines) / 2
        score = score_logistic_variant(errors, scale_factor=MAX_DOCSTRING_ERRORS)  # 5 per file would make sense
        # score = score_logistic_variant(len(lines) / 2, MAX_DOCSTRING_ERRORS)
        print("Docstring", len(lines) / 2, score)
        tr.metrics = {"docstyle": score}
        tr.details["parseme"] = raw_result.stdout  # TODO parse this
        tr.details["return_code"] = raw_result.return_code
        return tr
