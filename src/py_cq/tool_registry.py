"""Loads tool configurations from a YAML file and builds a registry that maps tool names to their configuration objects, enabling efficient lookup and instantiation of tools throughout the application. The module relies on PyYAML for parsing the configuration file."""

from importlib import import_module
from importlib.resources import files

import yaml

from py_cq.localtypes import ToolConfig


def load_tool_configs() -> dict[str, ToolConfig]:
    """Load tool configurations from the bundled tools.yaml and return a registry.

    Returns:
        dict[str, ToolConfig]: A mapping from tool ID to its configuration instance."""
    yaml_text = files("py_cq.config").joinpath("tools.yaml").read_text(encoding="utf-8")
    config = yaml.safe_load(yaml_text)
    registry = {}
    for tool_id, tool_data in config["tools"].items():
        # Dynamically import parser class
        module = import_module(f"py_cq.parsers.{tool_data['parser'].lower()}")
        parser_class = getattr(module, tool_data["parser"])
        registry[tool_id] = ToolConfig(
            name=tool_data["name"],
            command=tool_data["command"],
            parser_class=parser_class,
            priority=tool_data["priority"],
            warning_threshold=tool_data["warning_threshold"],
            error_threshold=tool_data["error_threshold"],
            run_in_target_env=tool_data.get("run_in_target_env", False),
            extra_deps=tool_data.get("extra_deps", []),
        )
    return registry


tool_registry = load_tool_configs()
