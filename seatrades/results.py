"""
This file contains tools to display the results of seatrades assignment.
"""

import logging

import altair as alt

from seatrades.seatrades import Seatrades

logger = logging.getLogger(__name__)
alt.data_transformers.disable_max_rows()


def display_assignments(seatrades: Seatrades) -> alt.Chart:
    """
    Displays the assignments of the seatrades visually for inference.
    """
    if not seatrades.status:
        raise ValueError(
            "Seatrades.assignments (and status code) not found."
            "Did you remember to run Seatrades.assign() first?"
        )
    elif seatrades.status < 1:
        logging.warning(
            f"Seatrades status code ({seatrades.status}) indicates that "
            "problem was not sucessfully solved. Use caution in interpretation of results."
        )

    df = seatrades.wrangle_assignments_to_longform(seatrades.assignments)

    # Matrix Assignment chart.
    assignment_base = alt.Chart(df).encode(
        x=alt.X("seatrade", sort=seatrades.seatrades_full, title=None),
        y=alt.Y("camper", sort=seatrades.campers, title=None),
    )
    assignment_rectangles = assignment_base.mark_rect(
        stroke="black", strokeWidth=0.1
    ).encode(
        color=alt.Color(
            "preference:O",
        )
    )
    assignment_text = (
        assignment_base.mark_text(color="white")
        .encode(text="preference:O")
        .transform_filter(alt.datum.preference > 0)
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
