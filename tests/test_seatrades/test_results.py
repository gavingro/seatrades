"""Tests for seatrades/results.py."""

import dataclasses

import pandas as pd
import pytest

from seatrades.results import (
    SolverState,
    SolverStatus,
    wrangle_assignments_to_longform,
    wrangle_fleet_assignments,
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

    def test_optimality_inverts_gap(self):
        status = SolverStatus(state=SolverState.OPTIMAL, gap=0.10)
        assert status.optimality == 0.90

    def test_optimality_is_one_when_gap_missing(self):
        status = SolverStatus(state=SolverState.OPTIMAL, gap=None)
        assert status.optimality == 1.0


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

    def test_age_lookup(self, sample_assignment_solution):
        result = wrangle_assignments_to_longform(sample_assignment_solution)
        alice_rows = result[result["camper"] == "Alice"]
        assert (alice_rows["age"] == 13).all()

    def test_block_split(self, sample_assignment_solution):
        result = wrangle_assignments_to_longform(sample_assignment_solution)
        assert set(result["block"].unique()) == {"1a", "2b"}

    def test_seatrade_names_stripped(self, sample_assignment_solution):
        result = wrangle_assignments_to_longform(sample_assignment_solution)
        assigned = result[result["assignment"] == 1.0]
        assert set(assigned["seatrade"].unique()) == {"Archery", "Sailing", "Climbing"}


@pytest.fixture
def fleet_split_solution(sample_assignment_solution):
    """A 4-block solution with a real fleet split, so both states appear.

    Cabin1 (campers 0,1) is on Fleet 1 — a seatrade in blocks 1a & 2a, Fleet Time in 1b & 2b.
    Cabin2 (campers 2,3) is on Fleet 2 — a seatrade in blocks 1b & 2b, Fleet Time in 1a & 2a.
    """
    camper_ids = pd.Index([0, 1, 2, 3], name="camper_id")
    seatrades_full = [f"{block}_{trade}" for block in ["1a", "1b", "2a", "2b"] for trade in ["Archery", "Sailing"]]
    assignments = pd.DataFrame(0.0, index=camper_ids, columns=seatrades_full)
    assignments.loc[0, ["1a_Archery", "2a_Archery"]] = 1.0
    assignments.loc[1, ["1a_Sailing", "2a_Sailing"]] = 1.0
    assignments.loc[2, ["1b_Archery", "2b_Archery"]] = 1.0
    assignments.loc[3, ["1b_Sailing", "2b_Sailing"]] = 1.0
    return dataclasses.replace(
        sample_assignment_solution,
        assignments=assignments,
        seatrades_full=seatrades_full,
    )


class TestWrangleFleetAssignments:
    def test_one_row_per_cabin_block_over_solution_blocks(self, sample_assignment_solution):
        # sample_assignment_solution only spans blocks 1a and 2b, so the grid derives
        # exactly those two blocks — cabins × present blocks, no phantom rows.
        result = wrangle_fleet_assignments(sample_assignment_solution)
        assert set(result.columns) >= {"cabin", "block", "state"}
        assert len(result) == 2 * 2  # 2 cabins × 2 present blocks
        assert set(result["cabin"]) == {"Cabin1", "Cabin2"}
        assert set(result["block"]) == {"1a", "2b"}

    def test_spans_all_four_blocks_when_solution_does(self, fleet_split_solution):
        result = wrangle_fleet_assignments(fleet_split_solution)
        assert len(result) == 2 * 4  # 2 cabins × 4 blocks
        assert list(result["block"].unique()) == ["1a", "1b", "2a", "2b"]  # canonical order

    def test_cabin_on_a_seatrade_reads_seatrade(self, fleet_split_solution):
        result = wrangle_fleet_assignments(fleet_split_solution)
        cell = result[(result["cabin"] == "Cabin1") & (result["block"] == "1a")]
        assert cell["state"].item() == "Seatrade"

    def test_cabin_with_no_assignment_reads_fleet_time(self, fleet_split_solution):
        # Cabin1 is on Fleet 1, so block 1b (a Fleet 2 slot) is Fleet Time for it.
        result = wrangle_fleet_assignments(fleet_split_solution)
        cell = result[(result["cabin"] == "Cabin1") & (result["block"] == "1b")]
        assert cell["state"].item() == "Fleet Time"
