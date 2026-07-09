"""Tests for seatrades/results.py."""

import dataclasses

import pandas as pd
import pytest

from seatrades.results import (
    UNMATCHED_PREFERENCE,
    SolverState,
    SolverStatus,
    wrangle_assignments_to_longform,
    wrangle_fleet_assignments,
    wrangle_seatrade_staffing,
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
        expected_cols = {"camper", "seatrade", "assignment", "preference_rank", "assigned_to_block", "cabin", "block"}
        assert expected_cols <= set(result.columns)

    def test_conflated_preference_column_is_gone(self, sample_assignment_solution):
        # The old single ``preference`` column conflated unassigned/assigned/unranked. It is
        # decomposed into assignment + preference_rank; leaving it would reintroduce the conflation.
        result = wrangle_assignments_to_longform(sample_assignment_solution)
        assert "preference" not in result.columns

    def test_unassigned_ranked_cell_carries_its_rank(self, sample_assignment_solution):
        # The core fix: an unassigned cell now records the rank the camper GAVE it, so a
        # near-miss is recoverable. Alice (prefs Archery, Sailing, ...) got 1a_Archery, so
        # her 1a_Sailing cell is unassigned but still carries rank 2.
        result = wrangle_assignments_to_longform(sample_assignment_solution)
        cell = result[(result["camper"] == "Alice") & (result["block"] == "1a") & (result["seatrade"] == "Sailing")]
        assert cell["assignment"].item() == 0.0
        assert cell["preference_rank"].item() == 2

    def test_assigned_ranked_rows_carry_their_rank(self, sample_assignment_solution):
        result = wrangle_assignments_to_longform(sample_assignment_solution)
        assigned = result[result["assignment"] == 1.0]
        assert assigned["preference_rank"].isin([1, 2, 3, 4, UNMATCHED_PREFERENCE]).all()

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


@pytest.fixture
def unranked_seatrade_solution(sample_assignment_solution):
    """The sample plus a Diving offering nobody ranked — so cells for it carry the sentinel.

    Every camper in the sample ranks all three *running* seatrades, so there are no unranked
    cells to test. Diving is offered but on nobody's preference list — the assigned-but-unranked
    (and unassigned-unranked) cell state.
    """
    assignments = sample_assignment_solution.assignments.copy()
    assignments["1a_Diving"] = 0.0
    seatrades_full = sample_assignment_solution.seatrades_full + ["1a_Diving"]
    return dataclasses.replace(
        sample_assignment_solution,
        assignments=assignments,
        seatrades_full=seatrades_full,
    )


class TestLongformScheduleAndPreferenceFacts:
    """The decomposed cell facts: preference_rank (camper↔seatrade) vs assigned_to_block (schedule)."""

    def _cell(self, result, camper, block, seatrade):
        return result[
            (result["camper"] == camper) & (result["block"] == block) & (result["seatrade"] == seatrade)
        ].iloc[0]

    def test_unranked_cell_carries_the_unmatched_sentinel(self, unranked_seatrade_solution):
        # A cell for a seatrade the camper never ranked holds UNMATCHED_PREFERENCE (not 0) — the
        # "unranked" state, kept off the display by the color/ghost filters, not by a zero rank.
        result = wrangle_assignments_to_longform(unranked_seatrade_solution)
        diving = result[result["seatrade"] == "Diving"]
        assert (diving["preference_rank"] == UNMATCHED_PREFERENCE).all()

    def test_ghost_rank_survives_in_the_campers_other_attended_block(self, sample_assignment_solution):
        # Alice got Archery (her #1) in block 1a and Sailing in 2b. Her Archery rank must STILL
        # surface in 2b — an unassigned, ranked cell in a block she attends — so a split same-pref
        # group stays fully visible (show-even-if-fulfilled-elsewhere). This is the key decision.
        result = wrangle_assignments_to_longform(sample_assignment_solution)
        cell = self._cell(result, "Alice", "2b", "Archery")
        assert cell["assignment"] == 0.0
        assert cell["preference_rank"] == 1
        assert bool(cell["assigned_to_block"]) is True

    def test_assigned_to_block_true_where_camper_has_a_seatrade(self, fleet_split_solution):
        # Cabin1's camper 0 is on Fleet 1: a seatrade in block 1a.
        result = wrangle_assignments_to_longform(fleet_split_solution)
        cell = self._cell(result, "Alice", "1a", "Archery")
        assert bool(cell["assigned_to_block"]) is True

    def test_assigned_to_block_false_in_a_fleet_time_block(self, fleet_split_solution):
        # Camper 0 is on Fleet 1, so block 1b is Fleet Time for them — no seatrade that block.
        result = wrangle_assignments_to_longform(fleet_split_solution)
        block_1b = result[(result["camper"] == "Alice") & (result["block"] == "1b")]
        assert (block_1b["assigned_to_block"] == False).all()  # noqa: E712

    def test_preference_rank_populated_even_in_a_fleet_time_block(self, fleet_split_solution):
        # preference_rank is a pure camper↔seatrade fact, so it is present even on a Fleet Time
        # block's cells; assigned_to_block is what keeps a ghost from drawing there, not a blank rank.
        result = wrangle_assignments_to_longform(fleet_split_solution)
        cell = self._cell(result, "Alice", "1b", "Sailing")  # Alice ranks Sailing #2
        assert cell["preference_rank"] == 2
        assert bool(cell["assigned_to_block"]) is False


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


@pytest.fixture
def zero_uptake_solution(sample_assignment_solution):
    """The sample plus a Kayaking offering nobody picked — an all-zero column in each block.

    Kayaking is in ``seatrades_full`` (offered in the setup) but carries no assignment, so it
    is the zero-uptake case: a seatrade with nobody to staff it, a full ``Not offered`` row.
    """
    assignments = sample_assignment_solution.assignments.copy()
    assignments["1a_Kayaking"] = 0.0
    assignments["2b_Kayaking"] = 0.0
    seatrades_full = sample_assignment_solution.seatrades_full + ["1a_Kayaking", "2b_Kayaking"]
    return dataclasses.replace(
        sample_assignment_solution,
        assignments=assignments,
        seatrades_full=seatrades_full,
    )


class TestWrangleSeatradeStaffing:
    def test_one_row_per_seatrade_block_over_solution_blocks(self, sample_assignment_solution):
        # sample spans blocks 1a and 2b with 3 seatrades (Archery, Sailing, Climbing),
        # so the grid is those 3 seatrades × the 2 present blocks — no phantom rows.
        result = wrangle_seatrade_staffing(sample_assignment_solution)
        assert set(result.columns) >= {"seatrade", "block", "state"}
        assert len(result) == 3 * 2  # 3 seatrades × 2 present blocks
        assert set(result["seatrade"]) == {"Archery", "Sailing", "Climbing"}
        assert set(result["block"]) == {"1a", "2b"}

    def test_seatrade_running_a_block_reads_running(self, sample_assignment_solution):
        # Archery is picked in block 1a (campers Alice & Dave), so it runs there.
        result = wrangle_seatrade_staffing(sample_assignment_solution)
        cell = result[(result["seatrade"] == "Archery") & (result["block"] == "1a")]
        assert cell["state"].item() == "Running"

    def test_seatrade_with_no_uptake_reads_not_offered(self, zero_uptake_solution):
        # Kayaking is offered but nobody picked it — Not offered in every block.
        result = wrangle_seatrade_staffing(zero_uptake_solution)
        kayaking = result[result["seatrade"] == "Kayaking"]
        assert (kayaking["state"] == "Not offered").all()

    def test_zero_uptake_seatrade_is_a_full_not_offered_row(self, zero_uptake_solution):
        # Every offered seatrade gets a row even at zero uptake, surfacing nobody-to-staff.
        result = wrangle_seatrade_staffing(zero_uptake_solution)
        assert "Kayaking" in set(result["seatrade"])
        kayaking = result[result["seatrade"] == "Kayaking"]
        assert len(kayaking) == 2  # both present blocks, all Not offered

    def test_rows_follow_seatrades_full_order_not_alphabetical(self, sample_assignment_solution):
        # display_seatrade_staffing derives its y-axis sort from this row order, so the wrangler
        # must emit seatrades in seatrades_full order. The sample order is Archery, Sailing,
        # Climbing — deliberately NOT alphabetical (Archery, Climbing, Sailing) — so this pins
        # the contract: a future regroup/sort that reordered rows would flip the view's y-axis.
        result = wrangle_seatrade_staffing(sample_assignment_solution)
        assert list(dict.fromkeys(result["seatrade"])) == ["Archery", "Sailing", "Climbing"]
