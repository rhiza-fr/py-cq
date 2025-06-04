from cq.localtypes import ToolConfig
from cq.parsers.compile_parser import CompileParser
from cq.parsers.complexity_parser import ComplexityParser
from cq.parsers.coverage_parser import CoverageParser
from cq.parsers.halstead_parser import HalsteadParser
from cq.parsers.maintainability_parser import MaintainabilityParser
from cq.parsers.pydocstyle_parser import PydocstyleParser
from cq.parsers.pytest_parser import PytestParser

# from cq.parsers.profile_parser import ProfileParser


tool_registry = {
    "compilation": ToolConfig(
        name="compile", 
        command=r"python -m compileall -q {context_path} -x '.*venv.*|.*\.tox.*|.*\.git.*'",
        parser_class=CompileParser
    ),
    "pytest": ToolConfig(
        name="pytest", command="pytest -v {context_path}", parser_class=PytestParser
    ),
    "coverage": ToolConfig(
        name="coverage",
        command="coverage run -m pytest {context_path} && coverage report",
        parser_class=CoverageParser,
    ),
    "pydocstyle": ToolConfig(
        name="pydocstyle",
        command="pydocstyle --convention=google {context_path}",
        parser_class=PydocstyleParser,
    ),
    "maintainability": ToolConfig(
        name="radon mi",
        command="radon mi -s --json {context_path}",
        parser_class=MaintainabilityParser,
    ),
    "complexity": ToolConfig(
        name="radon cc", command="radon cc --json {context_path}", parser_class=ComplexityParser
    ),
    "halstead": ToolConfig(
        name="radon hal", command="radon hal -f --json {context_path}", parser_class=HalsteadParser
    ),
    # "profile": ToolConfig(name="cProfile", command="python -m cProfile -o profile.prof {context_path}", parser_class=ProfileParser),
}
