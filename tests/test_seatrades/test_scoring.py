"""Tests for seatrades/scoring.py — post-hoc schedule goodness measurement."""

import dataclasses

import pandas as pd

from seatrades.results import AssignmentSolution, SolverState, SolverStatus
from seatrades.scoring import Scorecard, score


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


def _preference(card: Scorecard):
    return next(metric for metric in card.metrics if metric.name == "Preference")


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
