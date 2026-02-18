"""Loads tool configurations from a YAML file and builds a registry that maps tool names to their configuration objects, enabling efficient lookup and instantiation of tools throughout the application. The module relies on PyYAML for parsing the configuration file."""

from importlib import import_module
from pathlib import Path
import yaml
from cq.localtypes import ToolConfig


def load_tool_configs():
    """Load tool configurations from YAML and return a registry.

    This function reads the YAML file located at
    ``<project_root>/config/tools.yaml``, parses each tool entry, dynamically
    imports the corresponding parser module from the ``cq.parsers`` package,
    and creates a ``ToolConfig`` instance for each tool. The result is a
    dictionary mapping tool identifiers to ``ToolConfig`` objects.

    Returns:
        dict[str, ToolConfig]: A mapping from tool ID to its configuration instance.

    Raises:
        FileNotFoundError: If the tools.yaml configuration file does not exist.
        yaml.YAMLError: If the YAML file cannot be parsed.
        ModuleNotFoundError: If the specified parser module cannot be imported.
        AttributeError: If the specified parser class is missing in the module."""
    config_path = Path(__file__).parent.parent.parent / "config" / "tools.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    registry = {}
    for tool_id, tool_data in config["tools"].items():
        # Dynamically import parser class
        module = import_module(f"cq.parsers.{tool_data['parser'].lower()}")
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
