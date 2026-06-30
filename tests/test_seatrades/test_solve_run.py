"""Tests for the SolveRun service-layer seam."""

import threading
import time

import pytest

from seatrades.config import OptimizationConfig
from seatrades.results import SolverState
from seatrades.solve_run import SolveRun, detect_timeout, percent_from_elapsed


@pytest.fixture
def isolated_config(tmp_path):
    """OptimizationConfig whose CBC log lives under a temp dir, not the cwd."""
    return OptimizationConfig(log_path=tmp_path / "solve.log")


class TestPercentFromElapsed:
    def test_returns_fraction_of_time_limit(self):
        """Halfway through the time limit reports 0.5."""
        assert percent_from_elapsed(30.0, 60.0) == 0.5

    def test_caps_at_one_past_the_limit(self):
        """Elapsed beyond the time limit never exceeds 1.0."""
        assert percent_from_elapsed(90.0, 60.0) == 1.0


class TestDetectTimeout:
    def test_true_when_log_has_time_limit_line(self):
        """CBC's time-limit line marks the solve as timed out."""
        log_text = "Cbc0010I After 0 nodes\nResult - Stopped on time limit\nTotal time 60.0"
        assert detect_timeout(log_text) is True

    def test_false_when_log_lacks_time_limit_line(self):
        """A normal optimal log is not a timeout."""
        log_text = "Result - Optimal solution found\nObjective value 42.0"
        assert detect_timeout(log_text) is False


class TestSolveRunIsSideEffectFree:
    def test_init_does_not_start_thread_or_touch_log(
        self, scheduling_problem, isolated_config, sample_assignment_solution
    ):
        """Construction stores references only — no thread, no log file write."""
        isolated_config.log_path.write_text("pre-existing sentinel")

        run = SolveRun(scheduling_problem, isolated_config, solve_fn=lambda _p, _c: sample_assignment_solution)

        assert run.progress().running is False
        assert run.result() is None
        assert isolated_config.log_path.read_text() == "pre-existing sentinel"


def _wait_until_done(run, timeout=5.0):
    """Poll progress() until the solve finishes, via the public interface."""
    deadline = time.time() + timeout
    while run.progress().running and time.time() < deadline:
        time.sleep(0.01)
    assert run.progress().running is False, "solve did not finish within timeout"


class TestSolveRunOrchestration:
    def test_running_then_completes_with_solution(
        self, scheduling_problem, isolated_config, sample_assignment_solution
    ):
        """While solve_fn blocks, running is True / result None; once it returns, the
        solution is available and running is False."""
        gate = threading.Event()

        def blocking_solve(_problem, _config):
            gate.wait()
            return sample_assignment_solution

        run = SolveRun(scheduling_problem, isolated_config, solve_fn=blocking_solve)
        run.start()

        assert run.progress().running is True
        assert run.result() is None

        gate.set()
        _wait_until_done(run)

        assert run.result() is sample_assignment_solution

    def test_crash_becomes_error_solution_with_message(self, scheduling_problem, isolated_config):
        """A solve_fn that raises yields an ERROR AssignmentSolution whose status
        message carries the exception text — never a propagated crash."""

        def crashing_solve(_problem, _config):
            raise RuntimeError("solver blew up")

        run = SolveRun(scheduling_problem, isolated_config, solve_fn=crashing_solve)
        run.start()
        _wait_until_done(run)

        solution = run.result()
        assert solution is not None
        assert solution.status.state == SolverState.ERROR
        assert "solver blew up" in solution.status.message

    def test_immediate_return_takes_completion_path(
        self, scheduling_problem, isolated_config, sample_assignment_solution
    ):
        """A solve_fn that returns at once still lands on the completion path."""

        run = SolveRun(scheduling_problem, isolated_config, solve_fn=lambda _p, _c: sample_assignment_solution)
        run.start()
        _wait_until_done(run)

        assert run.result() is sample_assignment_solution

    def test_progress_reports_timeout_once_past_limit(
        self, scheduling_problem, isolated_config, sample_assignment_solution
    ):
        """Past the time limit, progress caps percent at 1.0, flags timed_out, and
        switches to the 'finishing up' message — all while still running."""
        isolated_config.solver.timeLimit = 0.01
        gate = threading.Event()

        def blocking_solve(_problem, _config):
            gate.wait()
            return sample_assignment_solution

        run = SolveRun(scheduling_problem, isolated_config, solve_fn=blocking_solve)
        run.start()
        time.sleep(0.05)
        progress = run.progress()
        gate.set()

        assert progress.running is True
        assert progress.percent == 1.0
        assert progress.timed_out is True
        assert progress.message == "Finishing up — time limit reached…"


class TestSolveRunIntegration:
    def test_real_solve_produces_optimal_solution_and_log(self, scheduling_problem, isolated_config):
        """End-to-end through the real solver: an optimal solution comes back and a
        real CBC log is written under the isolated path and readable via progress()."""
        run = SolveRun(scheduling_problem, isolated_config)
        run.start()
        _wait_until_done(run, timeout=30.0)

        solution = run.result()
        assert solution is not None
        assert solution.status.state == SolverState.OPTIMAL
        assert isolated_config.log_path.exists()
        assert run.progress().log_text != ""
