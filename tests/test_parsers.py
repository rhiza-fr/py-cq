"""Tests for parser parse() methods and utility coverage."""

from cq.localtypes import AbstractParser, RawResult, ToolConfig, ToolResult, CombinedToolResults
from cq.llm_formatter import format_for_llm
from cq.parsers.common import inv_normalize, read_source_line, read_source_lines, score_logistic_variant
from cq.parsers.ruffparser import RuffParser
from cq.parsers.typarser import TyParser
from cq.parsers.pytestparser import PytestParser
from cq.parsers.pydocstyleparser import PydocstyleParser
from cq.parsers.compileparser import CompileParser
from cq.parsers.coverageparser import CoverageParser
from cq import hello


class MinimalParser(AbstractParser):
    """Parser subclass that only implements parse(), using base class defaults for rest."""
    def parse(self, raw_result): return ToolResult()


def raw(stdout="", return_code=0):
    return RawResult(tool_name="test", command="cmd", stdout=stdout, return_code=return_code)


# --- cq.__init__ ---

def test_hello():
    assert hello() == "Hello from cq!"


# --- common utilities ---

def test_inv_normalize():
    assert inv_normalize(0, 100) == 1.0
    assert inv_normalize(100, 100) == 0.0
    assert inv_normalize(50, 100) == 0.5
    assert inv_normalize(150, 100) == 0.0  # clamped


def test_read_source_lines_valid(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text("line one\nline two\nline three\nline four")
    result = read_source_lines(str(f), 2, count=2)
    assert result == "line two\nline three"


def test_read_source_lines_missing_file():
    assert read_source_lines("/nonexistent/path.py", 1) == ""


def test_read_source_line_valid(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text("line one\nline two\nline three")
    assert read_source_line(str(f), 2) == "line two"


def test_read_source_line_out_of_bounds(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text("only one line")
    assert read_source_line(str(f), 99) == ""


def test_read_source_line_missing_file():
    assert read_source_line("/nonexistent/path.py", 1) == ""


def test_score_logistic_large_base():
    # base > 709/steepness triggers float("inf") branch
    result = score_logistic_variant(1e300, scale_factor=1.0)
    assert result == 0.0


# --- localtypes ---

def test_raw_result_to_dict():
    r = RawResult(tool_name="ruff", command="ruff check .", stdout="out", stderr="err", return_code=1)
    d = r.to_dict()
    assert d["tool_name"] == "ruff"
    assert d["stdout"] == "out"
    assert d["return_code"] == 1


def test_tool_result_to_dict():
    tr = ToolResult(metrics={"lint": 0.9}, details={"f.py": []})
    d = tr.to_dict()
    assert d["metrics"] == {"lint": 0.9}
    assert "raw" in d


def test_tool_result_post_init_coerces_non_dict():
    tr = ToolResult.__new__(ToolResult)
    tr.metrics = "bad"
    tr.details = None
    tr.raw = RawResult()
    tr.__post_init__()
    assert tr.details == {}
    assert tr.metrics == {}


def test_combined_to_dict():
    tr = ToolResult(metrics={"lint": 0.8})
    c = CombinedToolResults(path="src/", tool_results=[tr])
    d = c.to_dict()
    assert d["path"] == "src/"
    assert "score" in d
    assert len(d["metrics"]) == 1


# --- RuffParser ---

RUFF_OUTPUT = """\
src/foo.py:10:1: E501 line too long (100 > 79 characters)
src/foo.py:20:5: F841 local variable 'x' is assigned but never used
src/bar.py:5:1: F401 `os` imported but unused
Found 3 errors.
"""


def test_ruff_parse_violations():
    tr = RuffParser().parse(raw(RUFF_OUTPUT, return_code=1))
    assert "lint" in tr.metrics
    assert tr.metrics["lint"] < 1.0
    assert "src/foo.py" in tr.details
    assert len(tr.details["src/foo.py"]) == 2
    assert tr.details["src/foo.py"][0]["code"] == "E501"


def test_ruff_parse_clean():
    tr = RuffParser().parse(raw("All checks passed!\n", return_code=0))
    assert tr.metrics["lint"] == 1.0
    assert tr.details == {}


def test_ruff_provide_help():
    tr = ToolResult(raw=RawResult(stdout="ruff output here"))
    assert RuffParser().provide_help(tr) == "ruff output here"


# --- TyParser ---

TY_OUTPUT = """\
src/baz.py:7:5: error[invalid-return-type] return type mismatch
src/baz.py:15:1: warning[unused-import] `os` imported but unused
Found 2 diagnostics.
"""


def test_ty_parse_diagnostics():
    tr = TyParser().parse(raw(TY_OUTPUT, return_code=1))
    assert "type_check" in tr.metrics
    assert tr.metrics["type_check"] < 1.0
    assert "src/baz.py" in tr.details
    issues = tr.details["src/baz.py"]
    assert issues[0]["severity"] == "error"
    assert issues[1]["severity"] == "warning"


def test_ty_parse_clean():
    tr = TyParser().parse(raw("All checks passed!\n", return_code=0))
    assert tr.metrics["type_check"] == 1.0
    assert tr.details == {}


def test_ty_provide_help():
    tr = ToolResult(raw=RawResult(stdout="ty output"))
    assert TyParser().provide_help(tr) == "ty output"


# --- PytestParser ---

PYTEST_OUTPUT = """\
tests/test_foo.py::test_one PASSED    [ 50%]
tests/test_foo.py::test_two FAILED    [100%]
"""

PYTEST_NO_TESTS = "no tests ran"


def test_pytest_parse_mixed():
    tr = PytestParser().parse(raw(PYTEST_OUTPUT, return_code=1))
    assert tr.metrics["tests"] == 0.5
    assert "tests/test_foo.py" in tr.details
    assert tr.details["tests/test_foo.py"]["test_one"] == "PASSED"
    assert tr.details["tests/test_foo.py"]["test_two"] == "FAILED"


def test_pytest_parse_all_pass():
    output = "tests/test_foo.py::test_one PASSED    [100%]\n"
    tr = PytestParser().parse(raw(output, return_code=0))
    assert tr.metrics["tests"] == 1.0


def test_pytest_parse_no_tests():
    tr = PytestParser().parse(raw(PYTEST_NO_TESTS))
    assert tr.metrics == {}


def test_pytest_parse_empty():
    tr = PytestParser().parse(raw(""))
    assert tr.metrics["tests"] == 0


# --- PydocstyleParser ---

PYDOC_OUTPUT = """\
./src/foo.py:1 at module level:
        D100: Missing docstring in public module
./src/foo.py:10 in public function `bar`:
        D103: Missing docstring in public function
"""


def test_pydocstyle_parse_violations():
    tr = PydocstyleParser().parse(raw(PYDOC_OUTPUT, return_code=1))
    assert "docstyle" in tr.metrics
    assert tr.metrics["docstyle"] < 1.0
    assert "src/foo.py" in tr.details
    assert len(tr.details["src/foo.py"]) == 2
    assert tr.details["src/foo.py"][0]["code"] == "D100"


def test_pydocstyle_parse_clean():
    tr = PydocstyleParser().parse(raw("", return_code=0))
    assert tr.metrics["docstyle"] == 1.0
    assert tr.details == {}


# --- CompileParser ---

COMPILE_OUTPUT_WITH_ERROR = """\
Listing '.\\src'...
Compiling '.\\src\\good.py'...
Compiling '.\\src\\bad.py'...
***   File ".\\src\\bad.py", line 10
    x = {a = b}
         ^^^^^
SyntaxError: invalid syntax. Maybe you meant '==' or ':=' instead of '='?

Compiling '.\\src\\also_good.py'...
"""

COMPILE_OUTPUT_CLEAN = """\
Listing '.\\src'...
Compiling '.\\src\\good.py'...
Compiling '.\\src\\also_good.py'...
"""


def test_compile_parse_with_error():
    tr = CompileParser().parse(raw(COMPILE_OUTPUT_WITH_ERROR, return_code=1))
    assert "compile" in tr.metrics
    assert tr.metrics["compile"] < 1.0
    assert "failed_files" in tr.details
    assert "./src/bad.py" in tr.details["failed_files"]
    info = tr.details["failed_files"]["./src/bad.py"]
    assert info["line"] == 10
    assert "SyntaxError" in info["type"]


def test_compile_parse_clean():
    tr = CompileParser().parse(raw(COMPILE_OUTPUT_CLEAN, return_code=0))
    assert tr.metrics["compile"] == 1.0
    assert "failed_files" not in tr.details


def test_compile_parse_empty():
    tr = CompileParser().parse(raw(""))
    assert tr.metrics["compile"] == 1.0


def test_compile_provide_help():
    tr = ToolResult(details={"failed_files": {"src/bad.py": {"line": 5}}})
    help_text = CompileParser().provide_help(tr)
    assert "src/bad.py" in help_text


# compile error block with < 4 lines hits the "Unknown" type fallback (compileparser.py:107-108)
COMPILE_SHORT_ERROR = """\
Compiling '.\\src\\bad.py'...
***   File ".\\src\\bad.py", line 5
    bad_code
    ^^^^^^^^

"""


def test_compile_parse_short_error_block():
    tr = CompileParser().parse(raw(COMPILE_SHORT_ERROR, return_code=1))
    assert "failed_files" in tr.details
    info = next(iter(tr.details["failed_files"].values()))
    assert info["type"] == "Unknown"


# --- CoverageParser ---

COVERAGE_OUTPUT = """\
Name               Stmts   Miss  Cover
--------------------------------------
src/foo.py            20      2    90%
src/bar.py            10      0   100%
TOTAL                 30      2    93%
"""


def test_coverage_parse():
    tr = CoverageParser().parse(raw(COVERAGE_OUTPUT))
    assert abs(tr.metrics["coverage"] - 0.93) < 0.01
    assert "src/foo.py" in tr.details
    assert abs(tr.details["src/foo.py"]["coverage"] - 0.90) < 0.01
    assert tr.details["src/foo.py"]["missing"] == 2


def test_coverage_format_llm_message():
    tr = CoverageParser().parse(raw(COVERAGE_OUTPUT))
    msg = CoverageParser().format_llm_message(tr)
    assert "0.930" in msg
    assert "src/foo.py" in msg
    assert "90%" in msg
    assert "2 uncovered" in msg
    # 100%-covered file should not appear
    assert "src/bar.py" not in msg


def test_coverage_format_llm_message_no_details():
    from cq.localtypes import RawResult
    tr = ToolResult(metrics={"coverage": 0.95}, details={}, raw=RawResult())
    msg = CoverageParser().format_llm_message(tr)
    assert "0.950" in msg


def test_coverage_parse_empty():
    tr = CoverageParser().parse(raw(""))
    assert tr.metrics == {}


def test_coverage_parse_malformed_miss_count():
    # Non-integer Miss column falls through to missing=None
    output = "src/foo.py  10  bad  90%\nTOTAL  10  bad  90%\n"
    tr = CoverageParser().parse(raw(output))
    assert tr.details["src/foo.py"]["missing"] is None
    assert abs(tr.details["src/foo.py"]["coverage"] - 0.90) < 0.01


def test_coverage_parse_malformed_percentage():
    # Line with invalid percentage is skipped (ValueError branch)
    output = "src/foo.py  10  5  bad%\nTOTAL  10  5  90%\n"
    tr = CoverageParser().parse(raw(output))
    assert abs(tr.metrics["coverage"] - 0.90) < 0.01
    assert "src/foo.py" not in tr.details


# --- AbstractParser base class defaults ---

def test_abstract_provide_help_default():
    tr = ToolResult(raw=RawResult(stdout="some output"))
    assert MinimalParser().provide_help(tr) == ""


def test_abstract_format_llm_message_no_metrics():
    tr = ToolResult(metrics={})
    assert MinimalParser().format_llm_message(tr) == "No details available"


def test_abstract_parse_body_via_super():
    # Calls the abstract method body (pass) via super() to cover localtypes.py:129
    class SuperCaller(AbstractParser):
        def parse(self, raw_result):
            return super().parse(raw_result)
    result = SuperCaller().parse(RawResult())
    assert result is None


# --- Parser format_llm_message no-details fallbacks ---

def test_ruff_format_llm_no_details():
    tr = ToolResult(metrics={"lint": 0.5}, details={}, raw=RawResult())
    assert "no details" in RuffParser().format_llm_message(tr).lower()


def test_ty_format_llm_no_details():
    tr = ToolResult(metrics={"type_check": 0.5}, details={}, raw=RawResult())
    assert "no details" in TyParser().format_llm_message(tr).lower()


def test_pydocstyle_format_llm_no_details():
    tr = ToolResult(metrics={"docstyle": 0.5}, details={}, raw=RawResult())
    assert "no details" in PydocstyleParser().format_llm_message(tr).lower()


# --- Pydocstyle parse with unmatched lines (hits i += 1 branch) ---

PYDOC_WITH_NOISE = """\
some irrelevant header line
./src/foo.py:1 at module level:
        D100: Missing docstring in public module
another noise line
"""


def test_pydocstyle_parse_with_noise():
    tr = PydocstyleParser().parse(raw(PYDOC_WITH_NOISE))
    assert "src/foo.py" in tr.details
    assert len(tr.details["src/foo.py"]) == 1


# --- llm_formatter without explicit cq_invocation ---

def test_format_for_llm_default_invocation():
    config = ToolConfig(name="ruff", command="", parser_class=RuffParser, priority=3)
    registry = {"ruff": config}
    tr = ToolResult(
        metrics={"lint": 0.5},
        details={"src/foo.py": [{"line": 1, "code": "E501", "message": "too long"}]},
        raw=RawResult(tool_name="ruff", command="python -m ruff check src/"),
    )
    combined = CombinedToolResults(path=".", tool_results=[tr])
    result = format_for_llm(registry, combined)  # no cq_invocation → uses sys.argv
    assert "cq" in result
