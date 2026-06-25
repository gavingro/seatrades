"""Tests for seatrades/results.py."""

import pandas as pd

from seatrades.results import (
    SolverState,
    SolverStatus,
    wrangle_assignments_to_longform,
)


class TestSolverState:
    def test_has_three_members(self):
        assert set(SolverState.__members__.keys()) == {"OPTIMAL", "INFEASIBLE", "ERROR"}

    def test_optimal_value(self):
        assert SolverState.OPTIMAL.value == "OPTIMAL"

    def test_infeasible_value(self):
        assert SolverState.INFEASIBLE.value == "INFEASIBLE"

    def test_error_value(self):
        assert SolverState.ERROR.value == "ERROR"

    def test_from_pulp_optimal(self):
        assert SolverState.from_pulp(1) == SolverState.OPTIMAL

    def test_from_pulp_infeasible(self):
        assert SolverState.from_pulp(-1) == SolverState.INFEASIBLE

    def test_from_pulp_unsolved_maps_to_error(self):
        assert SolverState.from_pulp(0) == SolverState.ERROR

    def test_from_pulp_unbounded_maps_to_error(self):
        assert SolverState.from_pulp(-2) == SolverState.ERROR

    def test_from_pulp_undefined_maps_to_error(self):
        assert SolverState.from_pulp(-3) == SolverState.ERROR


class TestSolverStatus:
    def test_construction_with_defaults(self):
        status = SolverStatus(state=SolverState.OPTIMAL)
        assert status.state == SolverState.OPTIMAL
        assert status.gap is None
        assert status.message == ""

    def test_construction_with_all_fields(self):
        status = SolverStatus(
            state=SolverState.INFEASIBLE,
            gap=0.05,
            message="Problem infeasible",
        )
        assert status.state == SolverState.INFEASIBLE
        assert status.gap == 0.05
        assert status.message == "Problem infeasible"

    def test_from_pulp_optimal(self):
        status = SolverStatus.from_pulp(1)
        assert status.state == SolverState.OPTIMAL
        assert status.message == ""

    def test_from_pulp_infeasible(self):
        status = SolverStatus.from_pulp(-1)
        assert status.state == SolverState.INFEASIBLE
        assert status.message == ""

    def test_from_pulp_error_includes_message(self):
        status = SolverStatus.from_pulp(0)
        assert status.state == SolverState.ERROR
        assert "not solved" in status.message.lower()

    def test_from_pulp_unbounded_includes_message(self):
        status = SolverStatus.from_pulp(-2)
        assert status.state == SolverState.ERROR
        assert "unbounded" in status.message.lower()

    def test_from_pulp_undefined_status(self):
        status = SolverStatus.from_pulp(-3)
        assert status.state == SolverState.ERROR
        assert "undefined" in status.message.lower()

    def test_from_pulp_unknown_status(self):
        status = SolverStatus.from_pulp(99)
        assert status.state == SolverState.ERROR
        assert "99" in status.message


class TestAssignmentSolution:
    def test_construction(self, sample_assignment_solution):
        sol = sample_assignment_solution
        assert isinstance(sol.assignments, pd.DataFrame)
        assert isinstance(sol.status, SolverStatus)
        assert sol.status.state == SolverState.OPTIMAL
        assert sol.cabins == ["Cabin1", "Cabin2"]
        assert sol.campers == ["Alice", "Bob", "Carol", "Dave"]
        assert "1a_Archery" in sol.seatrades_full

    def test_assignments_has_campers_as_index(self, sample_assignment_solution):
        sol = sample_assignment_solution
        assert sol.assignments.index.name == "camper_id"
        assert len(sol.assignments) == 4

    def test_cabin_camper_prefs_has_cabin_column(self, sample_assignment_solution):
        sol = sample_assignment_solution
        assert "cabin" in sol.cabin_camper_prefs.columns
        assert sol.cabin_camper_prefs.index.name == "camper_id"


class TestWrangleAssignmentsToLongform:
    def test_output_columns(self, sample_assignment_solution):
        result = wrangle_assignments_to_longform(sample_assignment_solution)
        expected_cols = {"camper", "seatrade", "assignment", "preference", "cabin", "block"}
        assert expected_cols <= set(result.columns)

    def test_assigned_rows_have_nonzero_preference(self, sample_assignment_solution):
        result = wrangle_assignments_to_longform(sample_assignment_solution)
        assigned = result[result["assignment"] == 1.0]
        assert (assigned["preference"] > 0).all()

    def test_unassigned_rows_have_zero_preference(self, sample_assignment_solution):
        result = wrangle_assignments_to_longform(sample_assignment_solution)
        unassigned = result[result["assignment"] == 0.0]
        assert (unassigned["preference"] == 0).all()

    def test_cabin_lookup(self, sample_assignment_solution):
        result = wrangle_assignments_to_longform(sample_assignment_solution)
        alice_rows = result[result["camper"] == "Alice"]
        assert (alice_rows["cabin"] == "Cabin1").all()

    def test_block_split(self, sample_assignment_solution):
        result = wrangle_assignments_to_longform(sample_assignment_solution)
        assert set(result["block"].unique()) == {"1a", "2b"}

    def test_seatrade_names_stripped(self, sample_assignment_solution):
        result = wrangle_assignments_to_longform(sample_assignment_solution)
        assigned = result[result["assignment"] == 1.0]
        assert set(assigned["seatrade"].unique()) == {"Archery", "Sailing", "Climbing"}
