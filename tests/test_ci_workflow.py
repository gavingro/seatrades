"""Verify CI workflow has lint and test jobs with correct configuration."""

import subprocess
import sys

import yaml

PROJECT_ROOT = subprocess.run(
    ["git", "rev-parse", "--show-toplevel"],
    capture_output=True,
    text=True,
    check=True,
).stdout.strip()

CI_WORKFLOW = PROJECT_ROOT + "/.github/workflows/ci.yaml"


def _load_workflow():
    with open(CI_WORKFLOW) as f:
        return yaml.safe_load(f)


def _find_step(workflow, keyword, job):
    for s in workflow["jobs"][job]["steps"]:
        name = s.get("name", "")
        run = s.get("run", "")
        if keyword.lower() in name.lower() or keyword.lower() in run.lower():
            return s
    return None


class TestCILintJob:
    """CI lint job includes ruff and mypy steps."""

    def test_lint_job_exists(self):
        workflow = _load_workflow()
        assert "lint" in workflow["jobs"]

    def test_lint_job_installs_dev_deps(self):
        """Lint job has a separate install step with dev deps."""
        step = _find_step(_load_workflow(), "install", "lint")
        run = step.get("run", "")
        assert ".[dev]" in run or "[dev]" in run

    def test_ruff_step_exists(self):
        step = _find_step(_load_workflow(), "ruff", "lint")
        assert step is not None

    def test_mypy_step_exists(self):
        step = _find_step(_load_workflow(), "mypy", "lint")
        assert step is not None


class TestCITestJob:
    """CI test job includes pytest."""

    def test_test_job_exists(self):
        workflow = _load_workflow()
        assert "test" in workflow["jobs"]

    def test_test_job_installs_dev_deps(self):
        """Test job has a separate install step with dev deps."""
        step = _find_step(_load_workflow(), "install", "test")
        run = step.get("run", "")
        assert ".[dev]" in run or "[dev]" in run

    def test_pytest_step_exists(self):
        step = _find_step(_load_workflow(), "pytest", "test")
        assert step is not None


class TestDoctestCollection:
    """CI runs `pytest --doctest-modules`. The app.py entry script and the app/
    package both claim module name 'app', so doctest collection imports one and
    mismatches the other unless the entry script is excluded from collection."""

    def test_doctest_modules_collection_succeeds(self):
        result = subprocess.run(
            [sys.executable, "-m", "pytest", ".", "--doctest-modules", "--collect-only", "-q"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        output = result.stdout + result.stderr
        assert "import file mismatch" not in output, output
        assert result.returncode == 0, output
