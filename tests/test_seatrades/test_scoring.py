"""Tests for seatrades/scoring.py — post-hoc schedule goodness measurement."""

import dataclasses
import random

import numpy as np
import pandas as pd
import pulp
import pytest

from seatrades import solver
from seatrades.config import CamperSimulationConfig, OptimizationConfig, SeatradeSimulationConfig
from seatrades.preferences import join_and_validate
from seatrades.problem import SchedulingProblem
from seatrades.results import AssignmentSolution, SolverState, SolverStatus
from seatrades.scoring import (
    AGE_SPREAD_HIGH_ANCHOR,
    AGE_SPREAD_LOW_ANCHOR,
    CABIN_VARIETY_HIGH_ANCHOR,
    CABIN_VARIETY_LOW_ANCHOR,
    COHESION_HIGH_ANCHOR,
    COHESION_LOW_ANCHOR,
    FAIRNESS_BETWEEN_HIGH_ANCHOR,
    FAIRNESS_BETWEEN_LOW_ANCHOR,
    FAIRNESS_WITHIN_HIGH_ANCHOR,
    FAIRNESS_WITHIN_LOW_ANCHOR,
    PREFERENCE_HIGH_ANCHOR,
    PREFERENCE_LOW_ANCHOR,
    SPARSITY_HIGH_ANCHOR,
    SPARSITY_LOW_ANCHOR,
    Scorecard,
    score,
)
from seatrades.simulation import (
    simulate_camper_identity,
    simulate_camper_preferences,
    simulate_camper_relationships,
    simulate_seatrade_preferences,
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


# Cause pair per target CPR, both respecting the top-2 guarantee (min(r1, r2) <= 2)
# and matching the "cause" convention (min+max) used elsewhere in scoring.py.
_CPR_CAUSE = {3: (1, 2), 4: (1, 3), 5: (2, 3), 6: (2, 4)}


def _cabin_fairness_solution(entries: list[tuple[str, str, int]]) -> AssignmentSolution:
    """Build a solution from ``(name, cabin, target_cpr)`` rows.

    Each camper is given the two block ranks (block 1a, block 2b) that sum to their
    ``target_cpr`` via ``_CPR_CAUSE``, so a test can pin every camper's CPR exactly —
    which ``_roster_solution`` (CPR-blind, placeholder prefs) cannot do. Lets Fairness
    tests place chosen campers, at chosen CPRs, into chosen cabins.
    """
    prefs = ["A", "B", "C", "D"]
    columns = [f"1a_{p}" for p in prefs] + [f"2b_{p}" for p in prefs]
    camper_ids = pd.Index(range(len(entries)), name="camper_id")
    rows = []
    for _, _, cpr in entries:
        rank_1a, rank_2b = _CPR_CAUSE[cpr]
        row = {col: 0.0 for col in columns}
        row[f"1a_{prefs[rank_1a - 1]}"] = 1.0
        row[f"2b_{prefs[rank_2b - 1]}"] = 1.0
        rows.append(row)
    names = [name for name, _, _ in entries]
    cabins = [cabin for _, cabin, _ in entries]
    return AssignmentSolution(
        assignments=pd.DataFrame(rows, index=camper_ids, columns=columns),
        status=SolverStatus(state=SolverState.OPTIMAL),
        cabins=list(dict.fromkeys(cabins)),
        campers=names,
        seatrades_full=columns,
        cabin_camper_prefs=pd.DataFrame({"cabin": cabins, "age": [12] * len(entries)}, index=camper_ids),
        camper_prefs=pd.Series([prefs] * len(entries), index=camper_ids),
        camper_names=pd.Series(names, index=camper_ids),
    )


def _preference(card: Scorecard):
    return card.metric("Preference")


def _cohesion(card: Scorecard):
    return card.metric("Cohesion")


def _sparsity(card: Scorecard):
    return card.metric("Sparsity")


def _age_spread(card: Scorecard):
    return card.metric("Age spread")


def _fair_within(card: Scorecard):
    return card.metric("Fair within")


def _fair_between(card: Scorecard):
    return card.metric("Fair between")


def _cabin_variety(card: Scorecard):
    return card.metric("Cabin variety")


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

    def test_one_solo_session_counts_once_not_the_whole_camper(self):
        """Rollup is per camper×session: a camper stranded in one block only loses that session.

        Ann and Bea share both their sessions (2 shared each); Cy shares block 1a but is solo in
        2b → 1 shared, 1 solo. That is 5 shared of 6 total sessions → 5/6. Under the old per-camper
        "every session" rollup Cy's one solo block would sink his whole camper, giving 2/3.
        """
        solution = _roster_solution(
            [
                ("Ann", "Cabin1", [("1a", "Archery"), ("2b", "Sailing")]),
                ("Bea", "Cabin1", [("1a", "Archery"), ("2b", "Sailing")]),
                ("Cy", "Cabin1", [("1a", "Archery"), ("2b", "Rowing")]),
            ]
        )
        assert _cohesion(score(solution)).raw_value == pytest.approx(5 / 6)


class TestCohesionAnchors:
    def test_cohesion_metric_carries_its_anchors(self, sample_assignment_solution):
        """Cohesion ships its reference band + up-is-good orientation."""
        cohesion = _cohesion(score(sample_assignment_solution))
        assert cohesion.low_anchor == COHESION_LOW_ANCHOR
        assert cohesion.high_anchor == COHESION_HIGH_ANCHOR
        assert cohesion.higher_is_better is True


class TestCohesionDetail:
    def test_detail_is_one_row_per_camper_session(self):
        """detail is camper×session grain: each camper contributes one row per seatrade session.

        Ann and Bea have two sessions each, Cy has one → 5 rows. Each row carries that session's
        same-cabin cohort size (self counted; solo → 1), so a camper stranded in one block shows
        up as their own cohort-size-1 row rather than being hidden by their other, shared session.
        """
        solution = _roster_solution(
            [
                ("Ann", "Cabin1", [("1a", "Archery"), ("2b", "Sailing")]),
                ("Bea", "Cabin1", [("1a", "Archery"), ("2b", "Rowing")]),
                ("Cy", "Cabin2", [("1a", "Sailing")]),
            ]
        )
        detail = _cohesion(score(solution)).detail
        assert len(detail) == 5
        assert set(detail.columns) >= {"cabin", "camper", "block", "seatrade", "cohort_size"}
        # Ann is with Bea in 1a_Archery (cohort 2) but solo in 2b_Sailing (cohort 1).
        ann = detail[detail["camper"] == "Ann"]
        assert sorted(ann["cohort_size"]) == [1, 2]


class TestSparsityRawValue:
    def test_every_grid_slot_running_scores_one(self, sample_assignment_solution):
        """Fixture staffs all 6 (block, seatrade) slots in its catalog → 6/6 = 1.0."""
        assert _sparsity(score(sample_assignment_solution)).raw_value == 1.0

    def test_fraction_is_running_over_the_full_catalog_grid(self):
        """One camper touches 2 of the 4-seatrade × 2-block = 8 grid slots; the other 6 sit idle
        → 2/8. Empty slots stay in the denominator — that is the whole point of a fraction."""
        solution = _one_camper_solution(prefs=["A", "B", "C", "D"], assigned=("A", "C"))
        assert _sparsity(score(solution)).raw_value == pytest.approx(0.25)


class TestSparsityAnchors:
    def test_sparsity_metric_carries_its_anchors_flipped(self, sample_assignment_solution):
        """Sparsity ships its reference band and is down-is-bad (fewer seatrades = better)."""
        sparsity = _sparsity(score(sample_assignment_solution))
        assert sparsity.low_anchor == SPARSITY_LOW_ANCHOR
        assert sparsity.high_anchor == SPARSITY_HIGH_ANCHOR
        assert sparsity.higher_is_better is False


class TestSparsityDetail:
    def test_detail_is_the_full_grid_flagged_run_or_idle(self):
        """detail carries every (block, seatrade) slot — running and idle — so the countplot can
        stack the whole catalog per block. One camper of a 4-seatrade × 2-block catalog staffs 2
        slots → 8 rows, exactly the two staffed ones flagged assigned."""
        solution = _one_camper_solution(prefs=["A", "B", "C", "D"], assigned=("A", "C"))
        detail = _sparsity(score(solution)).detail
        assert len(detail) == 8
        assert set(detail.columns) >= {"block", "seatrade", "assigned"}
        staffed = {(row.block, row.seatrade) for row in detail[detail["assigned"]].itertuples()}
        assert staffed == {("1a", "A"), ("2b", "C")}


class TestAgeSpreadRawValue:
    def test_matches_hand_computed_session_weighted_mean(self, sample_assignment_solution):
        """Fixture ages: Alice 13, Bob 14, Carol 15, Dave 16. Per-session age range:
        1a_Archery {Alice,Dave} -> 3, 1a_Sailing {Bob} -> 0, 1a_Climbing {Carol} -> 0,
        2b_Archery {Carol} -> 0, 2b_Sailing {Alice} -> 0, 2b_Climbing {Bob,Dave} -> 2.
        Mean over the 6 running sessions (each session weighted equally, not by camper
        count) = (3+0+0+0+0+2)/6 = 5/6."""
        assert _age_spread(score(sample_assignment_solution)).raw_value == pytest.approx(5 / 6)

    def test_single_camper_sessions_have_zero_spread(self):
        """A running session with exactly one camper has age range 0 (max == min)."""
        solution = _one_camper_solution(prefs=["A", "B", "C", "D"], assigned=("A", "C"))
        assert _age_spread(score(solution)).raw_value == 0.0


class TestAgeSpreadAnchors:
    def test_age_spread_metric_carries_its_anchors_flipped(self, sample_assignment_solution):
        """Age Spread ships its reference band and is down-is-bad (narrower range = better)."""
        age_spread = _age_spread(score(sample_assignment_solution))
        assert age_spread.low_anchor == AGE_SPREAD_LOW_ANCHOR
        assert age_spread.high_anchor == AGE_SPREAD_HIGH_ANCHOR
        assert age_spread.higher_is_better is False


class TestAgeSpreadDetail:
    def test_one_row_per_running_session_with_block_and_spread(self, sample_assignment_solution):
        """detail is per running session so the countplot/tooltip can identify the
        seatrade x block with a large range: 1a_Archery (Alice 13, Dave 16) -> spread 3."""
        detail = _age_spread(score(sample_assignment_solution)).detail
        assert len(detail) == 6
        archery_1a = detail[(detail["block"] == "1a") & (detail["seatrade"] == "Archery")]
        assert list(archery_1a["spread"]) == [3]


class TestCabinVarietyRawValue:
    def test_single_cabin_session_scores_one(self):
        """A session with only one cabin present is fully dominated → max share 1.0 (worst)."""
        solution = _roster_solution(
            [
                ("Ann", "Cabin1", [("1a", "Archery")]),
                ("Bea", "Cabin1", [("1a", "Archery")]),
            ]
        )
        assert _cabin_variety(score(solution)).raw_value == 1.0

    def test_perfectly_mixed_session_scores_one_over_num_cabins(self):
        """One camper from each of 3 cabins in a session → no cabin bigger than 1/3 → 1/3."""
        solution = _roster_solution(
            [
                ("Ann", "Cabin1", [("1a", "Archery")]),
                ("Bea", "Cabin2", [("1a", "Archery")]),
                ("Cy", "Cabin3", [("1a", "Archery")]),
            ]
        )
        assert _cabin_variety(score(solution)).raw_value == pytest.approx(1 / 3)

    def test_matches_hand_computed_session_mean(self):
        """Two running sessions, each weighted equally. 1a_Archery: Cabin1 has 2 of 3 campers
        → share 2/3. 2b_Sailing: one camper each from Cabin1, Cabin2 → share 1/2. Mean over the
        two sessions = (2/3 + 1/2)/2 = 7/12."""
        solution = _roster_solution(
            [
                ("Ann", "Cabin1", [("1a", "Archery"), ("2b", "Sailing")]),
                ("Bea", "Cabin1", [("1a", "Archery")]),
                ("Cy", "Cabin2", [("1a", "Archery"), ("2b", "Sailing")]),
            ]
        )
        assert _cabin_variety(score(solution)).raw_value == pytest.approx(7 / 12)

    def test_fleet_time_blocks_are_not_sessions(self):
        """Only running seatrade sessions count. Ann is on Fleet Time in block 2 (no row there),
        so only 1a_Archery scores — a single-cabin session → 1.0, not diluted by an empty block."""
        solution = _roster_solution(
            [
                ("Ann", "Cabin1", [("1a", "Archery")]),
            ]
        )
        assert _cabin_variety(score(solution)).raw_value == 1.0


class TestCabinVarietyAnchors:
    def test_cabin_variety_metric_carries_its_anchors_flipped(self, sample_assignment_solution):
        """Cabin Variety ships its reference band and is down-is-bad (less domination = better)."""
        cabin_variety = _cabin_variety(score(sample_assignment_solution))
        assert cabin_variety.low_anchor == CABIN_VARIETY_LOW_ANCHOR
        assert cabin_variety.high_anchor == CABIN_VARIETY_HIGH_ANCHOR
        assert cabin_variety.higher_is_better is False


class TestCabinVarietyDetail:
    def test_one_row_per_running_session_with_max_share(self):
        """detail is per running session so the histogram/tooltip can name the most-dominated
        seatrade × block. Two running sessions → 2 rows; 1a_Archery (Cabin1 2 of 3) → 2/3."""
        solution = _roster_solution(
            [
                ("Ann", "Cabin1", [("1a", "Archery"), ("2b", "Sailing")]),
                ("Bea", "Cabin1", [("1a", "Archery")]),
                ("Cy", "Cabin2", [("1a", "Archery"), ("2b", "Sailing")]),
            ]
        )
        detail = _cabin_variety(score(solution)).detail
        assert len(detail) == 2
        assert set(detail.columns) >= {"block", "seatrade", "max_share"}
        archery_1a = detail[(detail["block"] == "1a") & (detail["seatrade"] == "Archery")]
        assert list(archery_1a["max_share"]) == pytest.approx([2 / 3])


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


class TestFairnessWithinRawValue:
    def test_matches_hand_computed_average_of_within_cabin_stds(self, sample_assignment_solution):
        """Fixture CPRs: Alice 3, Bob 4 (Cabin1); Carol 5, Dave 3 (Cabin2).
        Cabin1 population std([3, 4]) = 0.5; Cabin2 population std([5, 3]) = 1.0.
        Averaged across cabins = 0.75."""
        assert _fair_within(score(sample_assignment_solution)).raw_value == pytest.approx(0.75)

    def test_one_camper_cabin_has_zero_spread(self):
        """A cabin with a single camper has within-cabin std 0 (population std, not NaN)."""
        solution = _cabin_fairness_solution(
            [
                ("Ann", "Cabin1", 3),
                ("Bea", "Cabin2", 4),
            ]
        )
        assert _fair_within(score(solution)).raw_value == 0.0


class TestFairnessWithinAnchors:
    def test_fair_within_metric_carries_its_anchors_flipped(self, sample_assignment_solution):
        """Fairness Within ships its reference band and is down-is-bad (tighter = fairer)."""
        fair_within = _fair_within(score(sample_assignment_solution))
        assert fair_within.low_anchor == FAIRNESS_WITHIN_LOW_ANCHOR
        assert fair_within.high_anchor == FAIRNESS_WITHIN_HIGH_ANCHOR
        assert fair_within.higher_is_better is False


class TestFairnessWithinDetail:
    def test_one_row_per_cabin_with_spread(self, sample_assignment_solution):
        """detail is per-cabin: 2 cabins in the fixture -> 2 rows, each carrying its spread."""
        detail = _fair_within(score(sample_assignment_solution)).detail
        assert len(detail) == 2
        spreads = dict(zip(detail["cabin"], detail["spread"], strict=True))
        assert spreads == pytest.approx({"Cabin1": 0.5, "Cabin2": 1.0})


class TestFairnessBetweenRawValue:
    def test_matches_hand_computed_std_of_cabin_means(self, sample_assignment_solution):
        """Fixture cabin means: Cabin1 mean([3, 4]) = 3.5, Cabin2 mean([5, 3]) = 4.0.
        Population std([3.5, 4.0]) = 0.25."""
        assert _fair_between(score(sample_assignment_solution)).raw_value == pytest.approx(0.25)

    def test_mean_not_sum_ties_differently_sized_cabins(self):
        """PRD worked example: three cabins of sizes 3/4/3 with cabin means 4.00, 4.00, 5.33
        (cabins A and B tie at 4.00 despite different sizes, because mean -- not sum -- is
        used) -> population std([4.00, 4.00, 5.33...]) ~= 0.63."""
        solution = _cabin_fairness_solution(
            [
                ("A1", "CabinA", 4),
                ("A2", "CabinA", 4),
                ("A3", "CabinA", 4),
                ("B1", "CabinB", 3),
                ("B2", "CabinB", 3),
                ("B3", "CabinB", 5),
                ("B4", "CabinB", 5),
                ("C1", "CabinC", 6),
                ("C2", "CabinC", 6),
                ("C3", "CabinC", 4),
            ]
        )
        assert _fair_between(score(solution)).raw_value == pytest.approx(0.63, abs=1e-2)

    def test_one_cabin_roster_has_zero_spread(self):
        """A single-cabin roster has between-cabin std 0 (population std, not NaN)."""
        solution = _cabin_fairness_solution(
            [
                ("Ann", "Cabin1", 3),
                ("Bea", "Cabin1", 4),
            ]
        )
        assert _fair_between(score(solution)).raw_value == 0.0


class TestFairnessBetweenAnchors:
    def test_fair_between_metric_carries_its_anchors_flipped(self, sample_assignment_solution):
        """Fairness Between ships its reference band and is down-is-bad (tighter = fairer)."""
        fair_between = _fair_between(score(sample_assignment_solution))
        assert fair_between.low_anchor == FAIRNESS_BETWEEN_LOW_ANCHOR
        assert fair_between.high_anchor == FAIRNESS_BETWEEN_HIGH_ANCHOR
        assert fair_between.higher_is_better is False


class TestFairnessBetweenDetail:
    def test_one_row_per_cabin_with_mean_cpr(self, sample_assignment_solution):
        """detail is per-cabin: 2 cabins in the fixture -> 2 rows, each carrying its mean CPR."""
        detail = _fair_between(score(sample_assignment_solution)).detail
        assert len(detail) == 2
        means = dict(zip(detail["cabin"], detail["mean_cpr"], strict=True))
        assert means == pytest.approx({"Cabin1": 3.5, "Cabin2": 4.0})


def _solve_seeded_mock_scenario(seed: int) -> AssignmentSolution:
    """Simulate and solve one seeded mock scenario at the scale the anchors were calibrated
    against: 8 cabins (the app's demo scale and the largest roster the model schedules
    reliably) with the 17-seatrade catalog. Reseeds both RNGs so the roster is deterministic
    — the reseed is load-bearing (see the reseed gotcha in project memory).
    """
    random.seed(seed)
    np.random.seed(seed)
    seatrade_prefs = simulate_seatrade_preferences(SeatradeSimulationConfig(num_seatrades=17))
    identity = simulate_camper_identity(CamperSimulationConfig())
    camper_prefs = simulate_camper_preferences(identity, seatrade_prefs)
    relationships = simulate_camper_relationships(identity, camper_prefs)
    joined, setup, validated = join_and_validate(identity, camper_prefs, seatrade_prefs, relationships)
    problem = SchedulingProblem(joined, setup, relationships=validated)
    config = OptimizationConfig(solver=pulp.apis.PULP_CBC_CMD(msg=0, gapRel=0.10, timeLimit=120))
    return solver.run(problem, config)


@pytest.mark.slow
class TestCalibratedBandsBracketRealScenario:
    """Anchor-drift guard: on a real solve, every metric's raw value must land inside its
    calibrated [low_anchor, high_anchor]. If a later edit to the anchors, the simulation, or the
    solver pushes any metric out of band, this catches it. seed=0 is a solver-feasible mock
    scenario at 8 cabins whose seven metrics all sit strictly inside their bands, with room to
    spare — the roster-dependent Sparsity/Age-spread bands sit nearest an edge (Sparsity ~1/3 up
    from its floor), as expected. Pinned to one seed on purpose: random rosters flake INFEASIBLE
    at this scale (see the reseed gotcha in project memory), so a swept assertion would be less
    reliable, not more. (The ~22-cabin deployment target is infeasible in the current model — see
    the anchor-calibration notes in scoring.py.)
    """

    def test_every_metric_raw_value_is_within_its_reference_band(self):
        solution = _solve_seeded_mock_scenario(seed=0)
        assert solution.status.is_optimal, f"expected OPTIMAL, got {solution.status.state}"
        scorecard = score(solution)
        for metric in scorecard.metrics:
            assert metric.low_anchor <= metric.raw_value <= metric.high_anchor, (
                f"{metric.name} raw {metric.raw_value:.3f} fell outside its reference band "
                f"[{metric.low_anchor}, {metric.high_anchor}]"
            )
