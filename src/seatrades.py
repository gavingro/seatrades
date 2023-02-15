from typing import Dict, Literal, List, Optional
from time import time
import logging

import pulp
import pandas as pd
import altair as alt


class Seatrades:
    """A class to handle LP problems to solve seatrade assignment."""

    def __init__(
        self,
        camper_prefs: Dict[str, Dict[str, List[str]]],
        seatrades_prefs: Dict[str, Dict[str, int]],
    ):
        """
        A class to handle LP problems to solve seatrade assignment.

        Parameters
        ----------
        camper_prefs : dict
            A json-like dict containing the camper-cabin-seatrade
            preferences information.
        seatrades_prefs : dict
            A json-like dict containing the seatrade-minsize-maxsize
            information.
        """
        def flatten(outer_list: List[list]):
            """Flattens the 2d input list into 1d."""
            return [item for sublist in outer_list for item in sublist]

        self.camper_prefs = camper_prefs
        self.seatrades_prefs = seatrades_prefs
        # Seatrades for block 1 and block 2.
        self.seatrades = list(seatrades_prefs.keys())
        self.seatrades1 = [f"1_{seatrade}" for seatrade in self.seatrades]
        self.seatrades2 = [f"2_{seatrade}" for seatrade in self.seatrades]
        self.seatrades_full = self.seatrades1 + self.seatrades2
        self.cabins = list(camper_prefs.keys())
        self.campers = flatten(
            [list(cabin.keys()) for cabin in list(camper_prefs.values())]
        )
        self.assignments: pd.DataFrame

    def assign(self) -> pd.DataFrame:
        """
        Uses the objects campers_df and seatrades_df to solve a Linear Programming
        problem to assign each camper to their ideal seatrades while respecting
        size constraints.

        Details found in documentation/seatrades_assignment_math.md.

        Returns
        -------
        pd.DataFrame
            A matrix of binary 1's and 0's (assigned or not assigned) representing
            the assignment of campers (Y Axis) to seatrades in block 1 or 2 (X Axis).
        """
        # Setup problem and parameters.
        problem = pulp.LpProblem(name="seatrades_assignment")
        assignments = pulp.LpVariable.dicts(
            "Assignment", 
            (self.campers, self.seatrades_full),
            lowBound=0,
            upBound=1,
            cat=pulp.LpInteger
        )
        
        # CONSTRAINTS:
        # Constraint 1: Each camper is assigned 1 seatrade in each of 2 blocks.
        for block_index, seatrades in enumerate([self.seatrades1, self.seatrades2]):
            for c in self.campers:
                problem += (
                    pulp.lpSum([assignments[c][s] for s in seatrades]) == 1,
                    f"{c}_in_only_1_seatrade_{block_index}"
                )
        #Constraint 2: Each seatrade is assigned between min and max campers.
        for s in self.seatrades_full:
            seatrade = s[2:] # Remove block index for matching.
            problem += (
                pulp.lpSum([assignments[c][s] for c in self.campers]) 
                >= self.seatrades_prefs[seatrade]["campers_min"],
                f"More_than_{self.seatrades_prefs[seatrade]['campers_min']}_in_{s}"
            )
            problem += (
                pulp.lpSum([assignments[c][s] for c in self.campers]) 
                <= self.seatrades_prefs[seatrade]["campers_max"],
                f"Less_than_{self.seatrades_prefs[seatrade]['campers_max']}_in_{s}"
            )
        #Constraint 3: Campers cannot be assigned un-requested seatrades.
        for campers in self.camper_prefs.values():
            for c, seatrade_prefs in campers.items():
                problem += (
                    pulp.lpSum([
                        assignments[c][s] for s in self.seatrades_full 
                        if s[2:] not in seatrade_prefs  # Remove block index.
                    ]),
                    f"{c}_prefers_not_{s}"
                )

        #OBJECTIVE:
        obj = 0
        #Penalize giving lower-preference seatrades.
        for cabin, campers in self.camper_prefs.items():
            for c, preferences in campers.items():
                for block in [1, 2]:
                    obj += (
                        pulp.lpSum(
                            [
                                # Use indicator function from assignment 
                                # multiplied by linear preference penalty
                                # from index.
                                assignments[c][f"{block}_{s}"] 
                                * (preferences.index(s)) 
                                for s in preferences
                            ]
                        )
                    )
        problem += obj
        
        # Solve:
        status = problem.solve()

        self.assignments = pd.DataFrame(assignments).applymap(pulp.value).transpose()
        return self.assignments

    def get_assignments_by_cabin(self, assignments: pd.DataFrame) -> dict:
        """Get the assignments organized by Cabin -> Camper -> Seatrade."""
        ...

    def get_assignments_by_seatrade(self, assignments: pd.DataFrame) -> dict:
        """Get the assignments organized by seatrade -> Cabin -> Camper."""
        ...

    def wrangle_assignments_to_longform(
        self, assignments: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Melts the wide-form sparse dataframe into long-form, and adds column
        for camper preference scores of assigned seatrade.
        """
        ...

    def display_assignments(self, assignments: pd.DataFrame) -> alt.Chart:
        """
        Displays the assignments of the seatrades visually for inference.
        """
        ...

    def export_assignments_to_csv(self, filepath: str = "assignments.csv"):
        """
        Exports the seatrade assignments to a CSV file at the
        given path.

        Parameters
        ----------
        filepath : str
           The str to the filepath to export the assignments to.
        """
        ...
