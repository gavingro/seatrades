"""Tests for the assignments_tab module."""

from app.tabs.assignments_tab import (
    ACTIVE_RUN_KEY,
    assignment_failure_warning,
    finalize_solve,
    render_view,
    solve_view_state,
)
from seatrades.results import SolverState, SolverStatus


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
