"""Utility classes for representing and aggregating results from static-analysis tools.

This module defines dataclasses that capture tool configuration (`ToolConfig`), raw execution output (`RawResult`), parsed metrics (`ToolResult`), and a consolidated view of all tool results (`CombinedToolResults`).  It also provides an abstract `AbstractParser` that concrete parsers should subclass to convert a `RawResult` into a `ToolResult`.  Together these components enable parsing, combining, and serialising analysis metrics for downstream reporting and analysis."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Fingerprint:
    """Stable identity for a single reported issue.

    String form: ``tool::project::path[::line[::code]]``  (trailing empty fields omitted).
    ``project`` is an absolute path; ``path`` is relative to it.
    """

    tool: str
    project: str  # absolute path to project root
    path: str  # path relative to project
    line: str = ""
    code: str = ""

    def __str__(self) -> str:
        parts = [self.tool, self.project, self.path, self.line, self.code]
        while parts and not parts[-1]:
            parts.pop()
        return "::".join(parts)

    @classmethod
    def from_string(cls, s: str) -> "Fingerprint":
        parts = s.split("::")
        parts += [""] * (5 - len(parts))
        return cls(
            tool=parts[0], project=parts[1], path=parts[2], line=parts[3], code=parts[4]
        )


@dataclass
class ToolConfig:
    """Represents the configuration for an analysis tool, including its name, command, parser class, context path, order, and thresholds for warnings and errors."""

    name: str  # e.g., "pytest", "coverage", "pydocstyle"
    command: str  # The command to execute (can include placeholders)
    parser_class: Callable  # The parser class itself (resolved from its name in config)
    context_path: str = ""  # Path to project or file
    order: int = 5  # 1=first (compilation), 11=last (style)
    warning_threshold: float = 0.7  # Yellow warning if below this
    error_threshold: float = 0.5  # Red error if below this
    run_in_target_env: bool = False  # If True, run in target project's env via uv
    extra_deps: list[str] = field(
        default_factory=list
    )  # Extra deps to inject via uv --with
    parser_config: dict[str, Any] = field(default_factory=dict)
    exclude_format: str = (
        ""  # Per-path template for --exclude injection, e.g. " --exclude {path}"
    )
    scan_exclude_names: list[str] = field(
        default_factory=list
    )  # Top-level dir/file names to omit from {scan_targets}
    skip_for_file: bool = False  # If True, skip when context_path is a single file
    gate_strict: bool = True  # If False, small regressions above warning_threshold are accepted
    skip_if: str = ""  # Tool name; if that tool's score is below its error_threshold, skip this tool


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
    project_path: str = ""  # Absolute path to the target project root

    def to_dict(self):
        """Returns a dictionary containing the tool name, command, stdout, stderr, return code, and timestamp."""
        return {
            "tool_name": self.tool_name,
            "command": self.command,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "return_code": self.return_code,
            "timestamp": self.timestamp,
            "project_path": self.project_path,
        }


@dataclass
class ToolResult:
    """Represents a parsed metric from a tool run.

    This dataclass stores information about a metric extracted from a tool
    execution, ensuring that the `details` attribute is always a dictionary.
    It provides a `to_dict` method for convenient serialization of the metric
    data into a plain dictionary."""

    metrics: dict[str, float] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
    raw: RawResult = field(default_factory=RawResult)
    project_path: str = ""
    duration_s: float = 0.0

    def __post_init__(self):
        """Ensures that the `details` and `metrics` attributes are dictionaries, initializing them to empty dictionaries if they are not."""
        if not isinstance(self.details, dict):
            self.details = {}
        if not isinstance(self.metrics, dict):
            self.metrics = {}

    def to_dict(self) -> dict:
        """Returns a dictionary containing the tool name, metrics, details, and duration."""
        return {
            "tool_name": self.raw.tool_name,
            "metrics": self.metrics,
            "details": self.details,
            "project_path": self.project_path,
            "duration_s": self.duration_s,
        }


class CombinedToolResults:
    """Aggregates results from multiple tools, stores the associated path, and calculates an overall score by averaging the mean metric values of each ``ToolResult``. If a ``ToolResult`` has no metrics, it contributes zero, and the score defaults to ``0.0`` when the list is empty."""

    score: float
    path: str

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
        scored = [tr for tr in tool_results if tr.metrics]
        self.score = (
            sum(sum(tr.metrics.values()) / len(tr.metrics) for tr in scored)
            / len(scored)
            if scored
            else 0.0
        )

    def to_dict(self) -> dict:
        """Returns a dictionary containing the path, overall score, and each ToolResult serialized."""
        return {
            "metrics": [tool_result.to_dict() for tool_result in self.tool_results],
            "score": self.score,
            "path": self.path,
        }


class AbstractParser(ABC):
    """Base class for parsers that transform raw tool output into structured `ToolResult` objects.

    Subclasses must implement `parse` to convert a `RawResult` into a `ToolResult`. The `format_llm_message` method can be overridden to supply a richer single-defect description for a parsed result."""

    def __init__(self, parser_config: dict | None = None):
        self.parser_config = parser_config or {}

    @abstractmethod
    def parse(self, raw_result: RawResult) -> ToolResult:
        """Converts raw tool output into a structured ToolResult."""
        pass

    def format_llm_message(
        self, tr: ToolResult, *, context_lines: int = 15, limit: int = 1
    ) -> str:
        """Return a single-defect description for LLM consumption.

        Default implementation reports the worst metric by name and score.
        Parsers with richer details should override this."""
        if tr.metrics:
            metric_name, value = next(iter(tr.metrics.items()))
            return f"**{metric_name}** score: {value:.3f}"
        return "No details available"
