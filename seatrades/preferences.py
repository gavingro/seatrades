"""
This file contains logic and data objects capturing the preferences of campers
and camp staff towards seatrades.

Pandera mypy suppressions:
- type: ignore[misc] on @dataframe_check methods (lines ~19, ~37): pandera's
  @dataframe_check decorator uses cls as first arg, which mypy doesn't recognize
  as a valid classmethod pattern.
- type: ignore[attr-defined] on CamperSeatradePreferences.loc and .index (line ~54):
  pandera DataFrameModel subclasses are DataFrames at runtime but mypy can't
  verify DataFrame attribute access on them.

Revisit if pandera mypy plugin improves or pandas-stubs adds DataFrameModel support.
"""

import pandas as pd
from pandera import DataFrameModel, Field, dataframe_check


class SeatradesConfig(DataFrameModel):
    """Object to collect the configuration preferences for the Seatrades for
    the week."""

    seatrade: str
    campers_min: int = Field(ge=0, coerce=True, ignore_na=False)
    campers_max: int = Field(ge=0, coerce=True, ignore_na=False)

    @dataframe_check
    def min_campers_less_than_max_campers(cls, df: pd.DataFrame):  # type: ignore[misc]
        """The minimum campers should be less than or equal to the the maximum campers for a seatrade."""
        return df["campers_min"] <= df["campers_max"]


class CamperSeatradePreferences(DataFrameModel):
    """Objects to collect the camper preferences for which seatrade they want
    to be assigned."""

    cabin: str = Field(ignore_na=False)
    camper: str = Field(ignore_na=False)
    gender: str = Field(ignore_na=False)
    seatrade_1: str = Field(ignore_na=False)
    seatrade_2: str = Field(ignore_na=False)
    seatrade_3: str = Field(ignore_na=False)
    seatrade_4: str = Field(ignore_na=False)

    @dataframe_check
    def campers_must_choose_4_unique_seatrades(cls, df: pd.DataFrame):  # type: ignore[misc]
        """The minimum campers should be less than or equal to the the maximum campers for a seatrade."""
        return (
            (df["seatrade_1"] != df["seatrade_2"])
            & (df["seatrade_1"] != df["seatrade_2"])
            & (df["seatrade_1"] != df["seatrade_3"])
            & (df["seatrade_1"] != df["seatrade_4"])
            & (df["seatrade_2"] != df["seatrade_3"])
            & (df["seatrade_2"] != df["seatrade_4"])
            & (df["seatrade_3"] != df["seatrade_4"])
        )


def add_index_to_campername(
    camper_prefs: CamperSeatradePreferences,
) -> CamperSeatradePreferences:
    """Add index to Camper Names within the prefrence object to avoid name collisions."""
    camper_prefs.loc[:, "camper"] += "." + camper_prefs.index.astype(str)  # type: ignore[attr-defined]
    return camper_prefs
