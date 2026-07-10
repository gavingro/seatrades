"""Tests for the assignments_tab module."""

from streamlit.testing.v1 import AppTest

from app.tabs.assignments_tab import (
    ACTIVE_RUN_KEY,
    assignment_failure_warning,
    assignment_success_banner,
    finalize_solve,
    render_view,
    solve_view_state,
)
from seatrades.results import SolverState, SolverStatus
from seatrades.solve_run import SolveProgress

# One-liner app that renders just the live-progress fragment against the run seeded into
# session_state. A string (not from_function) so the import resolves in AppTest's fresh
# script namespace and the linter can't hoist/strip it.
_FRAGMENT_SCRIPT = "from app.tabs.assignments_tab import _solve_progress_fragment\n_solve_progress_fragment()\n"


class _RunningRun:
    """Fake SolveRun that stays in-flight, reporting whatever log it's given.

    ``log_text`` is mutated between polls to mimic CBC streaming new lines into the
    log while the solve runs.
    """

    def __init__(self, log_text: str = "") -> None:
        self.log_text = log_text

    def progress(self) -> SolveProgress:
        return SolveProgress(
            running=True,
            percent=0.1,
            message="Optimizing seatrade assignments…",
            log_text=self.log_text,
            timed_out=False,
        )


class _FakeSolution:
    """Minimal stand-in for AssignmentSolution: finalize only reads status.state."""

    def __init__(self, state):
        self.status = SolverStatus(state=state, message="")


class _FinishedRun:
    """Fake SolveRun whose solve has already completed with the given solution."""

    def __init__(self, solution):
        self._solution = solution

    def result(self):
        return self._solution


class TestSolveViewState:
    def test_empty_state_is_idle(self):
        """No active run and no solution → idle."""
        assert solve_view_state({}) == "idle"

    def test_active_run_is_running(self):
        """An active run present → running, even if a prior solution lingers."""
        state = {ACTIVE_RUN_KEY: object(), "assigned_solution": object()}
        assert solve_view_state(state) == "running"

    def test_solution_without_run_is_done(self):
        """A stored solution and no active run → done."""
        assert solve_view_state({"assigned_solution": object()}) == "done"


class TestFinalizeSolve:
    def test_optimal_run_stores_solution_and_clears_active_run(self):
        """A finished optimal solve lands its solution + success=True and frees the guard."""
        solution = _FakeSolution(SolverState.OPTIMAL)
        state = {ACTIVE_RUN_KEY: _FinishedRun(solution)}

        finalize_solve(state[ACTIVE_RUN_KEY], "CBC log lines", state)

        assert state["assigned_solution"] is solution
        assert state["optimization_success"] is True
        assert ACTIVE_RUN_KEY not in state

    def test_error_run_stores_solution_with_success_false(self):
        """A crashed solve still stores its solution but marks success=False."""
        solution = _FakeSolution(SolverState.ERROR)
        state = {ACTIVE_RUN_KEY: _FinishedRun(solution)}

        finalize_solve(state[ACTIVE_RUN_KEY], "CBC log lines", state)

        assert state["assigned_solution"] is solution
        assert state["optimization_success"] is False
        assert ACTIVE_RUN_KEY not in state

    def test_retains_final_solver_log_for_post_solve_inspection(self):
        """The finished run's log is stashed so the done view can show it after solving."""
        solution = _FakeSolution(SolverState.OPTIMAL)
        state = {ACTIVE_RUN_KEY: _FinishedRun(solution)}

        finalize_solve(state[ACTIVE_RUN_KEY], "Cbc0010I solved\nDone", state)

        assert state["solver_log"] == "Cbc0010I solved\nDone"


class TestSolveProgressFragment:
    def test_live_log_reflects_new_output_on_a_later_poll(self):
        """The live solver-log widget shows the newest CBC output as the solve streams it.

        The fragment re-polls every couple of seconds; each poll must render the log as
        it stands *now*, not stay frozen on the first poll's contents (regression: a
        keyed text_area pinned to its first value and never updated).
        """
        at = AppTest.from_string(_FRAGMENT_SCRIPT)
        at.session_state[ACTIVE_RUN_KEY] = _RunningRun(log_text="Cbc0010I first line\n")

        at.run()
        assert not at.exception

        # A later poll: CBC has streamed a new line into the log.
        at.session_state[ACTIVE_RUN_KEY].log_text = "Cbc0010I first line\nCbc0010I newest line\n"
        at.run()
        assert not at.exception

        value = at.text_area[0].value
        assert value is not None and "newest line" in value

    def test_live_log_shows_newest_line_on_top(self):
        """The live panel reverses the log so the latest CBC line reads first, no scroll."""
        at = AppTest.from_string(_FRAGMENT_SCRIPT)
        at.session_state[ACTIVE_RUN_KEY] = _RunningRun(log_text="older line\nnewest line\n")

        at.run()
        assert not at.exception

        value = at.text_area[0].value
        assert value is not None
        assert value.index("newest line") < value.index("older line")


class TestAssignmentFailureWarning:
    def test_error_surfaces_the_message(self):
        """A crashed solve shows its failure message, not the infeasibility copy."""
        status = SolverStatus(state=SolverState.ERROR, message="solver blew up")
        warning = assignment_failure_warning(status)
        assert "solver blew up" in warning

    def test_infeasible_shows_relax_a_limit_copy(self):
        """An infeasible solve keeps the relax-a-hard-limit guidance (unchanged copy)."""
        status = SolverStatus(state=SolverState.INFEASIBLE, message="")
        warning = assignment_failure_warning(status)
        assert "relaxing a hard limit" in warning
        assert "solver blew up" not in warning

    def test_timeout_shows_time_size_copy_not_an_error(self):
        """A timeout is a time/size problem — advise more time or a smaller problem, and
        never call it an unexpected error (the whole point of splitting TIMEOUT off ERROR)."""
        status = SolverStatus(state=SolverState.TIMEOUT, message="", timed_out=True)
        warning = assignment_failure_warning(status)
        assert "time limit" in warning.lower()
        assert "unexpected error" not in warning.lower()
        # The problem is feasible, so the infeasibility "relax a hard limit" copy is wrong here.
        assert "relaxing a hard limit" not in warning


class TestAssignmentSuccessBanner:
    def test_proven_optimal_reports_the_optimality_percent(self):
        """A gap-closed solve is proven near-optimal — state it with the percent."""
        status = SolverStatus(state=SolverState.OPTIMAL, gap=0.08, timed_out=False)
        banner = assignment_success_banner(status)
        assert "Every camper is assigned" in banner
        assert "92% optimal" in banner
        assert "proven" in banner.lower()

    def test_stopped_on_time_flags_it_as_best_so_far(self):
        """A solve that stopped at the time limit holds only the best incumbent — say so,
        and don't reuse the proven "X% optimal" copy that overstates its quality."""
        status = SolverStatus(state=SolverState.OPTIMAL, gap=0.08, timed_out=True)
        banner = assignment_success_banner(status)
        assert "Every camper is assigned" in banner
        assert "time limit" in banner.lower()
        assert "longer solve" in banner.lower()
        assert "proven" not in banner.lower()


class TestRenderView:
    def test_captains_book_returns_wideform(self, seatrade_sort_df):
        """Selecting By Camper should return wide-form dataframe."""
        result = render_view(seatrade_sort_df, "By Camper")
        assert result.columns.tolist() == [
            "cabin",
            "camper",
            "age",
            "Seatrade 1a",
            "Seatrade 1b",
            "Seatrade 2a",
            "Seatrade 2b",
        ]

    def test_captains_book_sorts_by_camper_order(self, seatrade_sort_df):
        """By Camper with camper_order should sort rows by that order."""
        camper_order = ["Carol", "Zed", "Bob", "Alice"]
        result = render_view(seatrade_sort_df, "By Camper", camper_order=camper_order)
        assert result["camper"].tolist() == ["Carol", "Zed", "Bob", "Alice"]

    def test_captains_book_without_camper_order_uses_cabin_sort(self, seatrade_sort_df):
        """By Camper without camper_order should sort by cabin → camper."""
        result = render_view(seatrade_sort_df, "By Camper")
        assert result["camper"].tolist() == ["Alice", "Bob", "Carol", "Zed"]

    def test_seatrade_leaders_returns_simplified_longform(self, seatrade_sort_df):
        """Selecting By Seatrade should return block, seatrade, camper, cabin."""
        result = render_view(seatrade_sort_df, "By Seatrade")
        assert result.columns.tolist() == ["block", "seatrade", "camper", "cabin"]

    def test_seatrade_leaders_ignores_camper_order(self, seatrade_sort_df):
        """By Seatrade view should ignore camper_order."""
        result_without = render_view(seatrade_sort_df, "By Seatrade")
        result_with = render_view(seatrade_sort_df, "By Seatrade", camper_order=["Zed", "Alice"])
        assert result_without.equals(result_with)
