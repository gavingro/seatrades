"""
This file contains logic and data objects capturing the preferences of campers
and camp staff towards seatrades.
"""

from pandera import DataFrameModel


class SeatradesConfig(DataFrameModel):
    """Object to collect the configuration preferences for the Seatrades for
    the week."""

    seatrade: str
    campers_min: int
    campers_max: int


class CamperSeatradePreferences(DataFrameModel):
    """Objects to collect the camper preferences for which seatrade they want
    to be assigned."""

    cabin: str
    camper: str
    gender: str
    seatrade_1: str
    seatrade_2: str
    seatrade_3: str
    seatrade_4: str
