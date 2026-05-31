"""Ensure source files contain only ASCII characters."""

from pathlib import Path

import pytest

SOURCE_DIRS = ["src", "tests"]


def collect_python_files() -> list[Path]:
    """src + tests"""
    root = Path(__file__).parent.parent
    files = []
    for d in SOURCE_DIRS:
        files.extend((root / d).rglob("*.py"))
    return files


@pytest.mark.parametrize(
    "path",
    collect_python_files(),
    ids=lambda p: str(p.relative_to(Path(__file__).parent.parent)),
)
def test_no_high_order_characters(path: Path) -> None:
    """Ensure compatible output"""
    text = path.read_bytes()
    for lineno, line in enumerate(text.splitlines(), start=1):
        for col, byte in enumerate(line, start=1):
            if byte > 127:
                char = chr(byte)
                raise AssertionError(
                    f"{path}:{lineno}:{col}: non-ASCII character {char!r} (0x{byte:02X})"
                )
