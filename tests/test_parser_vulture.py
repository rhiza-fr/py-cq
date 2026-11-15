"""Tests for VultureParser."""

from conftest import raw

from py_cq.localtypes import RawResult, ToolResult
from py_cq.parsers.vultureparser import VultureParser

VULTURE_OUTPUT = """\
src/foo.py:10: unused function 'bar' (80% confidence)
src/foo.py:25: unused variable 'x' (100% confidence)
src/baz.py:5: unused import 'os' (100% confidence)
"""


def test_vulture_parse_violations():
    """Test that the parser correctly identifies violations."""
    tr = VultureParser().parse(raw(VULTURE_OUTPUT, return_code=1))
    assert "dead_code" in tr.metrics
    assert tr.metrics["dead_code"] < 1.0
    assert "src/foo.py" in tr.details
    assert len(tr.details["src/foo.py"]) == 2
    assert tr.details["src/foo.py"][0]["name"] == "bar"
    assert tr.details["src/foo.py"][0]["confidence"] == 80


def test_vulture_drops_mock_and_framework_idioms():
    """Mock setup attributes, patch params and pydantic model_config are not dead code."""
    stdout = (
        "tests/t.py:3: unused attribute 'return_value' (60% confidence)\n"
        "tests/t.py:4: unused attribute 'side_effect' (60% confidence)\n"
        "tests/t.py:5: unused attribute '__enter__' (60% confidence)\n"
        "tests/t.py:6: unused attribute '__exit__' (60% confidence)\n"
        "tests/t.py:7: unused variable 'mock_open' (100% confidence)\n"
        "src/m.py:2: unused variable 'model_config' (60% confidence)\n"
        "src/m.py:9: unused attribute 'body_width' (60% confidence)\n"
    )
    tr = VultureParser().parse(raw(stdout, return_code=1))
    assert tr.details == {
        "src/m.py": [
            {
                "line": 9,
                "type": "unused attribute",
                "name": "body_width",
                "confidence": 60,
            }
        ]
    }


def test_vulture_parse_clean():
    """Test that clean vulture output is parsed correctly."""
    tr = VultureParser().parse(raw("", return_code=0))
    assert tr.metrics["dead_code"] == 1.0
    assert tr.details == {}


def test_vulture_more_violations_lower_score():
    """Test that more violations result in a lower score."""
    one = VultureParser().parse(raw(VULTURE_OUTPUT[: VULTURE_OUTPUT.index("\n") + 1]))
    many = VultureParser().parse(raw(VULTURE_OUTPUT))
    assert many.metrics["dead_code"] < one.metrics["dead_code"]


def test_vulture_format_llm_no_details():
    tr = ToolResult(metrics={"dead_code": 0.5}, details={}, raw=RawResult())
    assert "no details" in VultureParser().format_llm_message(tr).lower()


def test_vulture_format_llm_with_issue():
    """Test formatting of LLM message when there are issues found."""
    tr = ToolResult(
        metrics={"dead_code": 0.5},
        details={
            "src/foo.py": [
                {"line": 10, "type": "unused function", "name": "bar", "confidence": 80}
            ]
        },
        raw=RawResult(),
    )
    msg = VultureParser().format_llm_message(tr)
    assert "src/foo.py:10" in msg
    assert "bar" in msg
    assert "80%" in msg
    assert "ignore_names" not in msg


def test_vulture_format_llm_low_confidence_says_how_to_keep():
    """Below 80% vulture cannot rule out dynamic use, so the message offers an ignore."""
    tr = ToolResult(
        metrics={"dead_code": 0.5},
        details={
            "src/foo.py": [
                {"line": 10, "type": "unused function", "name": "bar", "confidence": 60}
            ]
        },
        raw=RawResult(),
    )
    msg = VultureParser().format_llm_message(tr)
    assert "60%" in msg
    assert '`"bar"` to `ignore_names` under `[tool.vulture]`' in msg


def test_vulture_parse_ignores_non_matching_lines():
    """Lines that don't match _LINE_RE are silently skipped - branch 27->25."""
    output = (
        "Note: 3 items unused (run with --min-confidence 0 to see all)\n"
        "src/foo.py:10: unused function 'bar' (80% confidence)\n"
        "\n"
        "-- summary --\n"
    )
    tr = VultureParser().parse(raw(output, return_code=1))
    assert tr.details == {
        "src/foo.py": [
            {"line": 10, "type": "unused function", "name": "bar", "confidence": 80}
        ]
    }


MODELS_SRC = """\
from pydantic import BaseModel


class Reply(BaseModel):
    how_hot: str = "warm"
    unannotated = 1


def f():
    local: int = 2
    return 0


module_level: int = 3
"""


def test_vulture_skips_typed_class_fields(tmp_path):
    """Typed fields in a class body (pydantic, dataclass, TypedDict) are not dead code."""
    (tmp_path / "m.py").write_text(MODELS_SRC)
    out = "\n".join(
        f"m.py:{line}: unused variable '{name}' (60% confidence)"
        for line, name in [
            (5, "how_hot"),
            (6, "unannotated"),
            (10, "local"),
            (14, "module_level"),
        ]
    )
    tr = VultureParser().parse(
        RawResult(stdout=out, return_code=0, project_path=tmp_path.as_posix())
    )
    names = [i["name"] for i in tr.details["m.py"]]
    assert names == ["unannotated", "local", "module_level"]


ENUM_EXIT_SRC = """\
import enum
from enum import StrEnum


class Kind(StrEnum):
    FIX = "FIX"


class Color(enum.Enum):
    RED = 1


class Plain:
    UNUSED = 1


class Ctx:
    def __exit__(self, exc_type, exc_val, exc_tb):
        return None
"""


def test_vulture_skips_enum_members_and_exit_params(tmp_path):
    """Enum members and __exit__ parameters are used without being named."""
    (tmp_path / "m.py").write_text(ENUM_EXIT_SRC)
    out = "\n".join(
        f"m.py:{line}: unused variable '{name}' ({conf}% confidence)"
        for line, name, conf in [
            (6, "FIX", 60),
            (10, "RED", 60),
            (14, "UNUSED", 60),
            (18, "exc_tb", 100),
        ]
    )
    tr = VultureParser().parse(
        RawResult(stdout=out, return_code=0, project_path=tmp_path.as_posix())
    )
    assert [i["name"] for i in tr.details["m.py"]] == ["UNUSED"]
