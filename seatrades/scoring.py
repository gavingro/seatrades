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
    """Measure a solved schedule's goodness. Deterministic: one solution in, one Scorecard out.

    Scoring measures only *assigned* seatrade rows, so the assigned-rows filter is applied
    once here and the per-metric helpers take the already-assigned frame as a precondition
    (empty seatrade cells / Fleet Time never carry an ``assignment == 1.0`` row). Sparsity is
    the one exception: it needs the *full* catalog×blocks grid — including the un-run slots —
    to score staffed sessions as a fraction of the possible, so it takes the unfiltered longform.
    """
    longform = wrangle_assignments_to_longform(solution)
    assigned = longform[longform["assignment"] == 1.0]
    return Scorecard(
        metrics=[
            _preference_metric(assigned),
            _cohesion_metric(assigned),
            _sparsity_metric(longform),
            _age_spread_metric(assigned),
            _fairness_within_metric(assigned),
            _fairness_between_metric(assigned),
            _cabin_variety_metric(assigned),
        ],
        optimality=solution.status.optimality,
    )


# ─── Anchor calibration (issue #97) ──────────────────────────────────────────────
# The reference bands below were calibrated on 2026-07-05 against real CBC solves of the
# simulated mock scenario (seatrades/simulation.py) with the 17-seatrade catalog, swept
# across optimization configs and RNG seeds at several roster scales. Exception: the Cohesion
# band was re-derived on 2026-07-06 when the #99 review tightened that metric — see its own note.
#
# A band [low_anchor, high_anchor] is the *expected/normal* raw range, roughly the p10–p90 of the
# observed distribution — not a theoretical best/worst — except where a metric has a natural
# ceiling, in which case that anchor sits at the ceiling: Sparsity's high_anchor is the staffing
# ceiling — every catalog slot run = 1.0. A genuine outlier still falls outside the
# band by design; see each metric's per-metric note. visualization.normalize_to_band uses the band
# as the default axis domain and a floor on axis
# width, expanding only to swallow a genuinely outlying scenario. Anchors are always in raw units
# with low < high; higher_is_better handles the up/down flip at render time.
#
# Scale note: Preference and the two Fairness σ metrics are roster-portable — bands come from the
# full sweep and were cross-checked to hold at large scale. Cohesion and Sparsity are also fractions:
# Cohesion's band was re-derived from seeded 8-cabin solves only (see its note), not the full cross-
# scale sweep, and Sparsity (running ÷ catalog×blocks, ceiling 1.0) is now catalog-portable but its
# floor was carried over from the old roster-DEPENDENT count band (the 8-cabin demo end). Age spread
# (absolute years) stays roster-DEPENDENT, its band spanning the normal operating range observed
# across ~8–18 cabins (~80–200 campers), with genuine outliers still falling past the anchors. NB: the
# ~22-cabin deployment target
# is *provably infeasible* in the current model with a 17-seatrade catalog (CBC: "Problem is
# infeasible"; the model reliably schedules only ~8–10 real cabins, and even ~12–18 cabins
# solve only for gender-balanced rosters), so the largest feasible solves are the closest
# real-scale proxy for the two roster-dependent bands.
# ─────────────────────────────────────────────────────────────────────────────────

# Preference — fraction of campers with a good schedule (CPR ≤ 4). Observed ~0.38–0.97
# across the sweep (default-config runs cluster ~0.73–0.94); band brackets the normal range,
# and a near-perfect or badly-compromised roster extends past the anchors.
PREFERENCE_LOW_ANCHOR = 0.55
PREFERENCE_HIGH_ANCHOR = 0.95

# A "good" schedule is CPR ≤ 4; bad is CPR ≥ 5. Exact complements.
# Quirk: CPR ≤ 4 is only reachable as 1+2 or 1+3, so "good" ⇔ the camper got their #1
# pick in one block. 1+4 (got your #1 *and* your #4) sums to CPR 5 = bad — intentional,
# not an off-by-one.
GOOD_CPR_MAX = 4


def _camper_cprs(assigned: pd.DataFrame) -> pd.DataFrame:
    """Combined Preference Rank per camper: sum of their two assigned block ranks.

    One row per camper (keyed by cabin+camper, since names alone can collide) with
    ``cpr`` (3–6). Assigned rows carry a 1–4 preference by the top-2 guarantee and
    the preference-only constraint, so the two-block sum lands in 3–6.
    """
    grouped = assigned.groupby(["cabin", "camper"], sort=False)["preference_rank"]
    detail = grouped.agg(cpr="sum", ranks=list).reset_index()
    detail["cause"] = detail["ranks"].map(lambda ranks: f"{min(ranks)}+{max(ranks)}")
    return detail.drop(columns="ranks")


# Cohesion — fraction of camper×session slots that are *shared* (same-cabin cohort ≥ 2, i.e. the
# camper has a cabinmate in that session). This is the same camper×session grain the detail
# histogram plots, so one solo session counts once, not as a whole stranded camper. Re-derived
# 2026-07-09 against seeded 8-cabin mock solves under the cabin-variety-on default
# (cabin_variety_weight=3, issue #108), which spreads cabins across seatrades and so runs cohesion
# a touch lower than before: the solvable seeds landed ~0.64–0.82 (seed 0 = 0.64), down from
# ~0.69–0.83 when variety was off. Band brackets that normal range; a fully-cohesive roster (every
# session shared → 1.0) expands past the high anchor rather than pinning there.
COHESION_LOW_ANCHOR = 0.60
COHESION_HIGH_ANCHOR = 0.85

# A camper "shares" a session if their same-cabin cohort there is ≥ 2 (self + a cabinmate).
# Solo (self only) is cohort size 1.
SHARED_COHORT_MIN = 2


def _cabin_session_cohorts(assigned: pd.DataFrame) -> pd.DataFrame:
    """Same-cabin cohort size for each camper in each of their seatrade sessions.

    One row per ``(camper, session)`` — camper keyed by cabin+camper since names alone can
    collide — carrying ``block``, ``seatrade`` and ``cohort_size`` = the number of same-cabin
    campers sharing that one ``(block, seatrade)`` session, counting the camper themselves
    (solo → 1). Roughly two rows per camper (one per seatrade block). Only assigned seatrade
    rows are present, so Fleet Time co-presence never counts — it is not a seatrade session.
    This is the camper×session grain the Cohesion detail histogram plots.
    """
    session_cohort = assigned.groupby(["block", "seatrade", "cabin"], sort=False)["camper"].transform("size")
    per_session = assigned.assign(cohort_size=session_cohort)
    return per_session[["cabin", "camper", "block", "seatrade", "cohort_size"]].reset_index(drop=True)


def _cohesion_metric(assigned: pd.DataFrame) -> QualityMetric:
    """The Cohesion metric — "how often is a camper with a cabinmate in a session?".

    Rollup is the fraction of camper×session slots that are *shared*: a slot counts as cohesive
    when the camper's same-cabin cohort there is ≥ 2 (self + a cabinmate). This is the same
    camper×session grain the detail histogram plots, so the rollup and the drill-down count the
    same thing — one solo session is one stranding, not a whole stranded camper.
    """
    session_cohorts = _cabin_session_cohorts(assigned)
    fraction_cohesive = (session_cohorts["cohort_size"] >= SHARED_COHORT_MIN).mean()
    return QualityMetric(
        name="Cohesion",
        raw_value=float(fraction_cohesive),
        low_anchor=COHESION_LOW_ANCHOR,
        high_anchor=COHESION_HIGH_ANCHOR,
        higher_is_better=True,
        detail=session_cohorts,
    )


# Sparsity — fraction of the catalog×blocks grid that runs (down-is-bad: fewer is better).
# Numerator = running sessions, denominator = distinct seatrades × 4 blocks (mock: 17 × 4 = 68),
# so the metric is catalog- and roster-portable. high_anchor is the ceiling — every possible slot
# staffed = 1.0. low_anchor 0.44 (= the old 30-session floor ÷ 68) keeps the 8-cabin demo inside
# the band rather than pinned at a misleading 100%; large rosters sit toward the busy end. Seeded
# 8-cabin mock solves ran ~0.50–0.65 (seed 0 = 0.56). Dividing the old raw-count anchors (30, 68)
# by the 68-slot grid leaves the normalized position unchanged — this is a units change, not a
# recalibration.
SPARSITY_LOW_ANCHOR = 0.44
SPARSITY_HIGH_ANCHOR = 1.0


def _catalog_sessions(longform: pd.DataFrame) -> pd.DataFrame:
    """Every ``(block, seatrade)`` slot in the catalog×blocks grid, flagged run-or-not.

    One row per ``(block, seatrade)`` column of the assignment matrix — the *full* grid of
    every catalog seatrade in every block, so ``len`` is the total possible sessions (the
    Sparsity denominator: distinct seatrades × blocks). ``assigned`` is True when ≥ 1 camper
    is in that slot (a running session) and False for the un-run remainder. Takes the unfiltered
    longform, not the assigned frame, precisely so the un-run slots survive. The detail countplot
    stacks these per block so a Captain sees which seatrades run in which block.
    """
    grid = longform.groupby(["block", "seatrade"], sort=False)["assignment"].max().reset_index()
    grid["assigned"] = grid["assignment"] == 1.0
    return grid[["block", "seatrade", "assigned"]]


def _sparsity_metric(longform: pd.DataFrame) -> QualityMetric:
    """The Sparsity metric — "how few of the possible seatrades do we have to staff?".

    Raw value is the fraction of the catalog×blocks grid that runs: running sessions ÷ total
    possible (distinct seatrades × blocks). A fraction, not a raw count, so it is portable across
    catalogs and rosters. Fewer running seatrades is better → down-is-bad.
    """
    sessions = _catalog_sessions(longform)
    fraction_running = sessions["assigned"].mean()
    return QualityMetric(
        name="Sparsity",
        raw_value=float(fraction_running),
        low_anchor=SPARSITY_LOW_ANCHOR,
        high_anchor=SPARSITY_HIGH_ANCHOR,
        higher_is_better=False,
        detail=sessions,
    )


# Age Spread — session-weighted mean age range in years (down-is-bad: tighter is better).
# Observed ~1.46–2.5 across the seeded sweep under the cabin-variety-on default
# (cabin_variety_weight=3, issue #108); large rosters sit ~2.4 (fuller sessions widen ranges —
# the intended trade-off with Sparsity). Low anchor lowered 1.5 → 1.4 on 2026-07-09 to keep
# bracketing the best seeds after variety pressure nudged the minimum down. Band brackets the
# normal range; a very homogeneous or very mixed camp extends past the anchors.
AGE_SPREAD_LOW_ANCHOR = 1.4
AGE_SPREAD_HIGH_ANCHOR = 2.5


def _running_session_age_spreads(assigned: pd.DataFrame) -> pd.DataFrame:
    """The age range (``maxAge − minAge``) of each running seatrade session.

    One row per ``(block, seatrade)`` with ≥ 1 camper, carrying its ``spread``. Only assigned
    seatrade rows are present, so Fleet Time is not a session here. ``spread`` is a *difference*
    in whole years: a single-age session (everyone the same age) is 0; a session with 16- and
    17-year-olds is 1 (not 2).
    """
    grouped = assigned.groupby(["block", "seatrade"], sort=False)["age"]
    spreads = (grouped.max() - grouped.min()).rename("spread")
    return spreads.reset_index()


def _age_spread_metric(assigned: pd.DataFrame) -> QualityMetric:
    """The Age Spread metric — "how age-homogeneous are the seatrades?".

    Raw value is the session-weighted mean age range over running seatrade sessions —
    each running seatrade contributes its range equally, regardless of camper count.
    Narrower is better → down-is-bad.
    """
    spreads = _running_session_age_spreads(assigned)
    return QualityMetric(
        name="Age spread",
        raw_value=float(spreads["spread"].mean()),
        low_anchor=AGE_SPREAD_LOW_ANCHOR,
        high_anchor=AGE_SPREAD_HIGH_ANCHOR,
        higher_is_better=False,
        detail=spreads,
    )


def _preference_metric(assigned: pd.DataFrame) -> QualityMetric:
    """The Preference metric — "how many campers got a good schedule?"."""
    cprs = _camper_cprs(assigned)
    fraction_good = (cprs["cpr"] <= GOOD_CPR_MAX).mean()
    return QualityMetric(
        name="Preference",
        raw_value=float(fraction_good),
        low_anchor=PREFERENCE_LOW_ANCHOR,
        high_anchor=PREFERENCE_HIGH_ANCHOR,
        higher_is_better=True,
        detail=cprs,
    )


# Fairness Within Cabins — mean within-cabin CPR σ (down-is-bad: tighter is fairer).
# Observed ~0.3–1.0 across the sweep (a cabin with identical CPRs → 0 is rare, as is >1.0).
# Band spans that normal range; 1.0 is a natural upper anchor for σ over the 4 CPR values.
FAIRNESS_WITHIN_LOW_ANCHOR = 0.3
FAIRNESS_WITHIN_HIGH_ANCHOR = 1.0


def _within_cabin_cpr_spreads(assigned: pd.DataFrame) -> pd.DataFrame:
    """The within-cabin CPR spread of each cabin: one row per cabin with its ``spread``.

    ``spread`` is the population standard deviation (``ddof=0``) of that cabin's
    campers' CPRs — population, not sample, std so a 1-camper cabin is 0, not NaN.
    """
    cprs = _camper_cprs(assigned)
    spreads = cprs.groupby("cabin", sort=False)["cpr"].std(ddof=0).rename("spread")
    return spreads.reset_index()


def _fairness_within_metric(assigned: pd.DataFrame) -> QualityMetric:
    """The Fairness Within Cabins metric — "inside a cabin, are schedules equally good?".

    Raw value is the within-cabin CPR std, averaged across cabins. Chosen std (outlier-
    sensitive) over variance (wrong units) or range (too coarse): one camper with a much
    worse schedule than their bunkmates should show up. Tighter is better → down-is-bad.
    """
    spreads = _within_cabin_cpr_spreads(assigned)
    return QualityMetric(
        name="Fair within",
        raw_value=float(spreads["spread"].mean()),
        low_anchor=FAIRNESS_WITHIN_LOW_ANCHOR,
        high_anchor=FAIRNESS_WITHIN_HIGH_ANCHOR,
        higher_is_better=False,
        detail=spreads,
    )


# Fairness Between Cabins — σ of cabin mean-CPRs (down-is-bad: tighter is fairer). Runs small
# and tight (observed ~0.09–0.32): cabin means cluster near the camp mean, so real spread is a
# fifth of the old 0–1 placeholder. Band brackets the observed normal range.
FAIRNESS_BETWEEN_LOW_ANCHOR = 0.1
FAIRNESS_BETWEEN_HIGH_ANCHOR = 0.35


def _cabin_mean_cprs(assigned: pd.DataFrame) -> pd.DataFrame:
    """The mean CPR of each cabin: one row per cabin with its ``mean_cpr``.

    Mean, not sum, so a cabin is not penalized merely for having an extra camper.
    """
    cprs = _camper_cprs(assigned)
    means = cprs.groupby("cabin", sort=False)["cpr"].mean().rename("mean_cpr")
    return means.reset_index()


def _fairness_between_metric(assigned: pd.DataFrame) -> QualityMetric:
    """The Fairness Between Cabins metric — "across cabins, is any cabin treated worse?".

    Raw value is the population std (``ddof=0``) of the cabin mean-CPRs across cabins —
    a 1-cabin roster is 0, not NaN. Tighter is better → down-is-bad.
    """
    means = _cabin_mean_cprs(assigned)
    return QualityMetric(
        name="Fair between",
        raw_value=float(means["mean_cpr"].std(ddof=0)),
        low_anchor=FAIRNESS_BETWEEN_LOW_ANCHOR,
        high_anchor=FAIRNESS_BETWEEN_HIGH_ANCHOR,
        higher_is_better=False,
        detail=means,
    )


# Cabin Variety — mean over running sessions of the largest cabin's *realized* share of the
# session (down-is-bad: less domination is better). Orthogonal to Cohesion: Cohesion asks
# "do I have a cabinmate here?" (per-camper, anti-loneliness); Cabin Variety asks "does one
# cabin dominate this session?" (per-session, anti-domination). Uses realized session size
# (honest post-hoc measure), a deliberate mismatch with the solver's capacity-based penalty
# threshold (#108) — the two still move together. Anchors calibrated 2026-07-09 against seeded
# 8-cabin mock solves under the cabin-variety-on default (cabin_variety_weight=3): the solvable
# seeds ran ~0.57–0.59 (seed 0 = 0.57). Band brackets that normal range with room to spare; a
# badly-dominated or perfectly-mixed schedule extends past the anchors.
CABIN_VARIETY_LOW_ANCHOR = 0.4
CABIN_VARIETY_HIGH_ANCHOR = 0.7


def _session_max_cabin_shares(assigned: pd.DataFrame) -> pd.DataFrame:
    """The largest single cabin's share of each running seatrade session.

    One row per running ``(block, seatrade)`` session with ``max_share`` = the biggest cabin's
    camper count ÷ the session's realized camper count. Only assigned seatrade rows are present,
    so Fleet Time is not a session and non-running slots are excluded. A session with only one
    cabin present is fully dominated → ``1.0``; a session split evenly across ``n`` cabins →
    ``1/n``. This is the per-session grain the Cabin Variety detail histogram plots.
    """
    cabin_counts = assigned.groupby(["block", "seatrade", "cabin"], sort=False).size()
    session_sizes = assigned.groupby(["block", "seatrade"], sort=False).size()
    max_cabin_count = cabin_counts.groupby(["block", "seatrade"], sort=False).max()
    max_share = (max_cabin_count / session_sizes).rename("max_share")
    return max_share.reset_index()


def _cabin_variety_metric(assigned: pd.DataFrame) -> QualityMetric:
    """The Cabin Variety metric — "does one cabin dominate a seatrade session?".

    Raw value is the mean over running sessions of each session's max cabin share — every
    running session weighted equally, regardless of camper count. Less domination is better →
    down-is-bad; render-time ``normalize_to_band`` flips it so a well-mixed schedule reads high.
    """
    shares = _session_max_cabin_shares(assigned)
    return QualityMetric(
        name="Cabin variety",
        raw_value=float(shares["max_share"].mean()),
        low_anchor=CABIN_VARIETY_LOW_ANCHOR,
        high_anchor=CABIN_VARIETY_HIGH_ANCHOR,
        higher_is_better=False,
        detail=shares,
    )
