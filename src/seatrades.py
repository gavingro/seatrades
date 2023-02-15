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
        self.camper_prefs = camper_prefs
        self.seatrades_prefs = seatrades_prefs

    def assign_seatrades(self) -> pd.DataFrame:
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
        ...

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
