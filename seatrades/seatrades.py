"""
This file contains tools to assign seatrades to campers based on their preferences.

TODO: Extract FLEETS constant — "1a","1b","2a","2b" is duplicated between
Seatrades.__init__ (self.fleets) and wrangle_assignments_to_wideform (col_order).
Derive CAPTAINS_BOOK_COLUMNS from a single source of truth.

Pandera mypy suppressions:
- type: ignore[attr-defined] on .set_index() calls (lines ~50, ~52, ~58): pandera
  DataFrameModel subclasses are DataFrames at runtime but mypy doesn't recognize
  set_index as a valid method on them.
- type: ignore[index] on bracket indexing (lines ~51, ~55, ~59): same root cause —
  mypy can't verify DataFrameModel is indexable.
- type: ignore[call-overload] on df.apply(lookup_cabin, axis=1) (line ~387): pandas-stubs
  has no overload variant matching a callable returning Optional[str] with axis=1.

Revisit if pandera mypy plugin improves or pandas-stubs adds DataFrameModel support.
"""

import logging
from typing import Optional

import pandas as pd
import pulp

from seatrades.preferences import (
    CamperSeatradePreferences,
    SeatradesConfig,
    add_index_to_campername,
)

logger = logging.getLogger(__name__)


class Seatrades:
    """A class to handle LP problems to solve seatrade assignment."""

    def __init__(
        self,
        cabin_camper_prefs: CamperSeatradePreferences,
        seatrades_prefs: SeatradesConfig,
    ):
        """
        A class to handle LP problems to solve seatrade assignment.

        Parameters
        ----------
        cabin_camper_prefs : CamperSeatradePreferences
            A dataframe containing the camper-cabin-seatrade
            preferences information.
        seatrades_prefs : SeatradesConfig
            A dataframe containing the seatrade-minsize-maxsize
            information.
        """
        cabin_camper_prefs = add_index_to_campername(cabin_camper_prefs)
        self.cabin_camper_prefs = cabin_camper_prefs.set_index("camper")  # type: ignore[attr-defined]
        self.cabins = cabin_camper_prefs["cabin"].unique().tolist()  # type: ignore[index]
        self.camper_prefs = cabin_camper_prefs.set_index("camper")[  # type: ignore[attr-defined]
            ["seatrade_1", "seatrade_2", "seatrade_3", "seatrade_4"]
        ].apply(list, axis="columns")
        self.campers = cabin_camper_prefs["camper"].tolist()  # type: ignore[index]

        # Seatrades for block 1 and block 2.
        self.seatrades_prefs = seatrades_prefs.set_index("seatrade")  # type: ignore[attr-defined]
        self.seatrades = seatrades_prefs["seatrade"]  # type: ignore[index]
        self.seatrades1a = [f"1a_{seatrade}" for seatrade in self.seatrades]
        self.seatrades1b = [f"1b_{seatrade}" for seatrade in self.seatrades]
        self.seatrades2a = [f"2a_{seatrade}" for seatrade in self.seatrades]
        self.seatrades2b = [f"2b_{seatrade}" for seatrade in self.seatrades]
        self.seatrades_full = self.seatrades1a + self.seatrades1b + self.seatrades2a + self.seatrades2b
        self.fleets = ["1a", "1b", "2a", "2b"]
        self.assignments: pd.DataFrame
        self.status = 0

    def assign(
        self,
        preference_weight: float = 5.0,
        cabins_weight: Optional[float] = None,
        sparsity_weight: Optional[float] = None,
        max_seatrades_per_fleet: Optional[int] = None,
        solver: Optional[pulp.core.LpSolver] = None,
    ) -> pulp.LpProblem:
        """
        Uses the objects campers_df and seatrades_df to solve a Linear Programming
        problem to assign each camper to their ideal seatrades while respecting
        size constraints.

        Details found in documentation/seatrades_assignment_math.md.

        Parameters
        ----------
        preference_weight : float, optional
            A scalar to weight the importance of camper
            preferences on seatrade assignments, by default 5.0
        cabins_weight : Optional[float], optional
            A scalar to weight the importance of putting cabinmates
            together on seatrade assignments (if not none), by default None
        sparsity_weight : Optional[float], optional
            A scalar to weight the importance of having fewer seatrades
            in each block (if not none), by default None
        max_seatrades_per_fleet : Optional[int], optional
            The maximum number of seatrade activities to be assigned across all campers
            within each fleet if present, by default None


        Returns
        -------
        pulp.LpProblem
            The underlying LpProblem instance that is being solved.
            The convergence of the problem can be found under the .status attribute.
        """
        # Setup problem and parameters.
        logger.info("Setting Up Problem Variables")
        problem = pulp.LpProblem(name="seatrades_assignment")
        camper_assignments = pulp.LpVariable.dicts(
            "Camper_Assignments",
            (self.campers, self.seatrades_full),
            lowBound=0,
            upBound=1,
            cat=pulp.LpBinary,
        )
        # Helper Param: Cabin Assignment is 1 if any camper
        # from cabin in seatrade, else 0.
        # Requires clever constraint by comparing camper assignment for each camper in seatrade.
        cabin_assignments = pulp.LpVariable.dicts(
            "Cabin Assignment",
            (self.cabins, self.seatrades_full),
            lowBound=0,
            upBound=1,
            cat=pulp.LpBinary,
        )
        for s in self.seatrades_full:
            for cabin in self.cabins:
                cabin_campers = self.cabin_camper_prefs.loc[self.cabin_camper_prefs["cabin"] == cabin,].index.tolist()
                for c in cabin_campers:
                    # Cabin assignment is ge than camper assignment.
                    # Ensures if any campers are assigned, cabin is assigned.
                    problem += cabin_assignments[cabin][s] >= camper_assignments[c][s]

        # Helper Param: Fleet Assignment is 1 if any camper
        # from cabin in fleet, else 0.
        # Requires clever constraint by comparing camper assignment fr each camper in fleet.
        fleet_assignment = pulp.LpVariable.dicts(
            "Cabin Fleet Assignment",
            (self.cabins, self.fleets),
            lowBound=0,
            upBound=1,
            cat=pulp.LpBinary,
        )
        for fleet in self.fleets:
            for seatrade in self.seatrades:
                s = f"{fleet}_{seatrade}"
                for cabin in self.cabins:
                    cabin_campers = self.cabin_camper_prefs.loc[
                        self.cabin_camper_prefs["cabin"] == cabin,
                    ].index.tolist()
                    for c in cabin_campers:
                        # Fleet assignment is ge than camper assignment.
                        # Ensures if any campers are assigned, cabin is assigned to fleet.
                        problem += fleet_assignment[cabin][fleet] >= camper_assignments[c][s]
        # Helper Param: Seatrade Assignment is 1 if any camper is
        # assigned to the seatrade, else 0.
        # Requires clever constraint by comparing camper assignment for each camper in seatrade.
        seatrade_assignment = pulp.LpVariable.dicts(
            "Seatrade Fleet Assignment",
            (self.fleets, self.seatrades),
            lowBound=0,
            upBound=1,
            cat=pulp.LpBinary,
        )
        for fleet in self.fleets:
            for seatrade in self.seatrades:
                s = f"{fleet}_{seatrade}"
                for c in self.campers:
                    # Fleet assignment is ge than camper assignment.
                    # Ensures if any campers are assigned, cabin is assigned to fleet.
                    problem += seatrade_assignment[fleet][seatrade] >= camper_assignments[c][s]

        # CONSTRAINTS:
        logger.info("Adding Variable Constraints")
        # Constraint 1: Each camper is assigned 1 seatrade in each of 2 blocks (1ab and 2ab).
        for block_index, seatrades in enumerate(
            [self.seatrades1a + self.seatrades1b, self.seatrades2a + self.seatrades2b],
        ):
            for c in self.campers:
                problem += (
                    pulp.lpSum([camper_assignments[c][s] for s in seatrades]) == 1,
                    f"{c}_in_only_1_seatrade_block_{block_index}",
                )
        # Constraint 2: Each camper cannot be assigned the same seatrade
        # in both blocks.
        for seatrade in self.seatrades:
            for c in self.campers:
                problem += (
                    pulp.lpSum(
                        [
                            camper_assignments[c][f"1a_{seatrade}"],
                            camper_assignments[c][f"1b_{seatrade}"],
                            camper_assignments[c][f"2a_{seatrade}"],
                            camper_assignments[c][f"2b_{seatrade}"],
                        ]
                    )
                    <= 1,
                    f"{c} can't take {seatrade} in both blocks",
                )
        # Constraint 3: Each seatrade is assigned between min and max campers.
        for s in self.seatrades_full:
            seatrade = s[3:]  # Remove block index for matching.
            seatrade_campers_min = self.seatrades_prefs.loc[seatrade, "campers_min"]
            problem += (
                pulp.lpSum([camper_assignments[c][s] for c in self.campers]) >= seatrade_campers_min,
                f"More_than_{seatrade_campers_min}_in_{s}",
            )
            seatrade_campers_max = self.seatrades_prefs.loc[seatrade, "campers_max"]
            problem += (
                pulp.lpSum([camper_assignments[c][s] for c in self.campers]) <= seatrade_campers_max,
                f"Less_than_{seatrade_campers_max}_in_{s}",
            )
        # Constraint 4: Campers cannot be assigned un-requested seatrades.
        for c, seatrade_prefs in self.camper_prefs.items():
            problem += (
                pulp.lpSum([camper_assignments[c][s] for s in self.seatrades_full if s[3:] not in seatrade_prefs]) == 0,
                f"{c}_prefers_not_these_seatrades.",
            )
        # Constraint 5: Campers guaranteed one of their top 2 choices.
        # In other words, they cannot be assigned 3rd and 4th choices together.
        # In other words, their combined preference totals must be less than 3+4=7.
        for c, preferences in self.camper_prefs.items():
            problem += (
                pulp.lpSum(
                    # Use indicator function from assignment
                    # multiplied by linear preference penalty
                    # from index.
                    [camper_assignments[c][f"1a_{s}"] * (preferences.index(s)) for s in preferences]
                    + [camper_assignments[c][f"1b_{s}"] * (preferences.index(s)) for s in preferences]
                    + [camper_assignments[c][f"2a_{s}"] * (preferences.index(s)) for s in preferences]
                    + [camper_assignments[c][f"2b_{s}"] * (preferences.index(s)) for s in preferences]
                )
                <= 5 - 1,  # indexing of 0 means 3rd + 4th preference index is 2+3=5.
                f"{c} guaranteed one of the first two seatrades.",
            )
        # Constraint 6: For each seatrade, a cabin can contribute no
        # more than 4 campers.
        for s in self.seatrades_full:
            for cabin in self.cabins:
                cabin_campers = self.cabin_camper_prefs.loc[self.cabin_camper_prefs["cabin"] == cabin].index.tolist()
                problem += (
                    pulp.lpSum([camper_assignments[c][s] for c in cabin_campers]) <= 4,
                    f"{cabin} must contribute <= 4 campers to {s}.",
                )
        # Constraint 7: Each cabin can only be assigned to a single
        # fleet (cabin has to be assigned together).
        for fleet_blocks in [["1a", "1b"], ["2a", "2b"]]:
            for cabin in self.cabins:
                problem += (
                    pulp.lpSum([fleet_assignment[cabin][f] for f in fleet_blocks]) == 1,
                    f"{cabin}_in_only_1_fleet_{fleet_blocks}",
                )
        # Constraint 8: Divide the number of cabins up equally between the two
        # fleets.
        # If each fleet needs at least half the cabins (rounded down), then cabins
        # should be split equally if even and fairly if odd.
        half_of_the_cabins_min = len(self.cabins) // 2
        for fleet in self.fleets:
            problem += (
                pulp.lpSum([fleet_assignment[cabin][fleet] for cabin in self.cabins]) >= half_of_the_cabins_min,
                f"Roughly_half_of_cabins_in_fleet_{fleet}",
            )
        # Constraint 9: Divide the number of girls and boys cabins roughly equally between the
        # fleets.
        cabin_genders = self.cabin_camper_prefs.groupby("cabin")["gender"].agg(lambda grp: pd.Series.mode(grp)[0])
        for gender in self.cabin_camper_prefs["gender"].unique():
            gender_cabins = cabin_genders[cabin_genders == gender].index.tolist()
            half_of_the_gender_cabins_min = len(gender_cabins) // 2
            for fleet in self.fleets:
                problem += (
                    pulp.lpSum([fleet_assignment[cabin][fleet] for cabin in gender_cabins])
                    >= half_of_the_gender_cabins_min,
                    f"Roughly_half_of_{gender}_cabins_in_fleet_{fleet}",
                )
        # (Optional) Constraint 10: Ensure no more than max_seatrades_per_fleet are
        # assigned within each fleet.
        if max_seatrades_per_fleet:
            for fleet in self.fleets:
                problem += (
                    pulp.lpSum([seatrade_assignment[fleet][f"{seatrade}"] for seatrade in self.seatrades])
                    <= max_seatrades_per_fleet,
                    f"Ensure_{fleet}_has_less_than_{max_seatrades_per_fleet}_seatrades.",
                )

        # OBJECTIVE:
        logger.info("Setting Up Objective Function")
        obj = 0
        # PENALTY 1: Penalize giving lower-preference seatrades.
        for c, preferences in self.camper_prefs.items():
            for block in self.fleets:
                obj += preference_weight * pulp.lpSum(
                    [
                        # Use indicator function from assignment
                        # multiplied by linear preference penalty
                        # from index.
                        camper_assignments[c][f"{block}_{s}"] * (preferences.index(s))
                        for s in preferences
                    ]
                )
        # OPTIONAL PENALTY 2: Penalize for number of cabins assigned to a single seatrade.
        # (Reward for assigning friends together).
        if cabins_weight:
            for s in self.seatrades_full:
                obj += cabins_weight * pulp.lpSum([cabin_assignments[cabin][s] for cabin in self.cabins])

        # OPTIONAL PENALTY 3: Penalize for number of seatrades assigned to a fleet.
        # (Reward for sparsity, meaning less staff needing to be scheduled).
        if sparsity_weight:
            for fleet in self.fleets:
                for s in self.seatrades:
                    obj += sparsity_weight * seatrade_assignment[fleet][s]

        logger.info("Solving Problem.")
        # Solve and save assignments:
        problem += obj

        if solver:
            status = problem.solve(solver)
        else:
            status = problem.solve()
        self.status = status if status else -1
        self.assignments = pd.DataFrame(camper_assignments).map(pulp.value).transpose()
        return problem

    def get_assignments_by_cabin(self, assignments: pd.DataFrame) -> dict:
        """Get the assignments organized by Cabin -> Camper -> Seatrade."""
        raise NotImplementedError

    def get_assignments_by_seatrade(self, assignments: pd.DataFrame) -> dict:
        """Get the assignments organized by seatrade -> Cabin -> Camper."""
        raise NotImplementedError
