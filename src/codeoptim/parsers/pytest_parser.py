import re

from codeoptim.localtypes import AbstractParser, RawResult, ToolResult


class PytestParser(AbstractParser):
    def parse(self, raw_result: RawResult) -> ToolResult:
        # Simplified parsing - replace with actual logic
        lines = raw_result.stdout.splitlines()
        tr = ToolResult(raw=raw_result)
        if "no tests ran" in raw_result.stdout:
            tr.metrics["test"] = 0
        else:
            tests_found = dict()
            num_tests = 0
            passed_tests = 0
            for line in lines:
                # data/problems/travelling_salesman/ts_good.py::test_calc_dist PASSED
                tests_match = re.search(r"(.*\.py)::(\w+) (\w+)", raw_result.stdout)
                if tests_match:
                    test_file = tests_match.group(1)
                    test_name = tests_match.group(2)
                    test_status = tests_match.group(3)
                    if test_file not in tests_found:
                        tests_found[test_file] = {}
                        tests_found[test_file][test_name] = test_status
                    num_tests += 1
                    if test_status == "PASSED":
                        passed_tests += 1
            tr.metrics["tests"] = passed_tests / num_tests if num_tests else 0
            tr.details = tests_found
            # TODO count the number of errors
            tr.details["return_code"] = raw_result.return_code
        return tr
