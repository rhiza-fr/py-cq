import yaml
from pathlib import Path
from importlib import import_module
from cq.localtypes import ToolConfig

def load_tool_configs():
    """Load tool configurations from YAML file and build registry"""
    config_path = Path(__file__).parent.parent / "config" / "tools.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    registry = {}
    for tool_id, tool_data in config["tools"].items():
        # Dynamically import parser class
        module = import_module(f"cq.parsers.{tool_data['parser'].lower()}_parser")
        parser_class = getattr(module, tool_data["parser"])
        
        registry[tool_id] = ToolConfig(
            name=tool_data["name"],
            command=tool_data["command"],
            parser_class=parser_class,
            priority=tool_data["priority"],
            warning_threshold=tool_data["warning_threshold"],
            error_threshold=tool_data["error_threshold"],
        )
    return registry

tool_registry = load_tool_configs()
