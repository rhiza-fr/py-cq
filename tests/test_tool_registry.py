"""Tests for tool_registry."""

from py_cq.tool_registry import load_tool_configs, tool_registry


def test_registry_loads_python_tools():
    """Tool registry loads tools from the python: block."""
    assert "ruff" in tool_registry
    assert "pytest" in tool_registry
    assert "bandit" in tool_registry


def test_registry_tools_have_required_fields():
    """Test that all tools in the registry have the required fields."""
    for name, tc in tool_registry.items():
        assert tc.command, f"{name} has no command"
        assert tc.parser_class is not None, f"{name} has no parser_class"
        assert isinstance(tc.order, int), f"{name} order must be int"


def test_all_parser_classes_instantiable():
    """Every parser_class can be instantiated with no parser_config argument."""
    for name, tc in tool_registry.items():
        instance = tc.parser_class()
        assert instance is not None, f"{name} parser_class failed to instantiate"


def test_all_extra_deps_are_strings():
    for name, tc in tool_registry.items():
        for dep in tc.extra_deps:
            assert isinstance(dep, str), f"{name} extra_dep {dep!r} is not a string"


def test_load_tool_configs_idempotent():
    """Calling load_tool_configs() twice returns identical registries."""
    r1 = load_tool_configs()
    r2 = load_tool_configs()
    assert set(r1.keys()) == set(r2.keys())
    for key in r1:
        assert r1[key].command == r2[key].command
        assert r1[key].order == r2[key].order
