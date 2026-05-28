"""Library API for py-cq. Instantiate CQ with a project root, then call methods."""

import copy
from importlib import import_module
from pathlib import Path

from py_cq.config import load_user_config
from py_cq.execution_engine import _cache, run_tools
from py_cq.llm_formatter import format_for_llm_json
from py_cq.localtypes import CombinedToolResults, ToolConfig, ToolResult
from py_cq.metric_aggregator import aggregate_metrics
from py_cq.tool_registry import tool_registry

_KNOWN_PARSER_CLASSES = frozenset({
    "CompileParser", "RuffParser", "TyParser", "BanditParser",
    "PytestParser", "CoverageParser", "ComplexityParser",
    "MaintainabilityParser", "HalsteadParser", "VultureParser",
    "InterrogateParser",
    "ExitCodeParser", "LineCountParser", "RegexCountParser",
})


def _apply_user_config(base: dict[str, ToolConfig], user_cfg: dict) -> dict[str, ToolConfig]:
    """Return a modified copy of base with user overrides applied.

    Raises ValueError on invalid config (caller wraps for CLI context).
    """
    registry = {k: copy.copy(v) for k, v in base.items()}
    for tool_id in user_cfg.get("disable", []):
        registry.pop(tool_id, None)
    for tool_id, thresholds in user_cfg.get("thresholds", {}).items():
        if tool_id in registry:
            if "warning" in thresholds:
                registry[tool_id].warning_threshold = float(thresholds["warning"])
            if "error" in thresholds:
                registry[tool_id].error_threshold = float(thresholds["error"])
    for tool_id, tool_data in user_cfg.get("tools", {}).items():
        if tool_id in base:
            available = ", ".join(sorted(base))
            raise ValueError(
                f"[tool.cq.tools.{tool_id}] is a built-in tool and cannot be redefined via pyproject.toml. "
                f"Use [tool.cq.thresholds.{tool_id}] to adjust thresholds instead. "
                f"Available: {available}"
            )
        try:
            parser_name = tool_data["parser"]
        except KeyError:
            raise ValueError(f"[tool.cq.tools.{tool_id}] missing required field 'parser'")
        if parser_name not in _KNOWN_PARSER_CLASSES:
            allowed = ", ".join(sorted(_KNOWN_PARSER_CLASSES))
            raise ValueError(
                f"[tool.cq.tools.{tool_id}] unknown parser {parser_name!r}. "
                f"Allowed parsers: {allowed}"
            )
        try:
            module = import_module(f"py_cq.parsers.{parser_name.lower()}")
            parser_class = getattr(module, parser_name)
            registry[tool_id] = ToolConfig(
                name=tool_id,
                command=tool_data["command"],
                parser_class=parser_class,
                order=tool_data["order"],
                warning_threshold=tool_data["warning_threshold"],
                error_threshold=tool_data["error_threshold"],
                run_in_target_env=tool_data.get("run_in_target_env", False),
                extra_deps=tool_data.get("extra_deps", []),
                parser_config=tool_data.get("parser_config", {}),
                exclude_format=tool_data.get("exclude_format", ""),
            )
        except (KeyError, ImportError, AttributeError) as e:
            raise ValueError(f"[tool.cq.tools.{tool_id}] {e}")
    return registry


class CQ:
    """Run code quality checks against a project root.

    Config is loaded once at construction from pyproject.toml [tool.cq].
    All methods return data objects; formatting is left to the caller.

    Example::

        cq = CQ(".")
        issue = cq.check_llm_json()   # {"id": ..., "message": ..., "file": ..., "project": ...}
        fixed = cq.verify(issue["id"])
    """

    def __init__(
        self,
        path: str | Path,
        *,
        skip: list[str] | None = None,
        only: list[str] | None = None,
        exclude: list[str] | None = None,
        workers: int = 0,
        clear_cache: bool = False,
    ) -> None:
        self.path = Path(path)
        self._workers = workers

        user_cfg = load_user_config(self.path)
        self._context_lines: int = int(user_cfg.get("context_lines", 15))
        self._registry = _apply_user_config(tool_registry, user_cfg)

        if only:
            keep = set(only)
            unknown = keep - set(self._registry)
            if unknown:
                raise ValueError(f"Unknown tool(s): {', '.join(sorted(unknown))}. Available: {', '.join(sorted(self._registry))}")
            self._registry = {k: v for k, v in self._registry.items() if k in keep}
        if skip:
            drop = set(skip)
            unknown = drop - set(self._registry)
            if unknown:
                raise ValueError(f"Unknown tool(s): {', '.join(sorted(unknown))}. Available: {', '.join(sorted(self._registry))}")
            self._registry = {k: v for k, v in self._registry.items() if k not in drop}

        config_excludes: list[str] = user_cfg.get("exclude", [])
        self._excludes = list(dict.fromkeys(config_excludes + (exclude or [])))
        self._project_root = self.path.resolve() if self.path.is_dir() else self.path.resolve().parent

        if clear_cache:
            _cache.clear()

    def raw(self, *, early_exit: bool = False) -> list[ToolResult]:
        """Run all tools and return parsed results before aggregation."""
        return run_tools(
            self._registry.values(), str(self.path), self._workers,
            early_exit=early_exit, excludes=self._excludes,
        )

    def check(self) -> CombinedToolResults:
        """Run all tools and return aggregated results."""
        return aggregate_metrics(str(self.path), self.raw())

    def check_llm_json(
        self,
        *,
        limit: int = 1,
        silence: list[str] | None = None,
        hint: bool = False,
    ) -> dict:
        """Return the top defect as a dict with keys: id, file, project, message.

        Stops running tools after the first error (early_exit) for speed.
        """
        results = self.raw(early_exit=True)
        combined = aggregate_metrics(str(self.path), results)
        return format_for_llm_json(
            self._registry, combined,
            context_lines=self._context_lines,
            hint=hint, limit=limit, silence=silence or [],
            project_root=self._project_root,
        )

    def verify(self, fingerprint: str) -> bool:
        """Return True if the fingerprinted issue is no longer present.

        Fingerprint format: tool:file[:line:code]  (as returned by check_llm_json["id"])
        """
        parts = fingerprint.rsplit(":", 2)
        if len(parts) < 2:
            raise ValueError(f"Expected tool:file[:line:code], got: {fingerprint!r}")
        tool_parts = parts[0].split(":", 1)
        tool_name = tool_parts[0]
        file_str = tool_parts[1] if len(tool_parts) > 1 else ""
        code = parts[2] if len(parts) == 3 else ""

        if tool_name not in tool_registry:
            raise ValueError(f"Unknown tool: {tool_name!r}")

        if file_str:
            file_path = Path(file_str)
            if not file_path.is_absolute():
                file_path = self._project_root / file_path
            target = str(file_path)
        else:
            target = str(self.path)

        only_registry = {tool_name: tool_registry[tool_name]}
        tool_results = run_tools(only_registry.values(), target, max_workers=1, early_exit=False, excludes=[])

        if not tool_results:
            return False

        tr = tool_results[0]
        tc = tool_registry[tool_name]

        if not code:
            return bool(tr.metrics and min(tr.metrics.values()) >= tc.warning_threshold)

        target_posix = Path(file_str).as_posix()
        for detail_file, issues in tr.details.items():
            detail_posix = Path(detail_file).as_posix()
            match = (
                detail_posix == target_posix
                or detail_posix.endswith(f"/{target_posix}")
                or target_posix.endswith(f"/{detail_posix}")
            )
            if match and isinstance(issues, list) and any(i.get("code") == code for i in issues):
                return False
        return True
