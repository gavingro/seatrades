"""Tests for seatrades/scoring.py — post-hoc schedule goodness measurement."""

import dataclasses

import pandas as pd
import pytest

from seatrades.results import AssignmentSolution, SolverState, SolverStatus
from seatrades.scoring import (
    COHESION_HIGH_ANCHOR,
    COHESION_LOW_ANCHOR,
    PREFERENCE_HIGH_ANCHOR,
    PREFERENCE_LOW_ANCHOR,
    SPARSITY_HIGH_ANCHOR,
    SPARSITY_LOW_ANCHOR,
    Scorecard,
    score,
)


def _one_camper_solution(prefs: list[str], assigned: tuple[str, str]) -> AssignmentSolution:
    """A single-camper solution: ``prefs`` ranked #1–4; ``assigned`` = the two seatrades
    (block 1a, block 2b) the camper actually got. Lets a test pin one camper's CPR exactly.
    """
    block_a, block_b = f"1a_{assigned[0]}", f"2b_{assigned[1]}"
    seatrades_full = [f"1a_{s}" for s in prefs] + [f"2b_{s}" for s in prefs]
    row = {col: (1.0 if col in (block_a, block_b) else 0.0) for col in seatrades_full}
    camper_ids = pd.Index([0], name="camper_id")
    return AssignmentSolution(
        assignments=pd.DataFrame([row], index=camper_ids),
        status=SolverStatus(state=SolverState.OPTIMAL),
        cabins=["Cabin1"],
        campers=["Solo"],
        seatrades_full=seatrades_full,
        cabin_camper_prefs=pd.DataFrame({"cabin": ["Cabin1"], "age": [12]}, index=camper_ids),
        camper_prefs=pd.Series([prefs], index=camper_ids),
        camper_names=pd.Series(["Solo"], index=camper_ids),
    )


def _roster_solution(campers: list[tuple[str, str, list[tuple[str, str]]]]) -> AssignmentSolution:
    """Build a solution from ``(name, cabin, [(block, seatrade), ...])`` rows.

    Each camper is assigned exactly the ``(block, seatrade)`` sessions listed; any block
    they have no session in is Fleet Time (no assignment row). Lets a test place chosen
    cabinmates in chosen sessions to pin Cohesion exactly. Preferences are irrelevant to
    Cohesion, so a placeholder ranking is used.
    """
    columns = sorted({f"{block}_{seatrade}" for _, _, sessions in campers for block, seatrade in sessions})
    camper_ids = pd.Index(range(len(campers)), name="camper_id")
    rows = []
    for _, _, sessions in campers:
        assigned = {f"{block}_{seatrade}" for block, seatrade in sessions}
        rows.append({col: (1.0 if col in assigned else 0.0) for col in columns})
    names = [name for name, _, _ in campers]
    cabins = [cabin for _, cabin, _ in campers]
    return AssignmentSolution(
        assignments=pd.DataFrame(rows, index=camper_ids, columns=columns),
        status=SolverStatus(state=SolverState.OPTIMAL),
        cabins=list(dict.fromkeys(cabins)),
        campers=names,
        seatrades_full=columns,
        cabin_camper_prefs=pd.DataFrame({"cabin": cabins, "age": [12] * len(campers)}, index=camper_ids),
        camper_prefs=pd.Series([["placeholder"]] * len(campers), index=camper_ids),
        camper_names=pd.Series(names, index=camper_ids),
    )


def _preference(card: Scorecard):
    return card.metric("Preference")


def _cohesion(card: Scorecard):
    return card.metric("Cohesion")


def _sparsity(card: Scorecard):
    return card.metric("Sparsity")


class TestCohesionRawValue:
    def test_stranded_roster_scores_zero(self, sample_assignment_solution):
        """Fixture campers never share a seatrade session with a cabinmate → 0.0 share."""
        assert _cohesion(score(sample_assignment_solution)).raw_value == 0.0

    def test_cabinmates_in_same_session_both_share(self):
        """Two cabinmates in the same (block, seatrade) both count as sharing → 1.0."""
        solution = _roster_solution(
            [
                ("Ann", "Cabin1", [("1a", "Archery")]),
                ("Bea", "Cabin1", [("1a", "Archery")]),
            ]
        )
        assert _cohesion(score(solution)).raw_value == 1.0

    def test_fleet_time_copresence_does_not_count(self):
        """Cabinmates who share only a Fleet-Time block (no seatrade row) do not share → 0.0."""
        solution = _roster_solution(
            [
                ("Ann", "Cabin1", [("1a", "Archery")]),  # block 2 = Fleet Time
                ("Bea", "Cabin1", [("1a", "Sailing")]),  # different seatrade, block 2 = Fleet Time
            ]
        )
        assert _cohesion(score(solution)).raw_value == 0.0

    def test_same_seatrade_different_block_does_not_count(self):
        """Same seatrade in different blocks is not the same session → 0.0."""
        solution = _roster_solution(
            [
                ("Ann", "Cabin1", [("1a", "Archery")]),
                ("Bea", "Cabin1", [("2b", "Archery")]),
            ]
        )
        assert _cohesion(score(solution)).raw_value == 0.0


class TestCohesionAnchors:
    def test_cohesion_metric_carries_its_anchors(self, sample_assignment_solution):
        """Cohesion ships its reference band + up-is-good orientation."""
        cohesion = _cohesion(score(sample_assignment_solution))
        assert cohesion.low_anchor == COHESION_LOW_ANCHOR
        assert cohesion.high_anchor == COHESION_HIGH_ANCHOR
        assert cohesion.higher_is_better is True


class TestCohesionDetail:
    def test_one_row_per_camper_with_cohort_size(self):
        """detail is per-camper: solo camper → cohort_size 1, shared camper → 2."""
        solution = _roster_solution(
            [
                ("Ann", "Cabin1", [("1a", "Archery")]),
                ("Bea", "Cabin1", [("1a", "Archery")]),
                ("Cy", "Cabin2", [("1a", "Sailing")]),
            ]
        )
        detail = _cohesion(score(solution)).detail
        assert len(detail) == 3
        sizes = dict(zip(detail["camper"], detail["cohort_size"], strict=True))
        assert sizes == {"Ann": 2, "Bea": 2, "Cy": 1}


class TestSparsityRawValue:
    def test_counts_every_running_session(self, sample_assignment_solution):
        """Fixture runs all 6 (block, seatrade) sessions (each has ≥1 camper) → count 6."""
        assert _sparsity(score(sample_assignment_solution)).raw_value == 6.0

    def test_empty_session_does_not_count(self):
        """A seatrade with 0 campers in a block is not running. One camper touches only 2 of
        the 8 (block, seatrade) columns → count 2, the other 6 empty columns don't count."""
        solution = _one_camper_solution(prefs=["A", "B", "C", "D"], assigned=("A", "C"))
        assert _sparsity(score(solution)).raw_value == 2.0

    def test_counts_across_all_blocks(self):
        """The same seatrade running in two different blocks is two running sessions."""
        solution = _roster_solution(
            [
                ("Ann", "Cabin1", [("1a", "Archery")]),
                ("Bea", "Cabin1", [("2b", "Archery")]),
            ]
        )
        assert _sparsity(score(solution)).raw_value == 2.0


class TestSparsityAnchors:
    def test_sparsity_metric_carries_its_anchors_flipped(self, sample_assignment_solution):
        """Sparsity ships its reference band and is down-is-bad (fewer seatrades = better)."""
        sparsity = _sparsity(score(sample_assignment_solution))
        assert sparsity.low_anchor == SPARSITY_LOW_ANCHOR
        assert sparsity.high_anchor == SPARSITY_HIGH_ANCHOR
        assert sparsity.higher_is_better is False


class TestSparsityDetail:
    def test_one_row_per_running_session_with_block(self):
        """detail is per running session so the countplot can tally per block:
        two 1a sessions + one 2b session → 3 rows carrying their block."""
        solution = _roster_solution(
            [
                ("Ann", "Cabin1", [("1a", "Archery")]),
                ("Bea", "Cabin1", [("1a", "Sailing")]),
                ("Cy", "Cabin2", [("2b", "Archery")]),
            ]
        )
        detail = _sparsity(score(solution)).detail
        assert len(detail) == 3
        assert sorted(detail["block"]) == ["1a", "1a", "2b"]


class TestScore:
    def test_returns_scorecard_with_preference_metric_and_optimality(self, sample_assignment_solution):
        """score() yields a Scorecard: the Preference metric plus the pass-through optimality."""
        solution = dataclasses.replace(
            sample_assignment_solution,
            status=SolverStatus(state=SolverState.OPTIMAL, gap=0.02),
        )

        card = score(solution)

        assert isinstance(card, Scorecard)
        assert card.optimality == solution.status.optimality  # 1 - 0.02
        metric_names = [metric.name for metric in card.metrics]
        assert "Preference" in metric_names

    def test_preference_metric_carries_its_anchors(self, sample_assignment_solution):
        """The Preference metric ships its reference band + orientation, not just the raw value."""
        preference = _preference(score(sample_assignment_solution))

        assert preference.low_anchor == PREFERENCE_LOW_ANCHOR
        assert preference.high_anchor == PREFERENCE_HIGH_ANCHOR
        assert preference.higher_is_better is True


class TestScorecardMetric:
    def test_metric_looks_up_by_name(self, sample_assignment_solution):
        """Scorecard.metric returns the metric with a matching name."""
        card = score(sample_assignment_solution)
        assert card.metric("Preference").name == "Preference"

    def test_metric_raises_for_unknown_name(self, sample_assignment_solution):
        """An unknown metric name is a KeyError, not a silent None."""
        card = score(sample_assignment_solution)
        with pytest.raises(KeyError):
            card.metric("Nonexistent")


class TestPreferenceRawValue:
    def test_matches_hand_computed_fraction(self, sample_assignment_solution):
        """Fraction of campers with CPR ≤ 4. Fixture CPRs: Alice 1+2=3, Bob 3+1=4,
        Carol 3+2=5, Dave 1+2=3 → 3 of 4 good → 0.75."""
        card = score(sample_assignment_solution)
        assert _preference(card).raw_value == 0.75

    def test_cpr_boundary_one_plus_three_is_good(self):
        """1+3 = CPR 4 counts as good (fraction 1.0)."""
        solution = _one_camper_solution(prefs=["A", "B", "C", "D"], assigned=("A", "C"))
        assert _preference(score(solution)).raw_value == 1.0

    def test_cpr_boundary_one_plus_four_is_bad(self):
        """1+4 = CPR 5 counts as bad (fraction 0.0) — the intentional quirk."""
        solution = _one_camper_solution(prefs=["A", "B", "C", "D"], assigned=("A", "D"))
        assert _preference(score(solution)).raw_value == 0.0


class TestPreferenceDetail:
    def test_one_row_per_camper_with_cpr(self, sample_assignment_solution):
        """detail is per-camper: 4 campers → 4 rows, each carrying its CPR."""
        detail = _preference(score(sample_assignment_solution)).detail
        assert len(detail) == 4
        assert set(detail["cpr"]) == {3, 4, 5}

    def test_cpr_five_carries_its_cause_split(self, sample_assignment_solution):
        """The CPR-5 camper (Carol, 3+2) is tagged with its cause so the bar can split 1+4 vs 2+3."""
        detail = _preference(score(sample_assignment_solution)).detail
        cpr5 = detail[detail["cpr"] == 5]
        assert list(cpr5["cause"]) == ["2+3"]

    def test_cause_is_min_plus_max_of_the_two_ranks(self):
        """A camper who got #1 and #4 is tagged '1+4'."""
        solution = _one_camper_solution(prefs=["A", "B", "C", "D"], assigned=("A", "D"))
        detail = _preference(score(solution)).detail
        assert list(detail["cause"]) == ["1+4"]
