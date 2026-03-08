"""Detect the primary language of a project from its file markers."""

from pathlib import Path

# Ordered: first match wins. Python is listed first so it takes priority.
_MARKERS: list[tuple[str, list[str]]] = [
    ("python", ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile"]),
    ("typescript", ["tsconfig.json", "package.json"]),
    ("rust", ["Cargo.toml"]),
    ("go", ["go.mod"]),
    ("ruby", ["Gemfile"]),
    ("java", ["pom.xml", "build.gradle"]),
]

_DOTNET_SUFFIXES = {".csproj", ".sln"}


def detect_language(path: Path) -> str | None:
    """Return the detected language for a project path, or None if unrecognised.

    If path is a file, the parent directory is checked.
    Dotnet is checked last as it uses suffix matching rather than fixed filenames."""
    directory = path if path.is_dir() else path.parent
    for language, markers in _MARKERS:
        if any((directory / marker).exists() for marker in markers):
            return language
    if any(f.suffix in _DOTNET_SUFFIXES for f in directory.iterdir() if f.is_file()):
        return "dotnet"
    return None
