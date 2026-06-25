"""Verify ruff and mypy configs in pyproject.toml are valid and functional."""

import subprocess

import pytest
import tomli
import yaml

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


class TestMypyClean:
    """Mypy type-checks the entire codebase with zero errors."""

    def test_mypy_check_no_errors(self):
        """mypy . exits 0 (no type errors in the codebase)."""
        result = subprocess.run(
            ["mypy", "."],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        assert result.returncode == 0, f"Mypy errors found:\n{result.stdout}"


class TestFormattingBaseline:
    """Codebase is formatted and lint-clean after initial ruff pass."""

    def test_ruff_format_check_passes(self):
        """All .py files pass ruff format --check (no reformats needed)."""
        result = subprocess.run(
            ["ruff", "format", "--check", "."],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        assert result.returncode == 0, f"Unformatted files:\n{result.stdout}"

    def test_ruff_check_no_errors(self):
        """ruff check . exits 0 (no violations)."""
        result = subprocess.run(
            ["ruff", "check", "."],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        assert result.returncode == 0, f"Ruff violations found:\n{result.stdout}"


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


class TestPreCommitConfig:
    """Pre-commit config exists, is valid YAML, and has all required hooks."""

    EXPECTED_HOOK_IDS = {
        "ruff-format",
        "ruff-check",
        "mypy",
        "trailing-whitespace",
        "end-of-file-fixer",
    }

    @pytest.fixture()
    def pre_commit_config(self):
        """Parse .pre-commit-config.yaml."""
        config_path = PROJECT_ROOT + "/.pre-commit-config.yaml"
        with open(config_path) as f:
            return yaml.safe_load(f)

    def test_pre_commit_config_exists_and_parses(self, pre_commit_config):
        """.pre-commit-config.yaml exists and parses as valid YAML."""
        assert pre_commit_config is not None

    def test_pre_commit_config_has_five_hooks(self, pre_commit_config):
        """Config contains exactly the five expected hooks."""
        hook_ids = {hook["id"] for repo in pre_commit_config["repos"] for hook in repo["hooks"]}
        assert self.EXPECTED_HOOK_IDS == hook_ids

    def test_ruff_hooks_reference_installed_version(self, pre_commit_config):
        """Ruff hooks reference the currently installed ruff version."""
        result = subprocess.run(
            ["ruff", "version"],
            capture_output=True,
            text=True,
            check=True,
        )
        # "ruff 0.15.12 (hash date)" -> "0.15.12"
        installed_version = result.stdout.strip().split()[1]

        for repo in pre_commit_config["repos"]:
            for hook in repo["hooks"]:
                if hook["id"].startswith("ruff"):
                    assert repo["rev"].endswith(installed_version), (
                        f"Hook {hook['id']} rev {repo['rev']} doesn't match ruff {installed_version}"
                    )

    def test_no_commit_to_branch_hook_absent(self, pre_commit_config):
        """no-commit-to-branch hook removed — branch protection via GitHub instead."""
        hook_ids = [hook["id"] for repo in pre_commit_config["repos"] for hook in repo["hooks"]]
        assert "no-commit-to-branch" not in hook_ids

    def test_pre_commit_run_all_files(self):
        """pre-commit run --all-files passes for all configured hooks."""
        result = subprocess.run(
            ["pre-commit", "run", "--all-files"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        assert result.returncode == 0, f"pre-commit failures:\n{result.stdout}\n{result.stderr}"
