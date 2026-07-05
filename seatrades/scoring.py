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

    def metric(self, name: str) -> QualityMetric:
        """The Quality Metric with this name; raises KeyError if there is none."""
        for metric in self.metrics:
            if metric.name == name:
                return metric
        raise KeyError(f"No Quality Metric named {name!r}")


def score(solution: AssignmentSolution) -> Scorecard:
    """Measure a solved schedule's goodness. Deterministic: one solution in, one Scorecard out."""
    longform = wrangle_assignments_to_longform(solution)
    return Scorecard(
        metrics=[
            _preference_metric(longform),
            _cohesion_metric(longform),
            _sparsity_metric(longform),
            _age_spread_metric(longform),
            _fairness_within_metric(longform),
            _fairness_between_metric(longform),
        ],
        optimality=solution.status.optimality,
    )


# Preference reference band — placeholder anchors, calibrated later in the
# anchor-calibration slice against real mock-data distributions.
PREFERENCE_LOW_ANCHOR = 0.6
PREFERENCE_HIGH_ANCHOR = 0.95

# A "good" schedule is CPR ≤ 4; bad is CPR ≥ 5. Exact complements.
# Quirk: CPR ≤ 4 is only reachable as 1+2 or 1+3, so "good" ⇔ the camper got their #1
# pick in one block. 1+4 (got your #1 *and* your #4) sums to CPR 5 = bad — intentional,
# not an off-by-one.
GOOD_CPR_MAX = 4


def _camper_cprs(longform: pd.DataFrame) -> pd.DataFrame:
    """Combined Preference Rank per camper: sum of their two assigned block ranks.

    One row per camper (keyed by cabin+camper, since names alone can collide) with
    ``cpr`` (3–6). Assigned rows carry a 1–4 preference by the top-2 guarantee and
    the preference-only constraint, so the two-block sum lands in 3–6.
    """
    assigned = longform[longform["assignment"] == 1.0]
    grouped = assigned.groupby(["cabin", "camper"], sort=False)["preference"]
    detail = grouped.agg(cpr="sum", ranks=list).reset_index()
    detail["cause"] = detail["ranks"].map(lambda ranks: f"{min(ranks)}+{max(ranks)}")
    return detail.drop(columns="ranks")


# Cohesion reference band — placeholder anchors, calibrated later in the
# anchor-calibration slice against real mock-data distributions.
COHESION_LOW_ANCHOR = 0.5
COHESION_HIGH_ANCHOR = 0.9

# A camper "shares" if their largest same-cabin cohort in any one session is ≥ 2 (self + a
# cabinmate). Solo (self only) is cohort size 1.
SHARED_COHORT_MIN = 2


def _cabin_cohorts(longform: pd.DataFrame) -> pd.DataFrame:
    """Largest same-cabin cohort size per camper across their seatrade sessions.

    One row per camper (keyed by cabin+camper, since names alone can collide) with
    ``cohort_size`` = the most same-cabin campers sharing any one of the camper's
    ``(block, seatrade)`` sessions, counting the camper themselves (solo → 1). Only
    assigned seatrade rows appear in ``longform``, so Fleet Time co-presence never
    counts — it is not a seatrade session.
    """
    assigned = longform[longform["assignment"] == 1.0]
    session_cohort = assigned.groupby(["block", "seatrade", "cabin"], sort=False)["camper"].transform("size")
    per_session = assigned.assign(cohort_size=session_cohort)
    detail = per_session.groupby(["cabin", "camper"], sort=False)["cohort_size"].max().reset_index()
    return detail


def _cohesion_metric(longform: pd.DataFrame) -> QualityMetric:
    """The Cohesion metric — "how many campers are with a cabinmate?"."""
    cohorts = _cabin_cohorts(longform)
    fraction_shared = (cohorts["cohort_size"] >= SHARED_COHORT_MIN).mean()
    return QualityMetric(
        name="Cohesion",
        raw_value=float(fraction_shared),
        low_anchor=COHESION_LOW_ANCHOR,
        high_anchor=COHESION_HIGH_ANCHOR,
        higher_is_better=True,
        detail=cohorts,
    )


# Sparsity reference band — placeholder anchors, calibrated later in the
# anchor-calibration slice against real mock-data distributions. Down-is-bad: fewer
# running seatrades is better. (The raw count's own ceiling is the catalog —
# seatrades × 4 blocks — which is where a calibrated high_anchor would come from.)
SPARSITY_LOW_ANCHOR = 8.0
SPARSITY_HIGH_ANCHOR = 24.0


def _running_seatrades(longform: pd.DataFrame) -> pd.DataFrame:
    """The running seatrade sessions: one row per ``(block, seatrade)`` with ≥ 1 camper.

    A session runs when at least one camper is assigned to it, so an empty seatrade (0
    campers in that block) never appears. Only assigned seatrade rows are in ``longform``,
    so Fleet Time is not a session here. One row per running session lets the detail
    countplot tally them per block.
    """
    assigned = longform[longform["assignment"] == 1.0]
    return assigned[["block", "seatrade"]].drop_duplicates().reset_index(drop=True)


def _sparsity_metric(longform: pd.DataFrame) -> QualityMetric:
    """The Sparsity metric — "how few seatrades do we have to staff?".

    Raw value is the count of running seatrades across all four blocks — the thing being
    measured, so it stays a raw count (not a rate). Fewer is better → down-is-bad.
    """
    running = _running_seatrades(longform)
    return QualityMetric(
        name="Sparsity",
        raw_value=float(len(running)),
        low_anchor=SPARSITY_LOW_ANCHOR,
        high_anchor=SPARSITY_HIGH_ANCHOR,
        higher_is_better=False,
        detail=running,
    )


# Age Spread reference band — placeholder anchors, calibrated later in the
# anchor-calibration slice against real mock-data distributions. Down-is-bad: a
# tighter age range per seatrade is better. Units are years.
AGE_SPREAD_LOW_ANCHOR = 1.0
AGE_SPREAD_HIGH_ANCHOR = 4.0


def _running_session_age_spreads(longform: pd.DataFrame) -> pd.DataFrame:
    """The age range (``maxAge − minAge``) of each running seatrade session.

    One row per ``(block, seatrade)`` with ≥ 1 camper, carrying its ``spread``. Only
    assigned seatrade rows are in ``longform``, so Fleet Time is not a session here.
    A single-camper session has ``spread`` 0 (max == min).
    """
    assigned = longform[longform["assignment"] == 1.0]
    grouped = assigned.groupby(["block", "seatrade"], sort=False)["age"]
    spreads = (grouped.max() - grouped.min()).rename("spread")
    return spreads.reset_index()


def _age_spread_metric(longform: pd.DataFrame) -> QualityMetric:
    """The Age Spread metric — "how age-homogeneous are the seatrades?".

    Raw value is the session-weighted mean age range over running seatrade sessions —
    each running seatrade contributes its range equally, regardless of camper count.
    Narrower is better → down-is-bad.
    """
    spreads = _running_session_age_spreads(longform)
    return QualityMetric(
        name="Age spread",
        raw_value=float(spreads["spread"].mean()),
        low_anchor=AGE_SPREAD_LOW_ANCHOR,
        high_anchor=AGE_SPREAD_HIGH_ANCHOR,
        higher_is_better=False,
        detail=spreads,
    )


def _preference_metric(longform: pd.DataFrame) -> QualityMetric:
    """The Preference metric — "how many campers got a good schedule?"."""
    cprs = _camper_cprs(longform)
    fraction_good = (cprs["cpr"] <= GOOD_CPR_MAX).mean()
    return QualityMetric(
        name="Preference",
        raw_value=float(fraction_good),
        low_anchor=PREFERENCE_LOW_ANCHOR,
        high_anchor=PREFERENCE_HIGH_ANCHOR,
        higher_is_better=True,
        detail=cprs,
    )


# Fairness Within Cabins reference band — placeholder anchors, need empirical tuning
# more than the other metrics (per the PRD). Down-is-bad: a tighter within-cabin CPR
# spread is fairer. Units are CPR std (population, ddof=0).
FAIRNESS_WITHIN_LOW_ANCHOR = 0.0
FAIRNESS_WITHIN_HIGH_ANCHOR = 1.0


def _within_cabin_cpr_spreads(longform: pd.DataFrame) -> pd.DataFrame:
    """The within-cabin CPR spread of each cabin: one row per cabin with its ``spread``.

    ``spread`` is the population standard deviation (``ddof=0``) of that cabin's
    campers' CPRs — population, not sample, std so a 1-camper cabin is 0, not NaN.
    """
    cprs = _camper_cprs(longform)
    spreads = cprs.groupby("cabin", sort=False)["cpr"].std(ddof=0).rename("spread")
    return spreads.reset_index()


def _fairness_within_metric(longform: pd.DataFrame) -> QualityMetric:
    """The Fairness Within Cabins metric — "inside a cabin, are schedules equally good?".

    Raw value is the within-cabin CPR std, averaged across cabins. Chosen std (outlier-
    sensitive) over variance (wrong units) or range (too coarse): one camper with a much
    worse schedule than their bunkmates should show up. Tighter is better → down-is-bad.
    """
    spreads = _within_cabin_cpr_spreads(longform)
    return QualityMetric(
        name="Fair within",
        raw_value=float(spreads["spread"].mean()),
        low_anchor=FAIRNESS_WITHIN_LOW_ANCHOR,
        high_anchor=FAIRNESS_WITHIN_HIGH_ANCHOR,
        higher_is_better=False,
        detail=spreads,
    )


# Fairness Between Cabins reference band — placeholder anchors, need empirical tuning
# more than the other metrics (per the PRD). Down-is-bad: a tighter spread of cabin
# mean-CPRs is fairer. Units are CPR std (population, ddof=0).
FAIRNESS_BETWEEN_LOW_ANCHOR = 0.0
FAIRNESS_BETWEEN_HIGH_ANCHOR = 1.0


def _cabin_mean_cprs(longform: pd.DataFrame) -> pd.DataFrame:
    """The mean CPR of each cabin: one row per cabin with its ``mean_cpr``.

    Mean, not sum, so a cabin is not penalized merely for having an extra camper.
    """
    cprs = _camper_cprs(longform)
    means = cprs.groupby("cabin", sort=False)["cpr"].mean().rename("mean_cpr")
    return means.reset_index()


def _fairness_between_metric(longform: pd.DataFrame) -> QualityMetric:
    """The Fairness Between Cabins metric — "across cabins, is any cabin treated worse?".

    Raw value is the population std (``ddof=0``) of the cabin mean-CPRs across cabins —
    a 1-cabin roster is 0, not NaN. Tighter is better → down-is-bad.
    """
    means = _cabin_mean_cprs(longform)
    return QualityMetric(
        name="Fair between",
        raw_value=float(means["mean_cpr"].std(ddof=0)),
        low_anchor=FAIRNESS_BETWEEN_LOW_ANCHOR,
        high_anchor=FAIRNESS_BETWEEN_HIGH_ANCHOR,
        higher_is_better=False,
        detail=means,
    )
