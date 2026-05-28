"""Loads tool configurations from a TOML file and builds a registry that maps tool names to their configuration objects, enabling efficient lookup and instantiation of tools throughout the application."""

import tomllib
from importlib import import_module
from importlib.resources import files

from py_cq.localtypes import ToolConfig


def load_tool_configs() -> dict[str, ToolConfig]:
    """Load tool configurations from the bundled config.toml and return a registry.

    Returns:
        dict[str, ToolConfig]: A mapping from tool ID to its configuration instance."""
    toml_bytes = files("py_cq.config").joinpath("config.toml").read_bytes()
    config = tomllib.loads(toml_bytes.decode())
    registry = {}
    for tool_id, tool_data in config["python"].items():
        # Dynamically import parser class
        module = import_module(f"py_cq.parsers.{tool_data['parser'].lower()}")
        parser_class = getattr(module, tool_data["parser"])
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
    return registry


tool_registry = load_tool_configs()
