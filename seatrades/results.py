"""
This file contains tools to display the results of seatrades assignment.
"""

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Optional

import altair as alt
import pandas as pd

if TYPE_CHECKING:
    from seatrades.seatrades import Seatrades


class SolverState(Enum):
    OPTIMAL = "OPTIMAL"
    INFEASIBLE = "INFEASIBLE"
    ERROR = "ERROR"

    @classmethod
    def from_pulp(cls, status_code: int) -> "SolverState":
        mapping = {1: cls.OPTIMAL, -1: cls.INFEASIBLE}
        return mapping.get(status_code, cls.ERROR)


@dataclass
class SolverStatus:
    state: SolverState
    gap: Optional[float] = None
    message: str = ""

    @classmethod
    def from_pulp(cls, status_code: int) -> "SolverStatus":
        state = SolverState.from_pulp(status_code)
        if state == SolverState.ERROR:
            pulp_messages = {0: "Not solved", -2: "Unbounded", -3: "Undefined"}
            message = pulp_messages.get(status_code, f"Unknown PuLP status: {status_code}")
        else:
            message = ""
        return cls(state=state, message=message)


@dataclass
class AssignmentSolution:
    assignments: pd.DataFrame
    status: SolverStatus
    cabins: list[str]
    campers: list[str]
    seatrades_full: list[str]
    cabin_camper_prefs: pd.DataFrame
    camper_prefs: pd.Series

    @classmethod
    def from_seatrades(cls, seatrades: "Seatrades") -> "AssignmentSolution":
        """Construct an AssignmentSolution from a solved Seatrades instance."""
        return cls(
            assignments=seatrades.assignments,
            status=SolverStatus.from_pulp(seatrades.status),
            cabins=seatrades.cabins,
            campers=seatrades.campers,
            seatrades_full=seatrades.seatrades_full,
            cabin_camper_prefs=seatrades.cabin_camper_prefs,
            camper_prefs=seatrades.camper_prefs,
        )


alt.data_transformers.disable_max_rows()


def wrangle_assignments_to_longform(solution: AssignmentSolution) -> pd.DataFrame:
    """Melt wide-form sparse DataFrame into long-form with preference and cabin lookup."""
    assignments = solution.assignments
    df = (
        assignments.melt(var_name="seatrade", ignore_index=False, value_name="assignment")
        .reset_index()
        .rename(columns={"index": "camper"})
    )

    def lookup_preference(row) -> int:
        if row.assignment:
            row_camper_prefs = solution.camper_prefs[row.camper]
            if row.seatrade[3:] in row_camper_prefs:
                return row_camper_prefs.index(row.seatrade[3:]) + 1
            return 999
        return 0

    df["preference"] = df.apply(lookup_preference, axis=1)

    def lookup_cabin(row) -> Optional[str]:
        camper = row.camper
        if camper in solution.cabin_camper_prefs.index:
            return solution.cabin_camper_prefs.loc[camper, "cabin"]
        return None

    df["cabin"] = df.apply(lookup_cabin, axis=1)  # type: ignore[call-overload]
    df[["block", "seatrade"]] = df["seatrade"].str.split("_", expand=True)

    return df


def wrangle_assignments_to_wideform(
    longform_df: pd.DataFrame,
    camper_order: Optional[list[str]] = None,
) -> pd.DataFrame:
    """Pivot long-form assignments to wide-form Captain's Book.

    1 row per camper. Columns: cabin, camper, Seatrade 1a, Seatrade 1b,
    Seatrade 2a, Seatrade 2b. Each camper fills exactly 2 of the 4 seatrade
    columns (one per block); the rest are blank.

    When camper_order is provided, rows are sorted to match that order.
    When None, rows are sorted by cabin → camper.
    Raises ValueError if a camper in the wideform is missing from camper_order.
    """
    assignments = longform_df[longform_df["assignment"] == 1.0].copy()
    assignments["block_label"] = "Seatrade " + assignments["block"]
    assignments["seatrade_name"] = assignments["seatrade"]

    assigned_by_camper = assignments.pivot_table(
        index=["cabin", "camper"],
        columns="block_label",
        values="seatrade_name",
        aggfunc="first",
        fill_value="",
    )

    seatrade_block_columns = ["Seatrade 1a", "Seatrade 1b", "Seatrade 2a", "Seatrade 2b"]
    for column in seatrade_block_columns:
        if column not in assigned_by_camper.columns:
            assigned_by_camper[column] = "Fleet Time"
    assigned_by_camper = assigned_by_camper[seatrade_block_columns]

    if camper_order is not None:
        wideform_campers = assigned_by_camper.index.get_level_values("camper").tolist()
        missing = set(wideform_campers) - set(camper_order)
        if missing:
            raise ValueError(f"camper_order is missing campers present in wideform: {sorted(missing)}")

    assigned_by_camper = assigned_by_camper.reset_index()

    if camper_order is not None:
        camper_rank = {name: i for i, name in enumerate(camper_order)}
        assigned_by_camper["_rank"] = assigned_by_camper["camper"].map(camper_rank)
        assigned_by_camper = (
            assigned_by_camper.sort_values(by="_rank", kind="stable").drop(columns="_rank").reset_index(drop=True)
        )
    else:
        assigned_by_camper = assigned_by_camper.sort_values(by=["cabin", "camper"], kind="stable")

    assigned_by_camper = assigned_by_camper[["cabin", "camper"] + seatrade_block_columns]
    assigned_by_camper.loc[:, seatrade_block_columns] = (
        assigned_by_camper.loc[:, seatrade_block_columns].replace("", pd.NA).fillna("Fleet Time")
    )

    return assigned_by_camper


def prepare_seatrade_leaders(longform_df: pd.DataFrame) -> pd.DataFrame:
    """Prepare Seatrade Leaders view: block, seatrade, camper, cabin.

    Filters to assigned rows only, drops preference/assignment columns.
    Sorted by block → seatrade → cabin → camper.
    """
    assigned = longform_df[longform_df["assignment"] == 1.0]
    sorted_assigned = assigned.sort_values(by=["block", "seatrade", "cabin", "camper"], kind="stable")
    return sorted_assigned[["block", "seatrade", "camper", "cabin"]].reset_index(drop=True)


def display_assignments(solution: AssignmentSolution) -> alt.Chart:
    """Display the assignments of the seatrades visually for inference."""
    if solution.status.state == SolverState.ERROR:
        raise ValueError(f"No solution found. {solution.status.message}")
    elif solution.status.state == SolverState.INFEASIBLE:
        raise ValueError(
            f"Solver status ({solution.status.state.value}) indicates "
            "the problem was not successfully solved. Refusing to render untrustworthy results."
        )

    df = wrangle_assignments_to_longform(solution)

    assignment_base = alt.Chart(df).encode(
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
