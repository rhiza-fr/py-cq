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

These functions provide deterministic fingerprints that can be used for
file integrity verification, caching, and change-detection logic.
"""

import hashlib
import os


def get_sigs(path: str):
    """Recursively scans a directory tree and returns a list of signatures for all Python files.

    The signature format is ``<file_path>:<size_bytes>:<mtime>`` where ``mtime`` is the
    last modification timestamp retrieved from ``os.stat``. The traversal skips
    directories named ``.venv``, ``venv`` and ``__pycache__``.

    Args:
        path (str): The root directory to scan.

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
            if entry.is_file(follow_symlinks=False) and entry.name.endswith(".py"):
                stat_info = entry.stat(follow_symlinks=False)
                items.append(f"{entry.path}:{stat_info.st_size}:{stat_info.st_mtime}")
            if entry.is_dir(follow_symlinks=False) and entry.name not in [".venv", "venv", "__pycache__", ".git"]:
                items.extend(get_sigs(entry.path))
    return items


def get_context_hash(path: str) -> str:
    """Compute an MD5 hash that uniquely identifies a file or directory.

    The hash is derived from a signature string. For a file, the signature consists of
    its path, size, and modification time. For a directory, the signature is the
    concatenation of the signatures of all files within it (recursively).

    Args:
        path (str): The filesystem path to hash.

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
        s = os.stat(path)
        h.update(f"{path}:{s.st_size}:{s.st_mtime}".encode())
    elif os.path.isdir(path):
        for sig in sorted(get_sigs(path)):
            h.update(sig.encode())
    else:
        h.update(b"empty")
    return h.hexdigest()
