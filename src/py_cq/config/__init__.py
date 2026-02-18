"""Default storage path and user config loader."""

import tomllib
from pathlib import Path

DEFAULT_STORAGE_FILE = ".cq.json"


def load_user_config(project_path: Path) -> dict:
    """Read [tool.cq] from pyproject.toml at project_path, if present.

    Args:
        project_path: Path to the project directory or a .py file.

    Returns:
        The contents of [tool.cq] as a plain dict, or {} if absent.
    """
    toml_path = (
        project_path.parent / "pyproject.toml"
        if project_path.is_file()
        else project_path / "pyproject.toml"
    )
    if not toml_path.exists():
        return {}
    with toml_path.open("rb") as f:
        data = tomllib.load(f)
    return data.get("tool", {}).get("cq", {})
