"""Configuration classes for the SeaTrades application."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd
import pulp
from pandera import DataFrameModel, Field, dataframe_check

SEATRADES_LOG_PATH = Path("seatrades_assignment.log")


@dataclass
class OptimizationConfig:
    preference_weight: int = 3
    cabins_weight: int = 2
    sparsity_weight: int = 1
    max_seatrades_per_fleet: Optional[int] = None
    solver: pulp.apis.LpSolver = pulp.apis.PULP_CBC_CMD(timeLimit=60, gapRel=0.10, logPath=SEATRADES_LOG_PATH)


@dataclass
class CamperSimulationConfig:
    num_cabins: int = 8
    num_preferences: int = 4
    camper_per_cabin_min: int = 8
    camper_per_cabin_max: int = 12


@dataclass
class SeatradeSimulationConfig:
    num_seatrades: int = 16
    camper_capacity_min: int = 8
    camper_capacity_max: int = 15


class SeatradesConfig(DataFrameModel):
    """Configuration preferences for the Seatrades for the week."""

    seatrade: str
    campers_min: int = Field(ge=0, coerce=True, ignore_na=False)
    campers_max: int = Field(ge=0, coerce=True, ignore_na=False)

    @dataframe_check
    def min_campers_less_than_max_campers(cls, df: pd.DataFrame):  # type: ignore[misc]
        """The minimum campers should be less than or equal to the maximum campers for a seatrade."""
        return df["campers_min"] <= df["campers_max"]


class CamperIdentity(DataFrameModel):
    """Camper identity data — cabin, name, gender."""

    cabin: str = Field(ignore_na=False)
    camper: str = Field(ignore_na=False)
    gender: str = Field(ignore_na=False)


class CamperPreferences(DataFrameModel):
    """Camper seatrade preferences — ranked choices."""

    camper: str = Field(ignore_na=False)
    seatrade_1: str = Field(ignore_na=False)
    seatrade_2: str = Field(ignore_na=False)
    seatrade_3: str = Field(ignore_na=False)
    seatrade_4: str = Field(ignore_na=False)

    @dataframe_check
    def campers_must_choose_4_unique_seatrades(cls, df: pd.DataFrame):  # type: ignore[misc]
        """Each camper must choose 4 unique seatrades."""
        return (
            (df["seatrade_1"] != df["seatrade_2"])
            & (df["seatrade_1"] != df["seatrade_3"])
            & (df["seatrade_1"] != df["seatrade_4"])
            & (df["seatrade_2"] != df["seatrade_3"])
            & (df["seatrade_2"] != df["seatrade_4"])
            & (df["seatrade_3"] != df["seatrade_4"])
        )


# Kept for backward compatibility during migration — will be removed.
class CamperSeatradePreferences(DataFrameModel):
    """Camper preferences for which seatrade they want to be assigned."""

    cabin: str = Field(ignore_na=False)
    camper: str = Field(ignore_na=False)
    gender: str = Field(ignore_na=False)
    seatrade_1: str = Field(ignore_na=False)
    seatrade_2: str = Field(ignore_na=False)
    seatrade_3: str = Field(ignore_na=False)
    seatrade_4: str = Field(ignore_na=False)

    @dataframe_check
    def campers_must_choose_4_unique_seatrades(cls, df: pd.DataFrame):  # type: ignore[misc]
        """Each camper must choose 4 unique seatrades."""
        return (
            (df["seatrade_1"] != df["seatrade_2"])
            & (df["seatrade_1"] != df["seatrade_3"])
            & (df["seatrade_1"] != df["seatrade_4"])
            & (df["seatrade_2"] != df["seatrade_3"])
            & (df["seatrade_2"] != df["seatrade_4"])
            & (df["seatrade_3"] != df["seatrade_4"])
        )
