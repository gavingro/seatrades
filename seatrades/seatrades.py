"""
This file contains tools to assign seatrades to campers based on their preferences.
"""

from typing import Dict, Literal, List, Optional
from time import time
import logging

import pulp
import numpy as np
import pandas as pd
import altair as alt

from seatrades.preferences import SeatradesConfig, CamperSeatradePreferences


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

        self.cabin_camper_prefs = cabin_camper_prefs.set_index("camper")
        self.cabins = cabin_camper_prefs["cabin"].unique().tolist()
        self.camper_prefs = cabin_camper_prefs.set_index("camper")[
            ["seatrade_1", "seatrade_2", "seatrade_3", "seatrade_4"]
        ].apply(list, axis="columns")
        self.campers = cabin_camper_prefs["camper"].tolist()

        # Seatrades for block 1 and block 2.
        self.seatrades_prefs = seatrades_prefs.set_index("seatrade")
        self.seatrades = seatrades_prefs["seatrade"]
        self.seatrades1a = [f"1a_{seatrade}" for seatrade in self.seatrades]
        self.seatrades1b = [f"1b_{seatrade}" for seatrade in self.seatrades]
        self.seatrades2a = [f"2a_{seatrade}" for seatrade in self.seatrades]
        self.seatrades2b = [f"2b_{seatrade}" for seatrade in self.seatrades]
        self.seatrades_full = (
            self.seatrades1a + self.seatrades1b + self.seatrades2a + self.seatrades2b
        )
        self.fleets = ["1a", "1b", "2a", "2b"]
        self.assignments: pd.DataFrame

    # Helper Function
    def _flatten(self, outer_list: List[list]):
        """Flattens the 2d input list into 1d."""
        return {
            key: value
            for inner_dict in outer_list.values()
            for key, value in inner_dict.items()
        }

    def assign(
        self, preference_temperature: float = 5.0, cabins_temperature: float = 5.0
    ) -> pulp.LpProblem:
        """
        Uses the objects campers_df and seatrades_df to solve a Linear Programming
        problem to assign each camper to their ideal seatrades while respecting
        size constraints.

        Details found in documentation/seatrades_assignment_math.md.

        Returns
        -------
        int
            A status code representing feasibility of the problem.
            1 if failure, 0 if success.
        """
        # Setup problem and parameters.
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
                cabin_campers = self.cabin_camper_prefs.loc[
                    self.cabin_camper_prefs["cabin"] == cabin,
                ].index.tolist()
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
                        problem += (
                            fleet_assignment[cabin][fleet] >= camper_assignments[c][s]
                        )

        # CONSTRAINTS:
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
                pulp.lpSum([camper_assignments[c][s] for c in self.campers])
                >= seatrade_campers_min,
                f"More_than_{seatrade_campers_min}_in_{s}",
            )
            seatrade_campers_max = self.seatrades_prefs.loc[seatrade, "campers_max"]
            problem += (
                pulp.lpSum([camper_assignments[c][s] for c in self.campers])
                <= seatrade_campers_max,
                f"Less_than_{seatrade_campers_max}_in_{s}",
            )
        # Constraint 4: Campers cannot be assigned un-requested seatrades.
        for c, seatrade_prefs in self.camper_prefs.items():
            problem += (
                pulp.lpSum(
                    [
                        camper_assignments[c][s]
                        for s in self.seatrades_full
                        if s[3:] not in seatrade_prefs
                    ]
                )
                == 0,
                f"{c}_prefers_not_these_seatrades.",
            )
        # Constraint 5: Campers guaranteed one of their top 2 choices.
        # In other words, they cannot be assigned 3rd and 4th choices together.
        for c, preferences in self.camper_prefs.items():
            problem += (
                pulp.lpSum(
                    # Use indicator function from assignment
                    # multiplied by linear preference penalty
                    # from index.
                    [
                        camper_assignments[c][f"1a_{s}"] * (preferences.index(s))
                        for s in preferences
                    ]
                    + [
                        camper_assignments[c][f"1b_{s}"] * (preferences.index(s))
                        for s in preferences
                    ]
                    + [
                        camper_assignments[c][f"2a_{s}"] * (preferences.index(s))
                        for s in preferences
                    ]
                    + [
                        camper_assignments[c][f"2b_{s}"] * (preferences.index(s))
                        for s in preferences
                    ]
                )
                <= 5 - 1,  # indexing of 0 means 3rd + 4th index is 5.
                f"{c} guaranteed one of the first two seatrades.",
            )
        # Constraint 6: For each seatrade, a cabin can contribute no
        # more than 4 campers.
        for s in self.seatrades_full:
            for cabin in self.cabins:
                cabin_campers = self.cabin_camper_prefs.loc[
                    self.cabin_camper_prefs["cabin"] == cabin
                ].index.tolist()
                problem += (
                    pulp.lpSum([camper_assignments[c][s] for c in cabin_campers]) <= 4,
                    f"{cabin} must contribute <= 4 campers to {s}.",
                )
        # # Constraint 7: Each cabin can only be assigned to a single
        # # fleet (cabin has to be assigned together).
        for fleet_blocks in [["1a", "1b"], ["2a", "2b"]]:
            for cabin in self.cabins:
                problem += (
                    pulp.lpSum([fleet_assignment[cabin][f] for f in fleet_blocks]) == 1,
                    f"{cabin}_in_only_1_fleet_{fleet_blocks}",
                )

        # OBJECTIVE:
        obj = 0
        # Penalize giving lower-preference seatrades.
        for c, preferences in self.camper_prefs.items():
            for block in ["1a", "1b", "2a", "2b"]:
                obj += preference_temperature * pulp.lpSum(
                    [
                        # Use indicator function from assignment
                        # multiplied by linear preference penalty
                        # from index.
                        camper_assignments[c][f"{block}_{s}"] * (preferences.index(s))
                        for s in preferences
                    ]
                )
        # Penalize for number of cabins assigned.
        # (Reward for assigning friends together).
        for s in self.seatrades_full:
            obj += cabins_temperature * pulp.lpSum(
                [cabin_assignments[cabin][s] for c in self.cabins]
            )

        problem += obj

        # Solve and save assignments:
        status = problem.solve()
        self.assignments = (
            pd.DataFrame(camper_assignments).applymap(pulp.value).transpose()
        )
        self.status = status
        return problem

    def get_assignments_by_cabin(self, assignments: pd.DataFrame) -> dict:
        """Get the assignments organized by Cabin -> Camper -> Seatrade."""
        raise NotImplementedError

    def get_assignments_by_seatrade(self, assignments: pd.DataFrame) -> dict:
        """Get the assignments organized by seatrade -> Cabin -> Camper."""
        raise NotImplementedError

    def wrangle_assignments_to_longform(
        self, assignments: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Melts the wide-form sparse dataframe into long-form, and adds column
        for camper preference scores of assigned seatrade.
        """
        df = (
            assignments.melt(
                var_name="seatrade", ignore_index=False, value_name="assignment"
            )
            .reset_index()
            .rename(columns={"index": "camper"})
        )

        def lookup_preference(row) -> int:
            """
            Returns the preference number of the
            seatrade for a given camper.
            If not selected due to infeasibility,
            returns 999.
            """
            if row.assignment:
                row_camper_prefs = self.camper_prefs[row.camper]
                if row.seatrade[3:] in row_camper_prefs:
                    pref_rank = row_camper_prefs.index(row.seatrade[3:]) + 1
                else:
                    pref_rank = 999
            else:
                pref_rank = 0
            return pref_rank

        df["preference"] = df.apply(lookup_preference, axis=1)

        def lookup_cabin(row) -> str:
            """
            Returns the cabin name that a camper is in.
            """
            camper = row.camper
            for campers, cabin in self.cabin_camper_prefs["cabin"].items():
                if camper in campers:
                    return cabin
            return None

        df["cabin"] = df.apply(lookup_cabin, axis=1)
        df[["block", "seatrade"]] = df["seatrade"].str.split("_", expand=True)

        return df

    def export_assignments_to_csv(self, filepath: str):
        """
        Exports the seatrade assignments to a CSV file at the
        given path.

        Parameters
        ----------
        filepath : str
           The str to the filepath to export the assignments to.
        """
        if not self.assigments:
            raise ValueError(
                "Seatrades.assignments not found."
                "Did you remember to run Seatrades.assign() first?"
            )
        raise NotImplementedError
