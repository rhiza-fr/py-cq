"""Tests for language_detector."""
from pathlib import Path
from py_cq.language_detector import detect_language


def test_python_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    assert detect_language(tmp_path) == "python"


def test_python_setup_py(tmp_path):
    (tmp_path / "setup.py").write_text("")
    assert detect_language(tmp_path) == "python"


def test_python_requirements(tmp_path):
    (tmp_path / "requirements.txt").write_text("")
    assert detect_language(tmp_path) == "python"


def test_typescript_tsconfig(tmp_path):
    (tmp_path / "tsconfig.json").write_text("{}")
    assert detect_language(tmp_path) == "typescript"


def test_typescript_package_json(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    assert detect_language(tmp_path) == "typescript"


def test_rust_cargo(tmp_path):
    (tmp_path / "Cargo.toml").write_text("")
    assert detect_language(tmp_path) == "rust"


def test_go_mod(tmp_path):
    (tmp_path / "go.mod").write_text("")
    assert detect_language(tmp_path) == "go"


def test_ruby_gemfile(tmp_path):
    (tmp_path / "Gemfile").write_text("")
    assert detect_language(tmp_path) == "ruby"


def test_java_pom(tmp_path):
    (tmp_path / "pom.xml").write_text("")
    assert detect_language(tmp_path) == "java"


def test_java_gradle(tmp_path):
    (tmp_path / "build.gradle").write_text("")
    assert detect_language(tmp_path) == "java"


def test_dotnet_csproj(tmp_path):
    (tmp_path / "app.csproj").write_text("")
    assert detect_language(tmp_path) == "dotnet"


def test_unknown_returns_none(tmp_path):
    assert detect_language(tmp_path) is None


def test_python_wins_over_typescript(tmp_path):
    """Python takes priority when both markers are present."""
    (tmp_path / "pyproject.toml").write_text("")
    (tmp_path / "package.json").write_text("{}")
    assert detect_language(tmp_path) == "python"


def test_file_input_checks_parent(tmp_path):
    """When given a file path, checks the parent directory."""
    (tmp_path / "pyproject.toml").write_text("")
    py_file = tmp_path / "foo.py"
    py_file.write_text("")
    assert detect_language(py_file) == "python"


def test_file_input_no_markers(tmp_path):
    f = tmp_path / "foo.txt"
    f.write_text("")
    assert detect_language(f) is None
