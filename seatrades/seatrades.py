"""
This file contains tools to assign seatrades to campers based on their preferences.
"""

from typing import Dict, Literal, List, Optional
from time import time
import logging

import pulp
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
        self.seatrades1 = [f"1_{seatrade}" for seatrade in self.seatrades]
        self.seatrades2 = [f"2_{seatrade}" for seatrade in self.seatrades]
        self.seatrades_full = self.seatrades1 + self.seatrades2
        self.assignments: pd.DataFrame

    # Helper Function
    def _flatten(self, outer_list: List[list]):
        """Flattens the 2d input list into 1d."""
        return {
            key: value
            for inner_dict in outer_list.values()
            for key, value in inner_dict.items()
        }

    def assign(self) -> int:
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
        assignments = pulp.LpVariable.dicts(
            "Assignment",
            (self.campers, self.seatrades_full),
            lowBound=0,
            upBound=1,
            cat=pulp.LpInteger,
        )

        # CONSTRAINTS:
        # Constraint 1: Each camper is assigned 1 seatrade in each of 2 blocks.
        for block_index, seatrades in enumerate([self.seatrades1, self.seatrades2]):
            for c in self.campers:
                problem += (
                    pulp.lpSum([assignments[c][s] for s in seatrades]) == 1,
                    f"{c}_in_only_1_seatrade_block_{block_index}",
                )
        # Constraint 2: Each camper cannot be assigned the same seatrade
        # in both blocks.
        for s1, s2 in zip(self.seatrades1, self.seatrades2):
            for c in self.campers:
                problem += (
                    pulp.lpSum([assignments[c][s1], assignments[c][s2]]) <= 1,
                    f"{c} can't take {s1[2:]} in both blocks",
                )
        # Constraint 3: Each seatrade is assigned between min and max campers.
        for s in self.seatrades_full:
            seatrade = s[2:]  # Remove block index for matching.
            seatrade_campers_min = self.seatrades_prefs.loc[seatrade, "campers_min"]
            problem += (
                pulp.lpSum([assignments[c][s] for c in self.campers])
                >= seatrade_campers_min,
                f"More_than_{seatrade_campers_min}_in_{s}",
            )
            seatrade_campers_max = self.seatrades_prefs.loc[seatrade, "campers_max"]
            problem += (
                pulp.lpSum([assignments[c][s] for c in self.campers])
                <= seatrade_campers_max,
                f"Less_than_{seatrade_campers_max}_in_{s}",
            )
        # Constraint 4: Campers cannot be assigned un-requested seatrades.
        for c, seatrade_prefs in self.camper_prefs.items():
            problem += (
                pulp.lpSum(
                    [
                        assignments[c][s]
                        for s in self.seatrades_full
                        if s[2:] not in seatrade_prefs
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
                        assignments[c][f"1_{s}"] * (preferences.index(s))
                        for s in preferences
                    ]
                    + [
                        assignments[c][f"2_{s}"] * (preferences.index(s))
                        for s in preferences
                    ]
                )
                <= 4,  # indexing of 0 means 3rd + 4th index is 5.
                f"{c} guaranteed one of the first two seatrades.",
            )

        # OBJECTIVE:
        obj = 0
        # Penalize giving lower-preference seatrades.
        for c, preferences in self.camper_prefs.items():
            for block in [1, 2]:
                obj += pulp.lpSum(
                    [
                        # Use indicator function from assignment
                        # multiplied by linear preference penalty
                        # from index.
                        assignments[c][f"{block}_{s}"] * (preferences.index(s))
                        for s in preferences
                    ]
                )
        problem += obj

        # Solve and save assignments:
        status = problem.solve()
        self.assignments = pd.DataFrame(assignments).applymap(pulp.value).transpose()
        self.status = status
        return self.status

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
                if row.seatrade[2:] in row_camper_prefs:
                    pref_rank = row_camper_prefs.index(row.seatrade[2:]) + 1
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
