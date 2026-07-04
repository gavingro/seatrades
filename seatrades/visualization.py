"""Altair chart specs for seatrade assignment results."""

import altair as alt
import pandas as pd

from seatrades.blocks import block_label
from seatrades.results import (
    UNMATCHED_PREFERENCE,
    AssignmentSolution,
    SolverState,
    wrangle_assignments_to_longform,
)
from seatrades.scoring import QualityMetric, Scorecard

# Fixed, deliberate ordinal x-order for the summary comparison plot. Only Preference
# exists in v1; the rest are placeholders the later metric slices fill in.
METRIC_ORDER = ["Preference", "Cohesion", "Sparsity", "Age spread", "Fair within", "Fair between"]

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

    Metrics sit on an ordinal x in the fixed ``METRIC_ORDER``; y is each metric's
    raw value normalized against its reference band; the tooltip carries the *raw*
    value (never the position). One scenario for v1, so each metric's observed
    min/max is just its own raw value.
    """
    rows = []
    for metric in scorecard.metrics:
        rows.append(
            {
                "name": metric.name,
                "raw_value": metric.raw_value,
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

    # TODO: switch to mark_line when we support overlaying multiple scenarios (area
    # fills get muddy + exaggerate axis-order bias).
    return (
        alt.Chart(summary_df)
        .mark_area(opacity=0.5, line=True, point=True)
        .encode(
            x=alt.X("name:N", sort=METRIC_ORDER, title=None),
            y=alt.Y("normalized:Q", scale=alt.Scale(domain=[0, 100]), title="Quality (up is good)"),
            tooltip=[alt.Tooltip("name:N", title="Metric"), alt.Tooltip("raw_value:Q", title="Raw value")],
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
                title="Combined Preference Rank (3 = best, 6 = worst)",
            ),
            y=alt.Y("count():Q", title="Campers"),
            color=alt.Color(
                "cause:N",
                scale=alt.Scale(domain=CPR_CAUSE_ORDER, range=CPR_CAUSE_RANGE),
                legend=alt.Legend(title="Rank pair (block #1 + block #2)"),
            ),
            tooltip=[alt.Tooltip("cause:N", title="Rank pair"), alt.Tooltip("count():Q", title="Campers")],
        )
        .properties(title={"text": "Preference — campers with a good schedule", "fontSize": 20, "anchor": "start"})
    )


def display_cohesion_detail(metric: QualityMetric) -> alt.Chart:
    """The Cohesion drill-down: how many campers landed in each same-cabin cohort size.

    x = the largest same-cabin cohort a camper shares a seatrade session with, counting
    themselves (1 = solo, 2 = with one cabinmate, …); y = camper count.
    """
    return (
        alt.Chart(metric.detail)
        .mark_bar(stroke="black", strokeWidth=0.2)
        .encode(
            x=alt.X("cohort_size:O", title="Cabinmates in same session (1 = solo)"),
            y=alt.Y("count():Q", title="Campers"),
            tooltip=[
                alt.Tooltip("cohort_size:O", title="Cabin group size"),
                alt.Tooltip("count():Q", title="Campers"),
            ],
        )
        .properties(title={"text": "Cohesion — campers with a cabinmate", "fontSize": 20, "anchor": "start"})
    )


# Name → detail-chart builder. Single source for "which metrics have a drill-down"; the
# selectbox options are derived from the scorecard, so this keeps options and charts from
# drifting. Add a metric's builder here when its detail chart is ready.
_DETAIL_BUILDERS = {
    "Preference": display_preference_detail,
    "Cohesion": display_cohesion_detail,
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
