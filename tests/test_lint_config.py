"""Verify ruff and mypy configs in pyproject.toml are valid and functional."""

import subprocess

import pytest
import tomli


PROJECT_ROOT = subprocess.run(
    ["git", "rev-parse", "--show-toplevel"],
    capture_output=True,
    text=True,
    check=True,
).stdout.strip()

PYPROJECT = PROJECT_ROOT + "/pyproject.toml"


@pytest.fixture()
def fixture_file(tmp_path):
    """Write a Python file with intentional violations that ruff and mypy should flag."""
    path = tmp_path / "smoke.py"
    path.write_text(
        '"""Smoke fixture with deliberate violations."""\n'
        "import os\n"  # ARG: unused import
        "\n"
        "def greet(name):\n"  # ARG: unused argument
        '    """Return greeting."""\n'
        '    return "hello, " + name\n'
        "\n"
        "x = greet('world')\n"
    )
    return path


@pytest.fixture()
def pyproject_config():
    """Parse pyproject.toml once per test class."""
    with open(PYPROJECT, "rb") as f:
        return tomli.load(f)


class TestRuffConfig:
    """Ruff reads pyproject.toml without config errors and flags violations."""

    def test_ruff_check_no_config_errors(self, fixture_file):
        """ruff check --config pyproject.toml exits without config-parse errors."""
        result = subprocess.run(
            ["ruff", "check", "--config", PYPROJECT, str(fixture_file)],
            capture_output=True,
            text=True,
        )
        # Exit code 0 = no violations, non-zero = violations found.
        # Either is fine — we just need no config errors.
        # Config errors produce exit code 2 with "Failed to parse" messages.
        assert "Failed to parse" not in result.stderr
        assert "error" not in result.stderr.lower() or "exit" in result.stderr.lower()

    def test_ruff_check_flags_unused_import(self, fixture_file):
        """Configured rule set catches ARG (unused argument) violations."""
        result = subprocess.run(
            ["ruff", "check", "--config", PYPROJECT, str(fixture_file)],
            capture_output=True,
            text=True,
        )
        # Unused import 'os' should be flagged (F401 or ARG001)
        assert result.returncode != 0
        assert "ARG" in result.stdout or "F401" in result.stdout

    def test_ruff_line_length_configured(self, pyproject_config):
        """Line-length is set to 120 in pyproject.toml."""
        assert pyproject_config["tool"]["ruff"]["line-length"] == 120

    def test_ruff_target_version_configured(self, pyproject_config):
        """Target-version is set to py310 in pyproject.toml."""
        assert pyproject_config["tool"]["ruff"]["target-version"] == "py310"


class TestMypyConfig:
    """Mypy reads pyproject.toml config and targets Python 3.10."""

    def test_mypy_config_no_parse_errors(self, fixture_file):
        """mypy --config-file pyproject.toml runs without config errors."""
        result = subprocess.run(
            ["mypy", "--config-file", PYPROJECT, str(fixture_file)],
            capture_output=True,
            text=True,
        )
        # Config errors produce lines containing "Error:" or "error:" in stderr
        assert "Error" not in result.stderr

    def test_mypy_python_version_configured(self, pyproject_config):
        """python_version is set to 3.10 in pyproject.toml."""
        assert pyproject_config["tool"]["mypy"]["python_version"] == "3.10"

    def test_mypy_warn_return_any(self, pyproject_config):
        """warn_return_any is disabled (permissive defaults)."""
        assert pyproject_config["tool"]["mypy"]["warn_return_any"] is False


class TestDevDeps:
    """Dev dependency group exists with required tools."""

    REQUIRED_PACKAGES = {"ruff", "mypy", "pre-commit"}

    def test_dev_group_exists(self, pyproject_config):
        """[project.optional-dependencies].dev group is defined."""
        assert "dev" in pyproject_config["project"]["optional-dependencies"]

    def test_dev_group_contains_required_tools(self, pyproject_config):
        """Dev group includes ruff, mypy, and pre-commit."""
        dev_deps = pyproject_config["project"]["optional-dependencies"]["dev"]
        dev_dep_names = {d.split(">=")[0].split("==")[0].split("[")[0].strip() for d in dev_deps}
        assert self.REQUIRED_PACKAGES.issubset(dev_dep_names)