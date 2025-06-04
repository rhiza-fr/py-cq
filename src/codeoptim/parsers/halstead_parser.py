import json

from codeoptim.localtypes import AbstractParser, RawResult, ToolResult
from codeoptim.parsers.common import inv_normalize


class HalsteadParser(AbstractParser):
    def parse(self, raw_result: RawResult) -> ToolResult:
        # radon hal -f --json .\data\problems\travelling_salesman\ts_bad.py
        # {".\\data\\problems\\travelling_salesman\\ts_bad.py":
        #  {"total": {"h1": 6, "h2": 18, "N1": 13, "N2": 22, "vocabulary": 24, "length": 35, "calculated_length": 90.56842503028855, "volume": 160.4736875252405, "difficulty": 3.6666666666666665, "effort": 588.4035209258818, "time": 32.68908449588233, "bugs": 0.05349122917508017},
        #   "functions": {"calc_dist": {"h1": 3, "h2": 9, "N1": 5, "N2": 10, "vocabulary": 12, "length": 15, "calculated_length": 33.28421251514428, "volume": 53.77443751081735, "difficulty": 1.6666666666666667, "effort": 89.62406251802892, "time": 4.9791145843349405, "bugs": 0.017924812503605784}, "find_nearest_city": {"h1": 1, "h2": 2, "N1": 1, "N2": 2, "vocabulary": 3, "length": 3, "calculated_length": 2.0, "volume": 4.754887502163469, "difficulty": 0.5, "effort": 2.3774437510817346, "time": 0.1320802083934297, "bugs": 0.0015849625007211565}, "generate_tour": {"h1": 2, "h2": 5, "N1": 6, "N2": 8, "vocabulary": 7, "length": 14, "calculated_length": 13.60964047443681, "volume": 39.302968908806456, "difficulty": 1.6, "effort": 62.884750254090335, "time": 3.493597236338352, "bugs": 0.01310098963626882}, "main": {"h1": 0, "h2": 0, "N1": 0, "N2": 0, "vocabulary": 0, "length": 0, "calculated_length": 0, "volume": 0, "difficulty": 0, "effort": 0, "time": 0.0, "bugs": 0.0}}}
        tr = ToolResult(raw=raw_result)
        MAX_FILE_BUGS = 2
        MAX_FILE_VOLUME = 8000
        MAX_FUNCTION_BUGS = 1
        MAX_FUNCTION_VOLUME = 1000

        min_file_nb = 1.0
        min_file_sm = 1.0
        min_function_nb = 1.0
        min_function_sm = 1.0

        data = json.loads(raw_result.stdout)
        for file, values in data.items():
            file_name = file.replace("\\", "/")
            if file_name not in tr.details:
                tr.details[file_name] = {"bug_free": 0.0, "smallness": 0.0, "functions": {}}
            if "error" in values:
                min_file_nb = 0.0
                min_file_sm = 0.0
                min_function_nb = 0.0
                min_function_sm = 0.0
                tr.details[file_name]["error"] = values["error"]
            if "total" in values:
                nb, sm = self.extract_bugs_and_volume(
                    values.get("total", {}), MAX_FILE_BUGS, MAX_FILE_VOLUME
                )
                min_file_nb = min(nb, min_file_nb)
                min_file_sm = min(sm, min_file_sm)
                tr.details[file_name]["bug_free"] = nb
                tr.details[file_name]["smallness"] = sm
            if "functions" in values:
                for function, function_values in values["functions"].items():
                    nb, sm = self.extract_bugs_and_volume(
                        function_values, MAX_FUNCTION_BUGS, MAX_FUNCTION_VOLUME
                    )
                    min_function_nb = min(nb, min_function_nb)
                    min_function_sm = min(sm, min_function_sm)
                    tr.details[file_name]["functions"][function] = {
                        "no_bugs": nb,
                        "smallness": sm,
                    }

        tr.metrics = {
            "file_bug_free": min_file_nb,
            "file_smallness": min_file_sm,
            "functions_bug_free": min_function_nb,
            "functions_smallness": min_function_sm,
        }
        tr.details["return_code"] = raw_result.return_code
        return tr

    def extract_bugs_and_volume(
        self, values: dict, max_bugs: float, max_volume: float
    ) -> tuple[float, float]:
        """
        Extracts the bugs and smallness from the given data.
        """
        no_bugs_score = inv_normalize(values.get("bugs", max_bugs), max_bugs)
        smallness_score = inv_normalize(values.get("volume", max_volume), max_volume)

        return no_bugs_score, smallness_score
