"""Utilities for computing cryptographic signatures and context hashes.

This module offers two lightweight helpers that simplify integrity checks and
change-detection in larger systems:

* **`get_sigs(path)`** - Recursively scans a directory tree and returns a list of
  signature strings for all Python files, ignoring virtual-environment and
  cache directories. Each signature encodes the file path, its size in bytes,
  and its last-modified timestamp (`st_mtime`).

* **`get_context_hash(path)`** - Computes an MD5 digest that uniquely identifies
  a file or directory. For a file it hashes its path, size, and modification
  time; for a directory it aggregates the signatures of all contained files.

When called with ``normalize=True`` the hash is derived from the AST of each
``.py`` file with docstrings stripped, so changes that cannot affect runtime
behaviour (docstrings, comments, formatting, mtime-only touches such as a
``git checkout``) leave the hash unchanged. This is used as the cache key for
tools whose results only depend on executable code (pytest, coverage).

These functions provide deterministic fingerprints that can be used for
file integrity verification, caching, and change-detection logic.
"""

import ast
import hashlib
import os
from pathlib import Path

_ENV_FILES = {".python-version", "pyproject.toml", "uv.lock"}
_SKIP_DIRS = {".venv", "venv", "__pycache__", ".git"}

# Memo: (path, size, mtime) -> normalized signature. Avoids re-parsing files
# whose stat is unchanged. Correctness never depends on this cache: a stale
# mtime only forces a re-parse that reproduces the same signature.
_norm_sig_cache: dict[tuple[str, int, float], str] = {}


def _strip_docstrings(tree: ast.AST) -> None:
    """Remove module/class/function docstrings in place so they don't affect the hash."""
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                node.body = body[1:]


def _normalized_sig(path: str, size: int, mtime: float) -> str:
    """Return a docstring/comment/format-invariant signature for a ``.py`` file.

    Falls back to a byte digest when the file can't be parsed (e.g. a mid-edit
    syntax error), so callers always get a usable signature.
    """
    key = (path, size, mtime)
    cached = _norm_sig_cache.get(key)
    if cached is not None:
        return cached
    raw = Path(path).read_bytes()
    try:
        tree = ast.parse(raw.decode("utf-8", "replace"))
        _strip_docstrings(tree)
        digest = hashlib.md5(ast.dump(tree).encode()).hexdigest()  # nosec
    except (SyntaxError, ValueError):
        digest = hashlib.md5(raw).hexdigest()  # nosec
    sig = f"{path}:{digest}"
    _norm_sig_cache[key] = sig
    return sig


def _byte_sig(path: str) -> str:
    """Return a path + content digest, independent of mtime."""
    return f"{path}:{hashlib.md5(Path(path).read_bytes()).hexdigest()}"  # nosec


def get_sigs(path: str, *, normalize: bool = False):
    """Recursively scans a directory tree and returns a list of signatures for all Python files.

    The signature format is ``<file_path>:<size_bytes>:<mtime>`` where ``mtime`` is the
    last modification timestamp retrieved from ``os.stat``. The traversal skips
    directories named ``.venv``, ``venv`` and ``__pycache__``.

    When ``normalize`` is ``True``, ``.py`` files are fingerprinted by their
    docstring-stripped AST and env files by their byte content, so the result is
    invariant to docstrings, comments, formatting, and mtime-only changes.

    Args:
        path (str): The root directory to scan.
        normalize (bool): Use AST/content fingerprints instead of size+mtime.

    Returns:
        list[str]: A signature string for each ``.py`` file found.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        PermissionError: If the process cannot access a directory or file.

    Example:
        >>> get_sigs('/tmp/project')
        ['/tmp/project/main.py:1024:1680000000.0', ...]
    """
    items = []
    with os.scandir(path) as entries:
        for entry in entries:
            # Use follow_symlinks=False to prevent cache poisoning from
            # symlinks pointing outside the project tree (M-2)
            if entry.is_file(follow_symlinks=False) and (
                entry.name.endswith(".py") or entry.name in _ENV_FILES
            ):
                if normalize:
                    if entry.name.endswith(".py"):
                        stat_info = entry.stat(follow_symlinks=False)
                        items.append(
                            _normalized_sig(
                                entry.path, stat_info.st_size, stat_info.st_mtime
                            )
                        )
                    else:
                        items.append(_byte_sig(entry.path))
                else:
                    stat_info = entry.stat(follow_symlinks=False)
                    items.append(
                        f"{entry.path}:{stat_info.st_size}:{stat_info.st_mtime}"
                    )
            if entry.is_dir(follow_symlinks=False) and entry.name not in _SKIP_DIRS:
                items.extend(get_sigs(entry.path, normalize=normalize))
    return items


def get_context_hash(path: str, *, normalize: bool = False) -> str:
    """Compute an MD5 hash that uniquely identifies a file or directory.

    The hash is derived from a signature string. For a file, the signature consists of
    its path, size, and modification time. For a directory, the signature is the
    concatenation of the signatures of all files within it (recursively).

    When ``normalize`` is ``True`` the signatures are derived from each ``.py``
    file's docstring-stripped AST, making the hash invariant to docstrings,
    comments, formatting, and mtime-only changes.

    Args:
        path (str): The filesystem path to hash.
        normalize (bool): Use AST/content fingerprints instead of size+mtime.

    Returns:
        str: The hexadecimal MD5 digest.

    Raises:
        OSError: If the file or directory cannot be accessed.

    Example:
        >>> get_context_hash('/tmp/example.txt')
        '5d41402abc4b2a76b9719d911017c592'
    """
    h = hashlib.md5()  # nosec
    if os.path.isfile(path):
        if normalize and path.endswith(".py"):
            s = os.stat(path)
            h.update(_normalized_sig(path, s.st_size, s.st_mtime).encode())
        else:
            s = os.stat(path)
            h.update(f"{path}:{s.st_size}:{s.st_mtime}".encode())
    elif os.path.isdir(path):
        for sig in sorted(get_sigs(path, normalize=normalize)):
            h.update(sig.encode())
    else:
        h.update(b"empty")
    return h.hexdigest()
