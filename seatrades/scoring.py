"""Post-hoc Scoring: measure a schedule's *goodness* from an AssignmentSolution.

Pure service layer — no Streamlit, no normalization. Distinct from the solver's
*Objective* (what CBC optimizes) and *Optimality* (the solver gap). See CONTEXT.md
"Scoring". Normalization to a shared 0–100 axis is a render-time concern and lives
in visualization.py, never here.
"""

from dataclasses import dataclass

import pandas as pd

from seatrades.results import AssignmentSolution, wrangle_assignments_to_longform


@dataclass
class QualityMetric:
    """One axis of schedule goodness, framed up-is-good.

    ``raw_value`` is the metric's rollup in its natural units; ``detail`` carries
    exactly what that metric's drill-down chart needs. ``low_anchor``/``high_anchor``
    are a curated reference band (domain knowledge, not theoretical best/worst).
    """

    name: str
    raw_value: float
    low_anchor: float
    high_anchor: float
    higher_is_better: bool
    detail: pd.DataFrame


@dataclass
class Scorecard:
    """The suite of Quality Metrics plus the pass-through solver optimality."""

    metrics: list[QualityMetric]
    optimality: float


def score(solution: AssignmentSolution) -> Scorecard:
    """Measure a solved schedule's goodness. Deterministic: one solution in, one Scorecard out."""
    return Scorecard(
        metrics=[_preference_metric(solution)],
        optimality=solution.status.optimality,
    )


# Preference reference band — placeholder anchors, calibrated later in the
# anchor-calibration slice against real mock-data distributions.
PREFERENCE_LOW_ANCHOR = 0.6
PREFERENCE_HIGH_ANCHOR = 0.95

# A "good" schedule is CPR ≤ 4; bad is CPR ≥ 5. Exact complements.
GOOD_CPR_MAX = 4


def _camper_cprs(solution: AssignmentSolution) -> pd.DataFrame:
    """Combined Preference Rank per camper: sum of their two assigned block ranks.

    One row per camper (keyed by cabin+camper, since names alone can collide) with
    ``cpr`` (3–6). Assigned rows carry a 1–4 preference by the top-2 guarantee and
    the preference-only constraint, so the two-block sum lands in 3–6.
    """
    longform = wrangle_assignments_to_longform(solution)
    assigned = longform[longform["assignment"] == 1.0]
    grouped = assigned.groupby(["cabin", "camper"], sort=False)["preference"]
    detail = grouped.agg(cpr="sum", ranks=list).reset_index()
    detail["cause"] = detail["ranks"].map(lambda ranks: f"{min(ranks)}+{max(ranks)}")
    return detail.drop(columns="ranks")


def _preference_metric(solution: AssignmentSolution) -> QualityMetric:
    """The Preference metric — "how many campers got a good schedule?"."""
    cprs = _camper_cprs(solution)
    fraction_good = (cprs["cpr"] <= GOOD_CPR_MAX).mean()
    return QualityMetric(
        name="Preference",
        raw_value=float(fraction_good),
        low_anchor=PREFERENCE_LOW_ANCHOR,
        high_anchor=PREFERENCE_HIGH_ANCHOR,
        higher_is_better=True,
        detail=cprs,
    )
