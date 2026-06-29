"""Tests for seatrades.solver — the solver.run() entry point."""

import pandas as pd
import pulp
import pytest

from seatrades.config import OptimizationConfig
from seatrades.problem import SchedulingProblem
from seatrades.results import (
    AssignmentSolution,
    SolverState,
    wrangle_assignments_to_longform,
    wrangle_assignments_to_wideform,
)
from seatrades.solver import run


class TestSolverRun:
    """solver.run(problem, config) -> AssignmentSolution."""

    def test_run_returns_assignment_solution(self, scheduling_problem, default_config):
        solution = run(scheduling_problem, default_config)
        assert isinstance(solution, AssignmentSolution)
        assert solution.status.state == SolverState.OPTIMAL

    def test_assignments_has_campers_as_index(self, scheduling_problem, default_config):
        solution = run(scheduling_problem, default_config)
        assert set(solution.assignments.index) == set(scheduling_problem.campers)

    def test_assignments_columns_match_seatrades_full(self, scheduling_problem, default_config):
        solution = run(scheduling_problem, default_config)
        assert list(solution.assignments.columns) == scheduling_problem.seatrades_full

    def test_domain_data_comes_from_problem(self, scheduling_problem, default_config):
        solution = run(scheduling_problem, default_config)
        assert solution.cabins == scheduling_problem.cabins
        # solution exposes camper NAMES; the problem's campers are internal integer IDs.
        assert solution.campers == scheduling_problem.camper_names
        assert solution.seatrades_full == scheduling_problem.seatrades_full
        assert solution.cabin_camper_prefs.equals(scheduling_problem.cabin_camper_prefs)
        assert solution.camper_prefs.equals(scheduling_problem.camper_prefs)

    def test_each_camper_assigned_one_seatrade_per_block(self, scheduling_problem, default_config):
        solution = run(scheduling_problem, default_config)
        for camper in solution.assignments.index:
            for block_pair in [("1a", "1b"), ("2a", "2b")]:
                cols = [
                    c
                    for c in solution.assignments.columns
                    if c.startswith(f"{block_pair[0]}_") or c.startswith(f"{block_pair[1]}_")
                ]
                total = solution.assignments.loc[camper, cols].sum()
                assert total == 1.0, f"Camper {camper} has sum {total} in block {block_pair}"

    def test_seatrade_names_with_spaces(self):
        """Seatrade names containing spaces must round-trip through PuLP without breakage."""
        joined = pd.DataFrame(
            {
                "cabin": ["Cabin1", "Cabin1", "Cabin2", "Cabin2"],
                "camper": ["Alice", "Bob", "Carol", "Dave"],
                "gender": ["F", "M", "F", "M"],
                "seatrade_1": ["Canoeing and Kayaking", "High Ropes", "Laser Tag", "Giant Swing"],
                "seatrade_2": ["High Ropes", "Canoeing and Kayaking", "Giant Swing", "Laser Tag"],
                "seatrade_3": ["Laser Tag", "Giant Swing", "Canoeing and Kayaking", "High Ropes"],
                "seatrade_4": ["Giant Swing", "Laser Tag", "High Ropes", "Canoeing and Kayaking"],
            }
        )
        setup = pd.DataFrame(
            {
                "seatrade": ["Canoeing and Kayaking", "High Ropes", "Laser Tag", "Giant Swing"],
                "campers_min": [0, 0, 0, 0],
                "campers_max": [10, 10, 10, 10],
            }
        )
        problem = SchedulingProblem(joined, setup)
        config = OptimizationConfig(solver=__import__("pulp").apis.PULP_CBC_CMD(msg=0))
        solution = run(problem, config)

        assert solution.status.state == SolverState.OPTIMAL
        assert list(solution.assignments.columns) == problem.seatrades_full
        # Verify column names contain spaces (not mangled to underscores)
        assert "1a_Canoeing and Kayaking" in solution.assignments.columns

    def test_resolve_produces_clean_names_no_suffix(self):
        """Re-solving the same data yields clean camper names — no .N index suffix leaks."""
        joined = pd.DataFrame(
            {
                "cabin": ["Cabin1", "Cabin1", "Cabin2", "Cabin2"],
                "camper": ["Alice", "Bob", "Carol", "Dave"],
                "gender": ["F", "M", "F", "M"],
                "seatrade_1": ["Archery", "Climbing", "Sailing", "Archery"],
                "seatrade_2": ["Sailing", "Archery", "Archery", "Climbing"],
                "seatrade_3": ["Climbing", "Sailing", "Climbing", "Sailing"],
                "seatrade_4": ["Kayaking", "Kayaking", "Kayaking", "Kayaking"],
            }
        )
        setup = pd.DataFrame(
            {
                "seatrade": ["Archery", "Sailing", "Climbing", "Kayaking"],
                "campers_min": [0, 0, 0, 0],
                "campers_max": [10, 10, 10, 10],
            }
        )
        config = OptimizationConfig(solver=pulp.apis.PULP_CBC_CMD(msg=0))

        # Build and solve twice from the same source data — the old suffix hack
        # mutated names and leaked compounding suffixes on repeated construction.
        run(SchedulingProblem(joined, setup), config)
        solution = run(SchedulingProblem(joined, setup), config)

        names = wrangle_assignments_to_longform(solution)["camper"].unique().tolist()
        assert set(names) == {"Alice", "Bob", "Carol", "Dave"}
        assert all("." not in name for name in names)
        assert solution.campers == ["Alice", "Bob", "Carol", "Dave"]

    def test_same_name_different_cabin(self):
        """Two campers sharing a name stay distinct: internally by camper_id, in output by the (cabin, camper) key."""
        joined = pd.DataFrame(
            {
                "cabin": ["Cabin1", "Cabin1", "Cabin2", "Cabin2"],
                "camper": ["Alex", "Bob", "Alex", "Dave"],
                "gender": ["F", "M", "F", "M"],
                "seatrade_1": ["Archery", "Climbing", "Sailing", "Archery"],
                "seatrade_2": ["Sailing", "Archery", "Archery", "Climbing"],
                "seatrade_3": ["Climbing", "Sailing", "Climbing", "Sailing"],
                "seatrade_4": ["Kayaking", "Kayaking", "Kayaking", "Kayaking"],
            }
        )
        setup = pd.DataFrame(
            {
                "seatrade": ["Archery", "Sailing", "Climbing", "Kayaking"],
                "campers_min": [0, 0, 0, 0],
                "campers_max": [10, 10, 10, 10],
            }
        )
        config = OptimizationConfig(solver=pulp.apis.PULP_CBC_CMD(msg=0))

        solution = run(SchedulingProblem(joined, setup), config)
        longform = wrangle_assignments_to_longform(solution)

        alex_rows = longform[longform["camper"] == "Alex"]
        assert set(alex_rows["cabin"].unique()) == {"Cabin1", "Cabin2"}

        wideform = wrangle_assignments_to_wideform(longform)
        alex_wide = wideform[wideform["camper"] == "Alex"]
        assert len(alex_wide) == 2
        assert set(alex_wide["cabin"]) == {"Cabin1", "Cabin2"}


class TestMangle:
    """Name mangling must match PuLP's internal variable naming."""

    def test_spaces_replaced_with_underscores(self):
        from seatrades.solver import _mangle

        assert _mangle("Canoeing and Kayaking") == "Canoeing_and_Kayaking"

    def test_hyphens_replaced_with_underscores(self):
        from seatrades.solver import _mangle

        assert _mangle("Jean-Luc") == "Jean_Luc"

    def test_dots_preserved(self):
        from seatrades.solver import _mangle

        assert _mangle("J.R.") == "J.R."

    def test_plus_sign_replaced(self):
        from seatrades.solver import _mangle

        assert _mangle("C++") == "C__"

    def test_unicode_letters_preserved(self):
        from seatrades.solver import _mangle

        assert _mangle("Bárbara") == "Bárbara"
        assert _mangle("José") == "José"
        assert _mangle("François") == "François"

    def test_no_special_chars(self):
        from seatrades.solver import _mangle

        assert _mangle("Alice") == "Alice"


class TestExtractCamperAssignments:
    """_extract_camper_assignments must find all expected variables."""

    def test_raises_when_variable_name_missing(self):
        """If _mangle produces a name that doesn't match, extraction must raise, not silently default to 0."""
        import pulp

        from seatrades.solver import _extract_camper_assignments

        # Create a minimal solved problem with known variables
        prob = pulp.LpProblem("test", pulp.LpMinimize)
        x = pulp.LpVariable("x", lowBound=0)
        prob += x
        prob.solve(pulp.PULP_CBC_CMD(msg=0))

        # Request a camper id whose variables don't exist in the problem
        with pytest.raises(ValueError, match="Expected.*variables.*found"):
            _extract_camper_assignments(prob.variables(), [0], ["1a_Archery"])


class TestStatusCodeMapping:
    """Solver status code must map PuLP codes correctly."""

    def test_optimal_status_passes_through(self, scheduling_problem, default_config):
        solution = run(scheduling_problem, default_config)
        assert solution.status.state == SolverState.OPTIMAL

    def test_optimal_solution_has_gap(self, scheduling_problem, default_config):
        solution = run(scheduling_problem, default_config)
        # Gap may be None if CBC doesn't write a gap line (small problems solve instantly)
        # but the field should be populated when available
        assert solution.status.gap is None or isinstance(solution.status.gap, float)

    def test_infeasible_solution_has_no_gap(self):
        joined = pd.DataFrame(
            {
                "cabin": ["Cabin1", "Cabin1"],
                "camper": ["Alice", "Bob"],
                "gender": ["F", "M"],
                "seatrade_1": ["Archery", "Archery"],
                "seatrade_2": ["Archery", "Archery"],
                "seatrade_3": ["Archery", "Archery"],
                "seatrade_4": ["Archery", "Archery"],
            }
        )
        setup = pd.DataFrame(
            {
                "seatrade": ["Archery"],
                "campers_min": [2],
                "campers_max": [2],
            }
        )
        problem = SchedulingProblem(joined, setup)
        config = OptimizationConfig(solver=__import__("pulp").apis.PULP_CBC_CMD(msg=0))
        solution = run(problem, config)
        assert solution.status.state == SolverState.INFEASIBLE
        assert solution.status.gap is None

    def test_infeasible_problem_returns_infeasible(self):
        """An infeasible problem should return SolverState.INFEASIBLE, not ERROR."""

        # 2 campers, 1 seatrade with max 1 — can't assign both
        joined = pd.DataFrame(
            {
                "cabin": ["Cabin1", "Cabin1"],
                "camper": ["Alice", "Bob"],
                "gender": ["F", "M"],
                "seatrade_1": ["Archery", "Archery"],
                "seatrade_2": ["Archery", "Archery"],
                "seatrade_3": ["Archery", "Archery"],
                "seatrade_4": ["Archery", "Archery"],
            }
        )
        setup = pd.DataFrame(
            {
                "seatrade": ["Archery"],
                "campers_min": [2],
                "campers_max": [2],
            }
        )
        problem = SchedulingProblem(joined, setup)
        config = OptimizationConfig(solver=__import__("pulp").apis.PULP_CBC_CMD(msg=0))
        solution = run(problem, config)
        # Infeasible should map to INFEASIBLE, not be swallowed as ERROR
        assert solution.status.state == SolverState.INFEASIBLE


class TestConditionalMinCapacity:
    """`campers_min` is a viability threshold, not a forced quota (issue #48).

    A session may have either 0 campers (it doesn't run) or a count within
    [campers_min, campers_max] (it runs). A seatrade nobody ranked simply drops.
    """

    # Four campers rank only pick1-pick4 (enough to fill both block pairs for
    # everyone). notpicked1 has campers_min > 0 but nobody ranks it.
    _joined = pd.DataFrame(
        {
            "cabin": ["Cabin1", "Cabin1", "Cabin2", "Cabin2"],
            "camper": ["Alice", "Bob", "Carol", "Dave"],
            "gender": ["F", "F", "M", "M"],
            "seatrade_1": ["pick1", "pick2", "pick3", "pick4"],
            "seatrade_2": ["pick2", "pick3", "pick4", "pick1"],
            "seatrade_3": ["pick3", "pick4", "pick1", "pick2"],
            "seatrade_4": ["pick4", "pick1", "pick2", "pick3"],
        }
    )
    _setup = pd.DataFrame(
        {
            "seatrade": ["pick1", "pick2", "pick3", "pick4", "notpicked1"],
            "campers_min": [0, 0, 0, 0, 2],
            "campers_max": [10, 10, 10, 10, 10],
        }
    )

    def test_unranked_session_drops_instead_of_infeasible(self):
        """Default (conditional min): notpicked1's sessions drop to 0; solve is OPTIMAL."""
        problem = SchedulingProblem(self._joined, self._setup)
        config = OptimizationConfig(solver=pulp.apis.PULP_CBC_CMD(msg=0))
        solution = run(problem, config)

        assert solution.status.state == SolverState.OPTIMAL
        notpicked_cols = [c for c in solution.assignments.columns if c.endswith("_notpicked1")]
        assert notpicked_cols  # the columns exist...
        assert solution.assignments[notpicked_cols].to_numpy().sum() == 0  # ...but hold no campers

    def test_dropped_session_absent_from_exports(self):
        """A non-running session yields no assigned rows, so it never reaches the
        wrangled exports/charts (user story 5)."""
        problem = SchedulingProblem(self._joined, self._setup)
        config = OptimizationConfig(solver=pulp.apis.PULP_CBC_CMD(msg=0))
        solution = run(problem, config)

        longform = wrangle_assignments_to_longform(solution)
        assigned = longform[longform["assignment"] == 1.0]
        assert "notpicked1" not in assigned["seatrade"].to_numpy()

        wideform = wrangle_assignments_to_wideform(longform)
        assert "notpicked1" not in wideform.to_numpy()

    def test_legacy_force_fill_is_infeasible(self):
        """allow_empty_sessions=False restores the hard floor: notpicked1 can't fill -> INFEASIBLE."""
        problem = SchedulingProblem(self._joined, self._setup)
        config = OptimizationConfig(allow_empty_sessions=False, solver=pulp.apis.PULP_CBC_CMD(msg=0))
        solution = run(problem, config)

        assert solution.status.state == SolverState.INFEASIBLE
