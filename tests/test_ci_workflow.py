"""Verify CI workflow has ruff and mypy steps with correct configuration."""

import subprocess

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


def _step_names(workflow):
    return [s.get("name", s.get("uses", "")) for s in workflow["jobs"]["build"]["steps"]]


def _find_step(workflow, keyword):
    for s in workflow["jobs"]["build"]["steps"]:
        name = s.get("name", "")
        run = s.get("run", "")
        if keyword.lower() in name.lower() or keyword.lower() in run.lower():
            return s
    return None


class TestCIRuffStep:
    """CI workflow includes a ruff check step."""

    def test_ruff_step_exists(self):
        workflow = _load_workflow()
        assert _find_step(workflow, "ruff") is not None

    def test_ruff_step_installs_dev_deps(self):
        """Ruff step uses pip install -e '.[dev]' to get ruff."""
        step = _find_step(_load_workflow(), "ruff")
        run = step.get("run", "")
        assert ".[dev]" in run or "[dev]" in run

    def test_ruff_step_is_non_blocking(self):
        """Lint violations are warnings — ruff step has continue-on-error."""
        step = _find_step(_load_workflow(), "ruff")
        assert step.get("continue-on-error") is True


class TestCIMypyStep:
    """CI workflow includes a mypy step."""

    def test_mypy_step_exists(self):
        workflow = _load_workflow()
        assert _find_step(workflow, "mypy") is not None

    def test_mypy_step_installs_dev_deps(self):
        """Mypy step uses pip install -e '.[dev]' to get mypy."""
        step = _find_step(_load_workflow(), "mypy")
        run = step.get("run", "")
        assert ".[dev]" in run or "[dev]" in run

    def test_mypy_step_is_non_blocking(self):
        """Type errors are warnings — mypy step has continue-on-error."""
        step = _find_step(_load_workflow(), "mypy")
        assert step.get("continue-on-error") is True


class TestCIPytestPreserved:
    """Existing pytest step is still present."""

    def test_pytest_step_exists(self):
        workflow = _load_workflow()
        assert _find_step(workflow, "pytest") is not None
