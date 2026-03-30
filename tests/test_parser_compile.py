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
    tr = CompileParser().parse(raw(COMPILE_SHORT_ERROR, return_code=1))
    assert "failed_files" in tr.details
    info = next(iter(tr.details["failed_files"].values()))
    assert info["type"] == "Unknown"
