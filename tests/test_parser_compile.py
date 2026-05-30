"""Tests for CompileParser."""

from conftest import raw

from py_cq.parsers.compileparser import CompileParser

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

# error block with < 4 lines hits the "Unknown" type fallback
COMPILE_SHORT_ERROR = """\
Compiling '.\\src\\bad.py'...
***   File ".\\src\\bad.py", line 5
    bad_code
    ^^^^^^^^

"""


def test_compile_parse_with_error():
    """Test parsing of compile output containing errors."""
    tr = CompileParser().parse(raw(COMPILE_OUTPUT_WITH_ERROR, return_code=1))
    assert "compile" in tr.metrics
    assert tr.metrics["compile"] < 1.0
    assert "failed_files" in tr.details
    assert "./src/bad.py" in tr.details["failed_files"]
    info = tr.details["failed_files"]["./src/bad.py"]
    assert info["line"] == 10
    assert "SyntaxError" in info["type"]


def test_compile_parse_clean():
    """Test that a clean compile output is parsed correctly."""
    tr = CompileParser().parse(raw(COMPILE_OUTPUT_CLEAN, return_code=0))
    assert tr.metrics["compile"] == 1.0
    assert "failed_files" not in tr.details


def test_compile_parse_empty():
    """Test compilation and parsing of an empty input."""
    tr = CompileParser().parse(raw(""))
    assert tr.metrics["compile"] == 1.0


def test_compile_format_llm_message_includes_callee(tmp_path):
    """When the error src line calls a project function, its definition is appended."""
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    bad_file = tmp_path / "bad.py"
    bad_file.write_text("def make_thing(a, b):\n    return a + b\n\nresult = make_thing(oink=2)\n")
    compile_output = (
        f"Compiling '{bad_file}'...\n"
        f'***   File "{bad_file}", line 4\n'
        "    result = make_thing(oink=2)\n"
        "             ^^^^^^^^^^^^^^^^^\n"
        "\n"
        "SyntaxError: invalid syntax\n"
        "\n"
    )
    tr = CompileParser().parse(raw(compile_output, return_code=1))
    msg = CompileParser().format_llm_message(tr)
    assert "def make_thing" in msg


def test_compile_parse_short_error_block():
    """Test that short error blocks are correctly parsed."""
    tr = CompileParser().parse(raw(COMPILE_SHORT_ERROR, return_code=1))
    assert "failed_files" in tr.details
    info = next(iter(tr.details["failed_files"].values()))
    assert info["type"] == "Unknown"


COMPILE_TWO_ERRORS_SAME_FILE = """\
Compiling '.\\src\\a.py'...
Compiling '.\\src\\b.py'...
***   File ".\\src\\a.py", line 5
    x = bad {
    ^^^^^^^^
SyntaxError: invalid syntax

***   File ".\\src\\b.py", line 10
    y = also_bad {
    ^^^^^^^^^^^
SyntaxError: invalid syntax

"""


def test_compile_parse_two_errors_different_files():
    """Two errors in different files are both captured in details."""
    tr = CompileParser().parse(raw(COMPILE_TWO_ERRORS_SAME_FILE, return_code=1))
    assert "failed_files" in tr.details
    assert "./src/a.py" in tr.details["failed_files"]
    assert "./src/b.py" in tr.details["failed_files"]
    assert tr.metrics["compile"] < 1.0


def test_compile_format_llm_message_short_error_fallback():
    """format_llm_message with Unknown type still produces a non-empty message."""
    tr = CompileParser().parse(raw(COMPILE_SHORT_ERROR, return_code=1))
    msg = CompileParser().format_llm_message(tr)
    assert "Unknown" in msg or "src/bad.py" in msg


# Error header without ", line N" — branch 82->87 (line_in_header False)
COMPILE_NO_LINE_NUMBER = """\
Compiling '.\\src\\bad.py'...
***   File ".\\src\\bad.py"
    bad_code
    ^^^^^^^^
SyntaxError: invalid syntax

"""


def test_compile_no_line_number_in_header():
    tr = CompileParser().parse(raw(COMPILE_NO_LINE_NUMBER, return_code=1))
    assert "failed_files" in tr.details
    info = next(iter(tr.details["failed_files"].values()))
    assert "line" not in info


# Error block with exactly 1 line — branch 87->89 (len > 1 False)
COMPILE_ONE_LINE_ERROR = """\
Compiling '.\\src\\bad.py'...
***   File ".\\src\\bad.py", line 5

"""


def test_compile_one_line_error_block():
    tr = CompileParser().parse(raw(COMPILE_ONE_LINE_ERROR, return_code=1))
    assert "failed_files" in tr.details
    info = next(iter(tr.details["failed_files"].values()))
    assert "src" not in info
    assert info["type"] == "Unknown"


# 4-line error block where line[3] has no "Error:" — branch 90->101
COMPILE_FOUR_LINES_NO_ERROR_KEYWORD = """\
Compiling '.\\src\\bad.py'...
***   File ".\\src\\bad.py", line 5
    bad_code
    ^^^^^^^^
    ^ (hint: check syntax here)

"""


def test_compile_four_lines_no_error_keyword():
    tr = CompileParser().parse(raw(COMPILE_FOUR_LINES_NO_ERROR_KEYWORD, return_code=1))
    assert "failed_files" in tr.details
    info = next(iter(tr.details["failed_files"].values()))
    assert "type" not in info


def test_compile_format_llm_message_no_src():
    """format_llm_message with no 'src' key in info — branch 130->135 (src_line falsy)."""
    tr = CompileParser().parse(raw(COMPILE_ONE_LINE_ERROR, return_code=1))
    msg = CompileParser().format_llm_message(tr)
    assert msg  # non-empty, no crash


# *** File line with no quotes — len(parts) < 2 → continue (line 69)
COMPILE_FILE_LINE_NO_QUOTES = """\
Compiling '.\\src\\bad.py'...
***   File no-quotes-here
    bad_code

"""


def test_compile_file_line_without_quotes_is_skipped():
    """A '*** File' header without quotes is skipped without crashing."""
    tr = CompileParser().parse(raw(COMPILE_FILE_LINE_NO_QUOTES, return_code=1))
    # No valid error block extracted — details should be empty or have no failed_files
    assert "failed_files" not in tr.details or tr.details["failed_files"] == {}


# *** File line with non-integer line number — ValueError branch (lines 90-91)
COMPILE_BAD_LINE_NUMBER = """\
Compiling '.\\src\\bad.py'...
***   File ".\\src\\bad.py", line NaN
    bad_code
    ^^^^^^^^
SyntaxError: invalid syntax

"""


def test_compile_non_integer_line_number_does_not_crash():
    """Non-integer line number in error header is silently ignored."""
    tr = CompileParser().parse(raw(COMPILE_BAD_LINE_NUMBER, return_code=1))
    assert "failed_files" in tr.details
    info = next(iter(tr.details["failed_files"].values()))
    assert "line" not in info  # line key absent because int() raised ValueError
