"""Configuration classes for the SeaTrades application."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd
import pulp
from pandera import DataFrameModel, Field, dataframe_check

SEATRADES_LOG_PATH = Path("seatrades_assignment.log")

NUM_PREFERENCES = 4
PREF_COLS = [f"seatrade_{i}" for i in range(1, NUM_PREFERENCES + 1)]


@dataclass
class OptimizationConfig:
    preference_weight: int = 3
    cabins_weight: int = 2
    sparsity_weight: int = 1
    max_seatrades_per_fleet: Optional[int] = None
    # When True (default), campers_min is a conditional minimum: a session runs with a
    # count in [min, max] or doesn't run (0 campers). When False, restores the legacy
    # hard floor that force-fills campers_min into every session. Not exposed in the UI.
    allow_empty_sessions: bool = True
    log_path: Path = SEATRADES_LOG_PATH
    # Accepts None as input, but __post_init__ guarantees a solver afterward —
    # typed non-Optional so callers (and mypy) can treat it as always present.
    solver: pulp.apis.LpSolver = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.solver is None:
            self.solver = pulp.apis.PULP_CBC_CMD(timeLimit=60, gapRel=0.10, logPath=self.log_path)


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
    def min_campers_less_than_max_campers(cls, df: pd.DataFrame) -> pd.Series:  # type: ignore[misc]
        """The minimum campers should be less than or equal to the maximum campers for a seatrade."""
        return df["campers_min"] <= df["campers_max"]


class CamperIdentity(DataFrameModel):
    """Camper identity data — cabin, name, gender."""

    cabin: str = Field(ignore_na=False)
    camper: str = Field(ignore_na=False)
    gender: str = Field(ignore_na=False)


RELATIONSHIP_TYPES = ["friends", "besties", "frenemies"]

# A besties pair needs two identical sessions, so its members must share at least
# this many preferred seatrades for the identical-schedule constraint to stay feasible.
BESTIES_MIN_SHARED_SEATRADES = 2

# A friends pair needs one shared session, so its members must share at least this
# many preferred seatrades to have any session they could both occupy.
FRIENDS_MIN_SHARED_SEATRADES = 1


class CamperRelationships(DataFrameModel):
    """Camper social relationships — pairs of campers with a relationship type.

    Each pair uses (cabin, camper) composite keys to match the camper identity
    domain model. ``relationship`` is one of friends, besties, or frenemies.
    """

    cabin_1: str = Field(ignore_na=False)
    camper_1: str = Field(ignore_na=False)
    cabin_2: str = Field(ignore_na=False)
    camper_2: str = Field(ignore_na=False)
    relationship: str = Field(isin=RELATIONSHIP_TYPES, ignore_na=False)


class CamperPreferences(DataFrameModel):
    """Camper seatrade preferences — ranked choices."""

    camper: str = Field(ignore_na=False)
    seatrade_1: str = Field(ignore_na=False)
    seatrade_2: str = Field(ignore_na=False)
    seatrade_3: str = Field(ignore_na=False)
    seatrade_4: str = Field(ignore_na=False)

    @dataframe_check
    def campers_must_choose_unique_seatrades(cls, df: pd.DataFrame) -> pd.Series:  # type: ignore[misc]
        """Each camper must choose NUM_PREFERENCES unique seatrades."""
        return df[PREF_COLS].nunique(axis="columns") == NUM_PREFERENCES
