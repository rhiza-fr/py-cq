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
        command=r"python -m compileall -r 10 -j 8 -f {context_path} -x .*venv",
        parser_class=CompileParser,
        priority=1,
        warning_threshold=0.9,
        error_threshold=0.8,
    ),
    "pytest": ToolConfig(
        name="pytest", 
        command="pytest -v {context_path}", 
        parser_class=PytestParser,
        priority=2,
        warning_threshold=0.7,
        error_threshold=0.5,
    ),
    "coverage": ToolConfig(
        name="coverage",
        command="coverage run -m pytest {context_path} && coverage report",
        parser_class=CoverageParser,
        priority=2,
        warning_threshold=0.7,
        error_threshold=0.5,
    ),
    "pydocstyle": ToolConfig(
        name="pydocstyle",
        command="pydocstyle --convention=google {context_path}",
        parser_class=PydocstyleParser,
        priority=5,
        warning_threshold=0.5,
        error_threshold=0.3,
    ),
    "maintainability": ToolConfig(
        name="radon mi",
        command="radon mi -s --json {context_path}",
        parser_class=MaintainabilityParser,
        priority=3,
        warning_threshold=0.6,
        error_threshold=0.4,
    ),
    "complexity": ToolConfig(
        name="radon cc", 
        command="radon cc --json {context_path}", 
        parser_class=ComplexityParser,
        priority=3,
        warning_threshold=0.6,
        error_threshold=0.4,
    ),
    "halstead": ToolConfig(
        name="radon hal", 
        command="radon hal -f --json {context_path}", 
        parser_class=HalsteadParser,
        priority=4,
        warning_threshold=0.5,
        error_threshold=0.3,
    ),
    # "profile": ToolConfig(name="cProfile", command="python -m cProfile -o profile.prof {context_path}", parser_class=ProfileParser),
}
