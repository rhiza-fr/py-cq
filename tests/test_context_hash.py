"""Tests for context_hash."""

import hashlib
import os

from py_cq.context_hash import get_context_hash, get_sigs


def test_get_context_hash_file_returns_md5(tmp_path):
    """Test that get_context_hash returns an MD5 hash of the file content."""
    f = tmp_path / "foo.py"
    f.write_text("x = 1")
    h = get_context_hash(str(f))
    assert isinstance(h, str) and len(h) == 32


def test_get_context_hash_file_changes_with_mtime(tmp_path):
    """Test that changing the mtime of a file results in a different context hash."""
    f = tmp_path / "foo.py"
    f.write_text("x = 1")
    h1 = get_context_hash(str(f))
    st = f.stat()
    os.utime(f, (st.st_mtime + 10, st.st_mtime + 10))
    h2 = get_context_hash(str(f))
    assert h1 != h2


def test_get_context_hash_directory(tmp_path):
    """Test get_context_hash with a directory."""
    (tmp_path / "a.py").write_text("a = 1")
    h = get_context_hash(str(tmp_path))
    assert isinstance(h, str) and len(h) == 32


def test_get_context_hash_nonexistent_returns_empty_hash(tmp_path):
    """Test that get_context_hash returns an empty hash for a nonexistent path."""
    h = get_context_hash(str(tmp_path / "nonexistent"))
    expected = hashlib.md5("empty".encode()).hexdigest()
    assert h == expected


def test_get_sigs_py_files_only(tmp_path):
    (tmp_path / "foo.py").write_text("")
    (tmp_path / "readme.md").write_text("")
    sigs = get_sigs(str(tmp_path))
    assert len(sigs) == 1
    assert "foo.py" in sigs[0]


def test_get_sigs_skips_venv(tmp_path):
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "lib.py").write_text("")
    (tmp_path / "app.py").write_text("")
    sigs = get_sigs(str(tmp_path))
    assert len(sigs) == 1
    assert all(".venv" not in s for s in sigs)


def test_get_sigs_skips_pycache(tmp_path):
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "mod.py").write_text("")
    (tmp_path / "mod.py").write_text("")
    sigs = get_sigs(str(tmp_path))
    assert len(sigs) == 1


def test_get_sigs_recursive(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "bar.py").write_text("")
    (tmp_path / "foo.py").write_text("")
    sigs = get_sigs(str(tmp_path))
    assert len(sigs) == 2


def test_get_sigs_sig_format(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text("hello")
    sigs = get_sigs(str(tmp_path))
    assert len(sigs) == 1
    parts = sigs[0].split(":")
    assert parts[-2].isdigit()   # size
    assert "." in parts[-1]      # mtime float
