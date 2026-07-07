"""Result data structures and wrangling functions for seatrade assignments."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd

from seatrades.problem import BLOCKS, block_name

SEATRADE_BLOCK_COLUMNS = ["Seatrade 1a", "Seatrade 1b", "Seatrade 2a", "Seatrade 2b"]

UNMATCHED_PREFERENCE = 999


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

    @property
    def is_optimal(self) -> bool:
        """Whether the solver reached an optimal solution."""
        return self.state == SolverState.OPTIMAL

    @property
    def optimality(self) -> float:
        """Fraction optimal (1.0 = provably optimal). Inverse of the optimality gap."""
        return 1.0 - self.gap if self.gap is not None else 1.0

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
    # camper_id -> camper_name. Internal: assignments/prefs are keyed by integer
    # camper_id; this translates them to names at the user-facing edge. No public
    # method exposes camper_id itself.
    camper_names: pd.Series


def wrangle_assignments_to_longform(solution: AssignmentSolution) -> pd.DataFrame:
    """Melt wide-form sparse DataFrame into long-form with preference and cabin lookup.

    Assignments are keyed by integer camper_id internally; this translates each
    row to its camper_name (looked up by id, which is collision-free) and emits a
    user-facing ``camper`` name column. The camper_id never appears in the output.
    """
    assignments = solution.assignments
    df = assignments.melt(var_name="seatrade", ignore_index=False, value_name="assignment").reset_index()

    def lookup_preference(row) -> int:
        if row.assignment == 1.0:
            row_camper_prefs = solution.camper_prefs[row.camper_id]
            seatrade_name = row.seatrade.split("_", 1)[1]
            if seatrade_name in row_camper_prefs:
                return row_camper_prefs.index(seatrade_name) + 1
            return UNMATCHED_PREFERENCE
        return 0

    df["preference"] = df.apply(lookup_preference, axis=1)

    def lookup_cabin(row) -> Optional[str]:
        if row.camper_id in solution.cabin_camper_prefs.index:
            return solution.cabin_camper_prefs.loc[row.camper_id, "cabin"]
        return None

    df["cabin"] = df.apply(lookup_cabin, axis=1)  # type: ignore[call-overload]
    df["age"] = df["camper_id"].map(solution.cabin_camper_prefs["age"])
    df["camper"] = df["camper_id"].map(solution.camper_names)
    df = df.drop(columns="camper_id")
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
        index=["cabin", "camper", "age"],
        columns="block_label",
        values="seatrade_name",
        aggfunc="first",
        fill_value="",
    )

    for column in SEATRADE_BLOCK_COLUMNS:
        if column not in assigned_by_camper.columns:
            assigned_by_camper[column] = "Fleet Time"
    assigned_by_camper = assigned_by_camper[SEATRADE_BLOCK_COLUMNS]

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

    assigned_by_camper = assigned_by_camper[["cabin", "camper", "age"] + SEATRADE_BLOCK_COLUMNS]
    assigned_by_camper.loc[:, SEATRADE_BLOCK_COLUMNS] = (
        assigned_by_camper.loc[:, SEATRADE_BLOCK_COLUMNS].replace("", pd.NA).fillna("Fleet Time")
    )

    return assigned_by_camper


def wrangle_fleet_assignments(solution: AssignmentSolution) -> pd.DataFrame:
    """Cabin × Block presence grid: is each cabin on a Seatrade or Fleet Time each block?

    One row per (cabin, block) over all ``solution.cabins`` × the blocks the solution
    actually spans (the distinct block prefixes of ``seatrades_full``, in canonical order).
    ``state`` is ``"Seatrade"`` if *any* of the cabin's campers is assigned a seatrade that
    block, else ``"Fleet Time"`` — the perfect complement, never modeled in the solver.
    """
    longform_df = wrangle_assignments_to_longform(solution)
    blocks = [block for block in BLOCKS if block in {block_name(full) for full in solution.seatrades_full}]

    assigned = longform_df[longform_df["assignment"] == 1.0]
    on_seatrade = set(zip(assigned["cabin"], assigned["block"], strict=True))

    rows = [
        {"cabin": cabin, "block": block, "state": "Seatrade" if (cabin, block) in on_seatrade else "Fleet Time"}
        for cabin in solution.cabins
        for block in blocks
    ]
    return pd.DataFrame(rows, columns=["cabin", "block", "state"])


def prepare_seatrade_leaders(longform_df: pd.DataFrame) -> pd.DataFrame:
    """Prepare Seatrade Leaders view: block, seatrade, camper, cabin.

    Filters to assigned rows only, drops preference/assignment columns.
    Sorted by block → seatrade → cabin → camper.
    """
    assigned = longform_df[longform_df["assignment"] == 1.0]
    sorted_assigned = assigned.sort_values(by=["block", "seatrade", "cabin", "camper"], kind="stable")
    return sorted_assigned[["block", "seatrade", "camper", "cabin"]].reset_index(drop=True)
