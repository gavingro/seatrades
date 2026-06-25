"""Altair chart specs for seatrade assignment results."""

import altair as alt

from seatrades.results import AssignmentSolution, SolverState, wrangle_assignments_to_longform


def display_assignments(solution: AssignmentSolution) -> alt.Chart:
    """Display the assignments of the seatrades visually for inference."""
    alt.data_transformers.disable_max_rows()
    if solution.status.state == SolverState.ERROR:
        raise ValueError(f"No solution found. {solution.status.message}")
    elif solution.status.state == SolverState.INFEASIBLE:
        raise ValueError(
            f"Solver status ({solution.status.state.value}) indicates "
            "the problem was not successfully solved. Refusing to render untrustworthy results."
        )

    longform_df = wrangle_assignments_to_longform(solution)

    assignment_base = alt.Chart(longform_df).encode(
        x=alt.X("seatrade", sort=solution.seatrades_full, title=None),
        y=alt.Y("camper", sort=solution.campers, title=None),
    )
    assignment_rectangles = assignment_base.mark_rect(stroke="black", strokeWidth=0.1).encode(
        color=alt.Color(
            "preference:O",
        )
    )
    assignment_text = (
        assignment_base.mark_text(color="white").encode(text="preference:O").transform_filter(alt.datum.preference > 0)
    )
    assignment_chart = (
        (assignment_rectangles + assignment_text)
        .facet(row="cabin", column="block", spacing={"row": 2})
        .resolve_scale(y="independent")
        .properties(
            title={
                "text": "Seatrades.",
                "subtitle": "Assignments by Preference.",
                "fontSize": 20,
                "anchor": "start",
            }
        )
    )

    return assignment_chart
