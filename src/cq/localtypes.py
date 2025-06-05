from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolConfig:
    """Configuration for a specific analysis tool."""

    name: str  # e.g., "pytest", "coverage", "pydocstyle"
    command: str  # The command to execute (can include placeholders)
    parser_class: Callable  # Name of the parser class to use
    context_path: str = ""  # Path to project or file


@dataclass
class RawResult:
    """Represents the raw output from a tool execution."""

    tool_name: str = ""
    command: str = ""
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0
    timestamp: str = ""  # For tracking when the analysis ran

    def to_dict(self):
        return {
            "tool_name": self.tool_name,
            "command": self.command,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "return_code": self.return_code,
            "timestamp": self.timestamp,
        }


@dataclass
class ToolResult:
    """Represents a parsed metric from a tool run."""

    metrics: dict[str, float] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)  # Additional details about the metric
    raw: RawResult = field(default_factory=RawResult)

    def __post_init__(self):
        """Ensure details is always a dictionary."""
        if not isinstance(self.details, dict):
            self.details = {}
        if not isinstance(self.metrics, dict):
            self.metrics = {}
        # if not isinstance(self.raw, dict):
        #     self.raw =

    def to_dict(self) -> dict:
        """Convert the Metric to a dictionary for easy serialization."""
        return {"metrics": self.metrics, "details": self.details, "raw": self.raw.to_dict()}


@dataclass
class CombinedToolResults:
    """Represents the aggregated tool results from all tools."""

    def __init__(self, path: str, tool_results: list[ToolResult]):
        self.tool_results = tool_results
        self.path = path
        score = 0.0
        for tr in self.tool_results:
            score += sum(tr.metrics.values()) / len(tr.metrics) if tr.metrics else 0.0
        self.score = score / len(self.tool_results) if tool_results else 0.0

    metrics: list[ToolResult]
    # context_path: str # Path to project or file
    score: float = 0.0
    path: str = ""

    def to_dict(self) -> dict:
        """Convert the CombinedMetric to a dictionary for easy serialization."""
        return {
            "metrics": [tool_result.to_dict() for tool_result in self.tool_results],
            "score": self.score,
            "path": self.path,
            # "timestamp": self.timestamp,
            # "context_path": self.context_path
        }


class AbstractParser(ABC):
    @abstractmethod
    def parse(self, raw_result: RawResult) -> ToolResult:
        pass
