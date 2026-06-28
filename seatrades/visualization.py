"""Altair chart specs for seatrade assignment results."""

import altair as alt

from seatrades.blocks import block_label
from seatrades.results import (
    UNMATCHED_PREFERENCE,
    AssignmentSolution,
    SolverState,
    wrangle_assignments_to_longform,
)

# Satisfaction scale: top choice (green) → low/unranked (red). "Unranked" is a
# camper assigned a seatrade they never ranked (the UNMATCHED_PREFERENCE sentinel).
SATISFACTION_ORDER = ["1", "2", "3", "4", "Unranked"]
SATISFACTION_RANGE = ["#1a9850", "#91cf60", "#fee08b", "#fc8d59", "#d73027"]

# Neutral fill for cells a camper is not assigned, so the grid stays visible on a dark app theme.
UNASSIGNED_COLOR = "#99C2DF"


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
                "fontSize": 20,
                "anchor": "start",
            }
        )
    )

    return assignment_chart
