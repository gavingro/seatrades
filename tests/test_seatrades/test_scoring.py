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
    scenario at 8 cabins whose six metrics all sit strictly inside their bands, with room to
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
