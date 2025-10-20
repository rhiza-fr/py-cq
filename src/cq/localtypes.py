"""Utility classes for representing and aggregating results from static-analysis tools.

This module defines dataclasses that capture tool configuration (`ToolConfig`), raw execution output (`RawResult`), parsed metrics (`ToolResult`), and a consolidated view of all tool results (`CombinedToolResults`).  It also provides an abstract `AbstractParser` that concrete parsers should subclass to convert a `RawResult` into a `ToolResult`.  Together these components enable parsing, combining, and serialising analysis metrics for downstream reporting and analysis."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolConfig:
    """Represents the configuration for an analysis tool, including its name, command, parser class, context path, priority, and thresholds for warnings and errors."""

    name: str  # e.g., "pytest", "coverage", "pydocstyle"
    command: str  # The command to execute (can include placeholders)
    parser_class: Callable  # Name of the parser class to use
    context_path: str = ""  # Path to project or file
    priority: int = 5  # 1=critical (compilation), 5=low (style)
    warning_threshold: float = 0.7  # Yellow warning if below this
    error_threshold: float = 0.5  # Red error if below this


@dataclass
class RawResult:
    """Represents the raw output from a tool execution.

    Instances store the unprocessed data returned by a tool and can be
    converted to a plain dictionary using :meth:`to_dict`."""

    tool_name: str = ""
    command: str = ""
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0
    timestamp: str = ""  # For tracking when the analysis ran

    def to_dict(self):
        """Returns a dictionary containing the tool name, command, stdout, stderr, return code, and timestamp."""
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
    """Represents a parsed metric from a tool run.

    This dataclass stores information about a metric extracted from a tool
    execution, ensuring that the `details` attribute is always a dictionary.
    It provides a `to_dict` method for convenient serialization of the metric
    data into a plain dictionary."""

    metrics: dict[str, float] = field(default_factory=dict)
    details: dict[str, Any] = field(
        default_factory=dict
    )  # Additional details about the metric
    raw: RawResult = field(default_factory=RawResult)

    def __post_init__(self):
        """Ensures that the `details` and `metrics` attributes are dictionaries, initializing them to empty dictionaries if they are not."""
        if not isinstance(self.details, dict):
            self.details = {}
        if not isinstance(self.metrics, dict):
            self.metrics = {}
        # if not isinstance(self.raw, dict):
        #     self.raw =

    def to_dict(self) -> dict:
        """Returns a dictionary containing the metrics, details, and the raw data serialized via its own `to_dict` method."""
        return {
            "metrics": self.metrics,
            "details": self.details,
            "raw": self.raw.to_dict(),
        }


@dataclass
class CombinedToolResults:
    """Aggregates results from multiple tools, stores the associated path, and calculates an overall score by averaging the mean metric values of each ``ToolResult``. If a ``ToolResult`` has no metrics, it contributes zero, and the score defaults to ``0.0`` when the list is empty."""

    def __init__(self, path: str, tool_results: list[ToolResult]):
        """Initializes a CombinedToolResults instance.

        Stores the given path and list of ToolResult objects, and computes an overall
        score by averaging the mean metric values of each ToolResult. ToolResults
        without metrics contribute zero. If the list is empty the score defaults to
        0.0.

        Args:
            path (str): Path associated with the results.
            tool_results (list[ToolResult]): List of ToolResult objects."""
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
        """Returns a dictionary containing the path, overall score, and each ToolResult serialized."""
        # "timestamp": self.timestamp,
        # "context_path": self.context_path
        return {
            "metrics": [tool_result.to_dict() for tool_result in self.tool_results],
            "score": self.score,
            "path": self.path,
        }


class AbstractParser(ABC):
    """Base class for parsers that transform raw tool output into structured `ToolResult` objects.

    Subclasses must implement `parse` to convert a `RawResult` into a `ToolResult`. An optional `provide_help` can be overridden to supply contextual guidance for a parsed result."""

    @abstractmethod
    def parse(self, raw_result: RawResult) -> ToolResult:
        """Converts raw tool output into a structured ToolResult."""
        pass

    def provide_help(self, tr: ToolResult) -> str:
        """Returns contextual help for a ToolResult; intended to be overridden by subclasses."""
        return ""
