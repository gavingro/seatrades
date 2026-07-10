"""Result data structures and wrangling functions for seatrade assignments."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd

from seatrades.problem import BLOCKS, block_name, seatrade_name

SEATRADE_BLOCK_COLUMNS = ["Seatrade 1a", "Seatrade 1b", "Seatrade 2a", "Seatrade 2b"]

UNMATCHED_PREFERENCE = 999


class SolverState(Enum):
    OPTIMAL = "OPTIMAL"
    INFEASIBLE = "INFEASIBLE"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"

    @classmethod
    def from_pulp(cls, status_code: int) -> "SolverState":
        # PuLP code 0 ("Not Solved") is CBC hitting its time limit — feasible but unproven,
        # a TIMEOUT, not a crash. Only genuinely undefined states (-2, -3, unknown) are ERROR.
        mapping = {1: cls.OPTIMAL, -1: cls.INFEASIBLE, 0: cls.TIMEOUT}
        return mapping.get(status_code, cls.ERROR)


@dataclass
class SolverStatus:
    state: SolverState
    gap: Optional[float] = None
    message: str = ""
    # Stop reason carried onto the FINAL status: True when the solve stopped at the time
    # limit rather than proving optimality. One meaning ("hit the time limit"), two evidence
    # sources: set from the PuLP code for a TIMEOUT (via ``from_pulp``), and from the CBC log
    # for a stopped-on-time OPTIMAL incumbent (via ``solver.run``). Distinguishes a TIMEOUT
    # from a crash, and a proven-optimal success from a stopped-on-time incumbent.
    timed_out: bool = False

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
            pulp_messages = {-2: "Unbounded", -3: "Undefined"}
            message = pulp_messages.get(status_code, f"Unknown PuLP status: {status_code}")
        else:
            message = ""
        return cls(state=state, message=message, timed_out=state == SolverState.TIMEOUT)


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

    def lookup_preference_rank(row) -> int:
        """The rank this camper GAVE this seatrade — a pure camper↔seatrade fact.

        Populated on every cell regardless of assignment or block, so the rank a camper
        gave a seatrade they *didn't* get stays recoverable. ``UNMATCHED_PREFERENCE`` for a
        seatrade they never ranked (most cells, since each camper ranks only 4 seatrades).
        """
        row_camper_prefs = solution.camper_prefs[row.camper_id]
        seatrade_name = row.seatrade.split("_", 1)[1]
        if seatrade_name in row_camper_prefs:
            return row_camper_prefs.index(seatrade_name) + 1
        return UNMATCHED_PREFERENCE

    df["preference_rank"] = df.apply(lookup_preference_rank, axis=1)

    def lookup_cabin(row) -> Optional[str]:
        if row.camper_id in solution.cabin_camper_prefs.index:
            return solution.cabin_camper_prefs.loc[row.camper_id, "cabin"]
        return None

    df["cabin"] = df.apply(lookup_cabin, axis=1)  # type: ignore[call-overload]
    df["age"] = df["camper_id"].map(solution.cabin_camper_prefs["age"])
    df["camper"] = df["camper_id"].map(solution.camper_names)
    df[["block", "seatrade"]] = df["seatrade"].str.split("_", expand=True)

    # A schedule fact, distinct from ``assignment`` (one cell): does this camper have *any*
    # real seatrade in this block, vs being on Fleet Time? Grouped on camper_id (names collide),
    # so it is uniform across all of a (camper, block)'s seatrade cells.
    df["assigned_to_block"] = df.groupby(["camper_id", "block"])["assignment"].transform("max") == 1.0

    df = df.drop(columns="camper_id")

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


def _spanned_blocks(solution: AssignmentSolution) -> list[str]:
    """The blocks the solution actually spans, in canonical ``BLOCKS`` order.

    Derived from the distinct block prefixes of ``seatrades_full`` so the overview grids never
    show a phantom column for a block that carries no seatrade offering this week.
    """
    solution_blocks = {block_name(full) for full in solution.seatrades_full}
    return [block for block in BLOCKS if block in solution_blocks]


def wrangle_fleet_assignments(solution: AssignmentSolution) -> pd.DataFrame:
    """Cabin × Block presence grid: is each cabin on a Seatrade or Fleet Time each block?

    One row per (cabin, block) over all ``solution.cabins`` × the blocks the solution
    actually spans (the distinct block prefixes of ``seatrades_full``, in canonical order).
    ``state`` is ``"Seatrade"`` if *any* of the cabin's campers is assigned a seatrade that
    block, else ``"Fleet Time"`` — the perfect complement, never modeled in the solver.
    """
    longform_df = wrangle_assignments_to_longform(solution)
    blocks = _spanned_blocks(solution)

    assigned = longform_df[longform_df["assignment"] == 1.0]
    on_seatrade = set(zip(assigned["cabin"], assigned["block"], strict=True))

    rows = [
        {"cabin": cabin, "block": block, "state": "Seatrade" if (cabin, block) in on_seatrade else "Fleet Time"}
        for cabin in solution.cabins
        for block in blocks
    ]
    return pd.DataFrame(rows, columns=["cabin", "block", "state"])


def wrangle_seatrade_staffing(solution: AssignmentSolution) -> pd.DataFrame:
    """Seatrade × Block staffing grid: does each seatrade run as a session each block?

    One row per (seatrade, block) over all seatrades in the setup (the distinct trade names
    of ``seatrades_full``, so a seatrade with zero uptake still gets a row) × the blocks the
    solution actually spans. ``state`` is ``"Running"`` if *any* camper is assigned that
    seatrade that block, else ``"Not offered"`` — so a seatrade nobody picked reads as a full
    ``Not offered`` row, surfacing that there is nobody to staff it this week.

    Rows are emitted in ``seatrades_full`` order; ``display_seatrade_staffing`` relies on this
    row order for its y-axis sort, so a downstream regroup/sort would silently reorder the view.
    """
    longform_df = wrangle_assignments_to_longform(solution)
    seatrades = list(dict.fromkeys(seatrade_name(full) for full in solution.seatrades_full))
    blocks = _spanned_blocks(solution)

    assigned = longform_df[longform_df["assignment"] == 1.0]
    running = set(zip(assigned["seatrade"], assigned["block"], strict=True))

    rows = [
        {"seatrade": seatrade, "block": block, "state": "Running" if (seatrade, block) in running else "Not offered"}
        for seatrade in seatrades
        for block in blocks
    ]
    return pd.DataFrame(rows, columns=["seatrade", "block", "state"])


def prepare_seatrade_leaders(longform_df: pd.DataFrame) -> pd.DataFrame:
    """Prepare Seatrade Leaders view: block, seatrade, camper, cabin.

    Filters to assigned rows only, drops preference/assignment columns.
    Sorted by block → seatrade → cabin → camper.
    """
    assigned = longform_df[longform_df["assignment"] == 1.0]
    sorted_assigned = assigned.sort_values(by=["block", "seatrade", "cabin", "camper"], kind="stable")
    return sorted_assigned[["block", "seatrade", "camper", "cabin"]].reset_index(drop=True)
