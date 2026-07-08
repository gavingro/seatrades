"""Altair chart specs for seatrade assignment results."""

import altair as alt
import pandas as pd

from seatrades.blocks import block_label
from seatrades.problem import BLOCKS
from seatrades.results import (
    UNMATCHED_PREFERENCE,
    AssignmentSolution,
    SolverState,
    wrangle_assignments_to_longform,
)
from seatrades.scoring import QualityMetric, Scorecard

# User-facing labels for metric names that carry project jargon; identity for the rest. The
# internal ``metric.name`` stays the stable key (``Scorecard.metric``, ``_DETAIL_BUILDERS``); only
# the displayed string changes, so tests and dispatch never churn when copy is reworded.
METRIC_DISPLAY_LABELS = {
    "Fair within": "Within-cabin fairness",
    "Fair between": "Between-cabin fairness",
}


def metric_label(name: str) -> str:
    """The user-facing label for a metric name — de-jargoned where needed, else the name itself."""
    return METRIC_DISPLAY_LABELS.get(name, name)


def _format_raw_value(name: str, value: float) -> str:
    """A metric's raw rollup in plain units for the Overview tooltip (never the 0–100 position).

    Fractions read as a percent, Sparsity as a seatrade count, Age spread in years, the fairness
    σ's as a 2-dp spread. Keyed by metric name; the fairness σ's (and any unlisted metric) render
    as an N.NN pick-rank spread.
    """
    if name in ("Preference", "Cohesion"):
        return f"{value:.0%} of campers"
    if name == "Sparsity":
        return f"{value:.0f} seatrades"
    if name == "Age spread":
        return f"{value:.1f} yr age range"
    return f"{value:.2f} pick-rank spread"


# CPR causes ordered good (greens) → bad (reds) so the detail bars read good-vs-bad at
# a glance and the CPR-5 bar visibly splits its two causes (1+4 vs 2+3).
CPR_CAUSE_ORDER = ["1+2", "1+3", "2+2", "1+4", "2+3", "2+4"]
CPR_CAUSE_RANGE = ["#1a9850", "#66bd63", "#a6d96a", "#fc8d59", "#f46d43", "#d73027"]

# Satisfaction scale: top choice (green) → low/unranked (red). "Unranked" is a
# camper assigned a seatrade they never ranked (the UNMATCHED_PREFERENCE sentinel).
SATISFACTION_ORDER = ["1", "2", "3", "4", "Unranked"]
SATISFACTION_RANGE = ["#1a9850", "#91cf60", "#fee08b", "#fc8d59", "#d73027"]

# Neutral fill for cells a camper is not assigned, so the grid stays visible on a dark app theme.
UNASSIGNED_COLOR = "#99C2DF"

# Cohesion detail: red↔green on the *quality* (not the block) — a camper alone in a session is bad
# (red), with any cabinmate is good (green). Blocks still ride ``detail`` so they split on the
# tooltip; the colour just reads the x-axis level so the eye lands on the right conclusion.
COHESION_TOGETHERNESS_ORDER = ["Alone", "With a cabinmate"]
COHESION_TOGETHERNESS_RANGE = ["#d73027", "#1a9850"]

# Age spread detail: red↔green diverging on the range — 0–1 yr is tight (green), 2 yr is a stretch
# (yellow), 3 yr or wider is bad (red). Ordinal buckets, so a discrete scale, not a gradient.
AGE_SPREAD_BAND_ORDER = ["0–1 yr", "2 yr", "3+ yr"]
AGE_SPREAD_BAND_RANGE = ["#1a9850", "#fee08b", "#d73027"]

# Fleet Assignments: a cabin is on a Seatrade or on Fleet Time each block. This encodes
# *presence*, not goodness, so it deliberately avoids the green→red SATISFACTION scale — a
# saturated neutral blue (on a seatrade) vs. a muted grey (its complementary Fleet Time slot).
FLEET_STATE_ORDER = ["Seatrade", "Fleet Time"]
FLEET_STATE_RANGE = ["#4c78a8", "#b3b3b3"]

# Optimality donut: filled arc (proof-of-optimum) vs. the remaining gap track.
OPTIMALITY_FILL_COLOR = SATISFACTION_RANGE[0]  # reuse the top-pick green — "as good as proven"
OPTIMALITY_TRACK_COLOR = "#3a3f44"  # muted track that reads on the dark app theme


def normalize_to_band(
    raw: float,
    low_anchor: float,
    high_anchor: float,
    higher_is_better: bool,
    observed_min: float,
    observed_max: float,
) -> float:
    """Map a raw metric value to a 0–100 position on a uniformly up-is-good axis.

    The reference band ``[low_anchor, high_anchor]`` is the default domain and a
    floor on axis width: the effective domain is
    ``[min(low_anchor, observed_min), max(high_anchor, observed_max)]`` — it only
    ever expands to swallow an out-of-band observation, never contracts inside the
    anchors. Down-is-bad metrics (``higher_is_better=False``) are flipped so a lower
    raw value scores higher. Raw values are kept separate (tooltips), never shown here.

    Because the domain depends on which scenarios are on screen, this is a
    render-time concern — it lives here, not in the measurement layer (scoring.py).
    """
    effective_low = min(low_anchor, observed_min)
    effective_high = max(high_anchor, observed_max)
    width = effective_high - effective_low
    if width == 0:
        # Degenerate zero-width band (only if anchors coincide and observation sits on them).
        return 50.0
    position = (raw - effective_low) / width * 100
    return position if higher_is_better else 100 - position


def display_quality_summary(scorecard: Scorecard) -> alt.Chart:
    """The summary comparison plot: every Quality Metric on one up-is-good 0–100 axis.

    Metrics sit on an ordinal x in ``scorecard.metrics`` order (the single source of the
    deliberate Preference→…→Between-cabin fairness sequence — no parallel order constant); the
    axis shows each metric's user-facing label; y is each metric's raw value normalized against
    its reference band; the tooltip carries the *raw* value in plain units (never the position).
    One scenario for v1, so each metric's observed min/max is just its own raw value.
    """
    rows = []
    for metric in scorecard.metrics:
        rows.append(
            {
                "name": metric.name,
                "label": metric_label(metric.name),
                "raw_display": _format_raw_value(metric.name, metric.raw_value),
                "normalized": normalize_to_band(
                    metric.raw_value,
                    metric.low_anchor,
                    metric.high_anchor,
                    metric.higher_is_better,
                    observed_min=metric.raw_value,
                    observed_max=metric.raw_value,
                ),
            }
        )
    summary_df = pd.DataFrame(rows)
    labels_in_order = [metric_label(metric.name) for metric in scorecard.metrics]

    # TODO: switch to mark_line when we support overlaying multiple scenarios (area
    # fills get muddy + exaggerate axis-order bias).
    return (
        alt.Chart(summary_df)
        .mark_area(opacity=0.5, line=True, point=True)
        .encode(
            x=alt.X("label:N", sort=labels_in_order, title=None),
            # Bare y-axis (no title, ticks, or labels): the 0–100 position is a normalized
            # comparison aid, not a number to read off — "higher is better" is said in the caption.
            y=alt.Y(
                "normalized:Q",
                scale=alt.Scale(domain=[0, 100]),
                title="",
                axis=alt.Axis(labels=False, ticks=False),
            ),
            tooltip=[
                alt.Tooltip("label:N", title="Metric"),
                alt.Tooltip("raw_display:N", title="Measured value"),
            ],
        )
        .properties(title={"text": "Schedule Quality", "fontSize": 20, "anchor": "start"})
    )


def display_preference_detail(metric: QualityMetric) -> alt.Chart:
    """The Preference drill-down: how many campers landed at each CPR (3–6).

    x = CPR, y = camper count. Bars are coloured by ``cause`` (the two ranks that
    summed to the CPR), which does double duty: greens for good CPRs (≤4) vs reds
    for bad (≥5), and it splits the CPR-5 bar into its 1+4 and 2+3 causes.
    """
    return (
        alt.Chart(metric.detail)
        .mark_bar(stroke="black", strokeWidth=0.2)
        .encode(
            x=alt.X(
                "cpr:O",
                scale=alt.Scale(domain=[3, 4, 5, 6]),
                title="Combined pick rank (3 = best, 6 = worst)",
            ),
            y=alt.Y("count():Q", title="Campers"),
            color=alt.Color(
                "cause:N",
                scale=alt.Scale(domain=CPR_CAUSE_ORDER, range=CPR_CAUSE_RANGE),
                legend=alt.Legend(title="Which two picks (block 1 + block 2)"),
            ),
            tooltip=[
                alt.Tooltip("cause:N", title="Which picks"),
                alt.Tooltip("count():Q", title="Campers"),
            ],
        )
        .properties(
            title={
                "text": "Preference — campers who got good picks",
                "fontSize": 20,
                "anchor": "start",
            }
        )
    )


def display_cohesion_detail(metric: QualityMetric) -> alt.Chart:
    """The Cohesion drill-down: how many camper-sessions landed at each cabin-group size.

    x = how many cabinmates a camper is with in a session, counting themselves (1 = solo/
    stranded, 2 = with one cabinmate, …); y = count of camper-sessions. Colour reads the *quality*,
    not the block: a camper alone (x = 1) is red, with any cabinmate is green — the good-vs-bad the
    rollup penalises. Blocks are *not* colour-coded (a block colour falsely reads as "some blocks
    good, some bad"); they still ride the neutral ``detail`` stacking channel so the four blocks
    stay separate on hover. ``metric.detail`` is one row per (camper, session), so the solo bar
    counts every stranding, not just every stranded camper.
    """
    return (
        alt.Chart(metric.detail)
        .transform_calculate(togetherness="datum.cohort_size === 1 ? 'Alone' : 'With a cabinmate'")
        .mark_bar(stroke="black", strokeWidth=0.2)
        .encode(
            x=alt.X("cohort_size:O", title="Cabinmates together in a session (1 = alone)"),
            y=alt.Y("count():Q", title="Camper-sessions"),
            color=alt.Color(
                "togetherness:N",
                scale=alt.Scale(domain=COHESION_TOGETHERNESS_ORDER, range=COHESION_TOGETHERNESS_RANGE),
                legend=alt.Legend(title="Is the camper with a cabinmate?"),
            ),
            detail=["block:N"],
            tooltip=[
                alt.Tooltip("cohort_size:O", title="Cabinmates together"),
                alt.Tooltip("block:N", title="Block"),
                alt.Tooltip("count():Q", title="Camper-sessions"),
            ],
        )
        .properties(
            title={
                "text": "Cohesion — is each camper with a cabinmate?",
                "fontSize": 20,
                "anchor": "start",
            }
        )
    )


def display_sparsity_detail(metric: QualityMetric) -> alt.Chart:
    """The Sparsity drill-down: how many seatrades run in each block.

    x = block, y = count of running seatrades (sessions with ≥ 1 camper). ``metric.detail``
    is one row per running session, so a plain count per block tallies the sessions.
    """
    return (
        alt.Chart(metric.detail)
        .mark_bar(stroke="black", strokeWidth=0.2)
        .encode(
            x=alt.X("block:N", title="Block"),
            y=alt.Y("count():Q", title="Running seatrades"),
            tooltip=[
                alt.Tooltip("block:N", title="Block"),
                alt.Tooltip("count():Q", title="Running seatrades"),
            ],
        )
        .properties(
            title={
                "text": "Sparsity — seatrades to staff per block",
                "fontSize": 20,
                "anchor": "start",
            }
        )
    )


def display_age_spread_detail(metric: QualityMetric) -> alt.Chart:
    """The Age Spread drill-down: how many seatrades run at each age range.

    x = age range (years), y = count of running seatrades with that range. ``metric.detail``
    is one row per running session; the tooltip carries the seatrade and block so a large
    range can be traced back to the specific seatrade × block session that caused it.

    ``detail`` stacks one unit-height mark per running session, so each bar's height is the
    real seatrade count for that range. It has to ride a stacking channel: tooltip fields are
    pulled into the ``count()`` groupby (one group per session) but tooltip does not stack, so
    the fields there alone would overplot every session at height 1 and no bar would reach its
    true count.

    Colour is a red↔green diverging band on the range itself: 0–1 yr green, 2 yr yellow, 3+ yr red.
    """
    return (
        alt.Chart(metric.detail)
        .transform_calculate(band="datum.spread <= 1 ? '0–1 yr' : (datum.spread === 2 ? '2 yr' : '3+ yr')")
        .mark_bar(stroke="black", strokeWidth=0.2)
        .encode(
            x=alt.X("spread:O", title="Age range: oldest − youngest (0 = all the same age)"),
            y=alt.Y("count():Q", title="Seatrades"),
            color=alt.Color(
                "band:N",
                scale=alt.Scale(domain=AGE_SPREAD_BAND_ORDER, range=AGE_SPREAD_BAND_RANGE),
                legend=alt.Legend(title="Age range"),
            ),
            detail=["seatrade:N", "block:N"],
            tooltip=[
                alt.Tooltip("seatrade:N", title="Seatrade"),
                alt.Tooltip("block:N", title="Block"),
                alt.Tooltip("spread:O", title="Age range"),
            ],
        )
        .properties(
            title={
                "text": "Age spread — age range per seatrade",
                "fontSize": 20,
                "anchor": "start",
            }
        )
    )


def _histogram_with_average(
    detail: pd.DataFrame,
    field: str,
    x_title: str,
    tooltip_title: str,
    average: float,
    title: str,
) -> alt.Chart:
    """A per-cabin histogram (binned quantitative ``field`` on x, cabin count on y) with a
    dashed reference line at ``average`` on the bars' shared x scale, so it lines up with them
    rather than drawing its own independent axis.

    ``cabin`` rides the ``detail`` stacking channel (not tooltip alone) so bars reach their true
    cabin count — the same stacking gotcha as Age Spread: tooltip fields alone are pulled into
    the ``count()`` groupby but don't stack, so bars would overplot at height 1. ``average`` is
    passed in (not read off the metric) so each caller sources it from the plotted column and
    the line cannot drift from the bars.
    """
    bars = (
        alt.Chart(detail)
        .mark_bar(stroke="black", strokeWidth=0.2)
        .encode(
            x=alt.X(f"{field}:Q", bin=alt.Bin(maxbins=10), title=x_title),
            y=alt.Y("count():Q", title="Cabins"),
            detail=["cabin:N"],
            tooltip=[
                alt.Tooltip("cabin:N", title="Cabin"),
                alt.Tooltip(f"{field}:Q", title=tooltip_title),
            ],
        )
    )
    average_line = (
        alt.Chart(pd.DataFrame({"average": [average]}))
        .mark_rule(color="white", strokeDash=[4, 4])
        .encode(x=alt.X("average:Q"))
    )
    return (bars + average_line).properties(title={"text": title, "fontSize": 20, "anchor": "start"})


def display_fairness_within_detail(metric: QualityMetric) -> alt.Chart:
    """The Fairness Within drill-down: how many cabins land at each within-cabin CPR spread.

    The reference line is the mean of the *plotted* per-cabin spreads. That equals
    ``metric.raw_value`` here (Fairness Within's rollup already is the average-of-spreads), but
    is computed from the plotted column so it can never drift from the bars.
    """
    return _histogram_with_average(
        metric.detail,
        field="spread",
        x_title="Spread of pick ranks within a cabin (0 = everyone equal)",
        tooltip_title="Pick-rank spread",
        average=metric.detail["spread"].mean(),
        title="Within-cabin fairness — how even are schedules inside a cabin?",
    )


def display_fairness_between_detail(metric: QualityMetric) -> alt.Chart:
    """The Fairness Between drill-down: how many cabins land at each mean CPR.

    The reference line is the mean of the *plotted* cabin mean-CPRs — *not* ``metric.raw_value``,
    which is the std of those means (the Fairness Between score itself, a different quantity/units
    from what the x-axis plots).
    """
    return _histogram_with_average(
        metric.detail,
        field="mean_cpr",
        x_title="Cabin's average pick rank (3 = best, 6 = worst)",
        tooltip_title="Average pick rank",
        average=metric.detail["mean_cpr"].mean(),
        title="Between-cabin fairness — is any cabin worse off?",
    )


# Name → detail-chart builder. Single source for "which metrics have a drill-down"; the
# selectbox options are derived from the scorecard, so this keeps options and charts from
# drifting. Add a metric's builder here when its detail chart is ready.
_DETAIL_BUILDERS = {
    "Preference": display_preference_detail,
    "Cohesion": display_cohesion_detail,
    "Sparsity": display_sparsity_detail,
    "Age spread": display_age_spread_detail,
    "Fair within": display_fairness_within_detail,
    "Fair between": display_fairness_between_detail,
}


def display_metric_detail(metric: QualityMetric) -> alt.Chart:
    """Dispatch a Quality Metric to its detail chart via ``_DETAIL_BUILDERS``.

    Raises ``KeyError`` for a metric whose detail chart is not wired up yet, so an
    unrenderable selectbox option fails loudly instead of drawing the wrong chart.
    """
    try:
        builder = _DETAIL_BUILDERS[metric.name]
    except KeyError:
        raise KeyError(f"No detail chart registered for Quality Metric {metric.name!r}") from None
    return builder(metric)


def display_optimality_donut(optimality: float) -> alt.Chart:
    """Render the solver optimality as a donut gauge (N/100) with the percent in its center.

    ``optimality`` is the 0.0–1.0 fraction from ``SolverStatus.optimality`` (1.0 = provably
    optimal). This is the *solver's* proof-of-optimum, not schedule goodness — the caption
    at the call site says so. Pure Altair, no Streamlit.
    """
    pct = round(optimality * 100)
    segments = pd.DataFrame(
        {
            "segment": ["optimal", "gap"],
            "value": [optimality, 1.0 - optimality],
            "order": [0, 1],
        }
    )
    arc = (
        alt.Chart(segments)
        .mark_arc(innerRadius=55, outerRadius=80)
        .encode(
            theta=alt.Theta("value:Q", stack=True),
            color=alt.Color(
                "segment:N",
                scale=alt.Scale(
                    domain=["optimal", "gap"],
                    range=[OPTIMALITY_FILL_COLOR, OPTIMALITY_TRACK_COLOR],
                ),
                legend=None,
            ),
            order=alt.Order("order:Q"),
        )
    )
    center_text = (
        alt.Chart(pd.DataFrame({"label": [f"{pct}%"]}))
        .mark_text(fontSize=32, fontWeight="bold", color="white")
        .encode(text="label:N")
    )
    return (arc + center_text).properties(
        title={
            "text": "Solver Optimality",
            "fontSize": 20,
            "anchor": "start",
        }
    )


def _satisfaction_label(preference: int) -> str:
    """Map a preference rank to its satisfaction colour bucket."""
    if preference == UNMATCHED_PREFERENCE:
        return "Unranked"
    return str(preference)


def _rank_text(preference: int) -> str:
    """The rank to print on a cell — blank when the camper was assigned an unranked seatrade."""
    if preference == UNMATCHED_PREFERENCE:
        return ""
    return str(preference)


def display_fleet_assignments(fleet_grid: pd.DataFrame) -> alt.Chart:
    """Render the Cabin × Block fleet-placement overview as a neutral presence heatmap.

    Takes a ``wrangle_fleet_assignments`` frame (``cabin``, ``block``, ``state``). Each cell is
    a labeled binary — ``Seatrade`` or ``Fleet Time`` — coloured on the neutral presence scale,
    never the satisfaction scale. Blocks are decoded to their AM/PM labels (``1a`` → ``1st·AM``).

    Carries no chart title: the app renders an ``st.subheader("Fleet Assignments")`` directly
    above it, so a same-text chart title would double the heading.
    """
    fleet_grid = fleet_grid.copy()
    fleet_grid["block"] = fleet_grid["block"].map(block_label)
    block_order = [block_label(block) for block in BLOCKS]
    return (
        alt.Chart(fleet_grid)
        .mark_rect(stroke="white", strokeWidth=0.5)
        .encode(
            x=alt.X("block:N", title=None, sort=block_order),
            y=alt.Y("cabin:N", title=None),
            color=alt.Color(
                "state:N",
                scale=alt.Scale(domain=FLEET_STATE_ORDER, range=FLEET_STATE_RANGE),
                legend=alt.Legend(title="Cabin activity"),
            ),
            tooltip=[
                alt.Tooltip("cabin:N", title="Cabin"),
                alt.Tooltip("block:N", title="Block"),
                alt.Tooltip("state:N", title="Activity"),
            ],
        )
    )


def display_assignments(solution: AssignmentSolution) -> alt.Chart:
    """Render the seatrade assignments as a faceted Altair satisfaction heatmap."""
    alt.data_transformers.disable_max_rows()
    if solution.status.state == SolverState.ERROR:
        raise ValueError(f"No solution found. {solution.status.message}")
    elif solution.status.state == SolverState.INFEASIBLE:
        raise ValueError(
            f"Solver status ({solution.status.state.value}) indicates "
            "the problem was not successfully solved. Refusing to render untrustworthy results."
        )

    longform_df = wrangle_assignments_to_longform(solution)
    longform_df["block"] = longform_df["block"].map(block_label)
    longform_df["satisfaction"] = longform_df["preference"].map(_satisfaction_label)
    longform_df["rank_text"] = longform_df["preference"].map(_rank_text)

    assignment_base = alt.Chart(longform_df).encode(
        x=alt.X("seatrade", sort=solution.seatrades_full, title=None),
        y=alt.Y("camper", sort=solution.campers, title=None),
    )
    # Neutral fill behind every cell so the grid reads on a dark theme; assigned
    # cells are then coloured by satisfaction on top.
    assignment_background = assignment_base.mark_rect(color=UNASSIGNED_COLOR, stroke="white", strokeWidth=0.3)
    assigned_cells = assignment_base.transform_filter(alt.datum.preference > 0)
    assignment_rectangles = assigned_cells.mark_rect(stroke="black", strokeWidth=0.1).encode(
        color=alt.Color(
            "satisfaction:N",
            scale=alt.Scale(domain=SATISFACTION_ORDER, range=SATISFACTION_RANGE),
            legend=alt.Legend(title="Camper satisfaction (1 = top pick)"),
        )
    )
    assignment_text = assigned_cells.mark_text(color="black").encode(text="rank_text:N")
    assignment_chart = (
        (assignment_background + assignment_rectangles + assignment_text)
        .facet(row="cabin", column="block", spacing={"row": 2})
        .resolve_scale(y="independent")
        .properties(
            title={
                "text": "Camper Seatrade Assignments",
                "subtitle": "Colored by how happy each camper is with their assignment (1 = top pick).",
                "subtitleColor": "white",
                "fontSize": 20,
                "anchor": "start",
            }
        )
    )

    return assignment_chart
