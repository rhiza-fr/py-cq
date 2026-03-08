"""Tests for tool_registry."""
from py_cq.tool_registry import tool_registry


def test_registry_loads_python_tools():
    """Tool registry loads tools from the python: block."""
    assert "ruff" in tool_registry
    assert "pytest" in tool_registry
    assert "bandit" in tool_registry


def test_registry_tools_have_required_fields():
    for name, tc in tool_registry.items():
        assert tc.command, f"{name} has no command"
        assert tc.parser_class is not None, f"{name} has no parser_class"
        assert isinstance(tc.order, int), f"{name} order must be int"
