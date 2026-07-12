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


def cabin_seat_cap(share: float, campers_max: int) -> int:
    """One cabin's per-seatrade seat cap under the opt-in ``max_cabin_share_per_seatrade``.

    Floored at 1 so a tiny-capacity seatrade (where ``round`` would give 0) never
    becomes unfillable. Shared by the solver constraint that *enforces* the cap
    (``_add_cabin_share_cap_constraints``) and the diagnostics post-mortem that
    *explains* it, so the two can never round it differently.
    """
    return max(1, round(share * campers_max))


@dataclass
class OptimizationConfig:
    preference_weight: int = 4
    cabins_weight: int = 3
    sparsity_weight: int = 2
    # Soft age-grouping penalty. age_weight defaults ON at a low weight (like
    # sparsity_weight): the always-present age data nudges the solver toward tighter
    # age spread. age_balance splits emphasis between the session level (per
    # block_seatrade) and the fleet level (per block); 0.5 = balanced.
    age_weight: int = 1
    age_balance: float = 0.5
    # Soft penalty discouraging one cabin from dominating a seatrade. Each seatrade gives
    # a free threshold of round(0.25 * campers_max); each camper a cabin places beyond it
    # adds penalty. Defaults ON at a modest weight; 0 disables. The direct counterweight to
    # cabins_weight (cabin togetherness).
    cabin_variety_weight: int = 3
    # Optional hard cap on any one cabin's share of a seatrade's capacity, in [0.25, 1.0].
    # Default 1.0 = OFF (constraint not added). Below 1.0, caps a cabin at
    # round(share * campers_max) campers per seatrade.
    max_cabin_share_per_seatrade: float = 1.0
    max_seatrades_per_fleet: Optional[int] = None
    # When True (default), campers_min is a conditional minimum: a session runs with a
    # count in [min, max] or doesn't run (0 campers). When False, restores the legacy
    # hard floor that force-fills campers_min into every session. Not exposed in the UI.
    allow_empty_sessions: bool = True
    # When True, force each cabin into the same fleet (AM/PM) across both halves of the
    # week — a cabin that is Morning in the first half stays Morning in the second (and
    # Afternoon stays Afternoon). When False (default), the solver picks each cabin's
    # fleet per half independently. Opt-in hard constraint; reproduces the legacy
    # hand-scheduled arrangement.
    force_same_fleet_all_week: bool = False
    log_path: Path = SEATRADES_LOG_PATH
    # Accepts None as input, but __post_init__ guarantees a solver afterward —
    # typed non-Optional so callers (and mypy) can treat it as always present.
    solver: pulp.apis.LpSolver = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.solver is None:
            self.solver = pulp.apis.PULP_CBC_CMD(timeLimit=120, gapRel=0.10, logPath=self.log_path)


@dataclass
class CamperSimulationConfig:
    num_cabins: int = 8
    num_preferences: int = 4
    camper_per_cabin_min: int = 8
    camper_per_cabin_max: int = 12
    # Bounds on each cabin's *base* age, drawn uniformly per cabin. Per-camper jitter
    # (normal spread) rides on top and may land just outside these bounds.
    base_age_min: int = 13
    base_age_max: int = 16
    age_spread: float = 0.7


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
    """Camper identity data — cabin, name, gender, age."""

    cabin: str = Field(ignore_na=False)
    camper: str = Field(ignore_na=False)
    gender: str = Field(ignore_na=False)
    age: int = Field(ge=1, coerce=True, ignore_na=False)


RELATIONSHIP_TYPES = ["friends", "besties", "frenemies"]

# A besties pair needs two identical sessions, so its members must share at least
# this many preferred seatrades for the identical-schedule constraint to stay feasible.
BESTIES_MIN_SHARED_SEATRADES = 2

# A friends pair needs one shared session, so its members must share at least this
# many preferred seatrades to have any session they could both occupy.
FRIENDS_MIN_SHARED_SEATRADES = 1

# --- Suspected-tier placeholder thresholds (issue #114) ----------------------
# Cutoffs for the advisory "pressure" hints the diagnostics post-mortem shows on an
# INFEASIBLE solve. These are deliberately CONSERVATIVE placeholders — chosen to err
# toward silence so a hint never fires on comfortably-feasible input. Research spike
# #115 replaces the values empirically; the checks read these constants, so the spike
# tunes numbers without reshaping the checks.

# Top-2 oversubscription: a seatrade is under pressure when the campers who rank it
# first or second outnumber its half-week seats (2·campers_max) by at least this factor.
SUSPECTED_TOP2_OVERSUBSCRIPTION_FACTOR = 1.5

# Cabin clustering: a cabin funnels its cohesion into one seatrade when at least this
# share of the cabin ranks the same seatrade *first* — pressure only when that seatrade
# also can't seat the whole cabin across both its blocks (2·campers_max). A per-cabin
# cohesion pressure, distinct from the global top-2 scarcity signal above. Floored to a
# substantial cohesive group (real cabins are 8–12) so a tiny cabin never cries wolf.
SUSPECTED_CABIN_CLUSTERING_SHARE = 0.75
SUSPECTED_CABIN_CLUSTERING_MIN_CAMPERS = 8

# Cross-cabin frenemies overlap: a frenemies group spanning cabins is under pressure
# when its size reaches this multiple of the distinct seatrades its members rank.
SUSPECTED_FRENEMIES_CLUSTERING_RATIO = 1.0

# Gender-balance vs. the same-fleet-all-week lock: with force_same_fleet_all_week ON,
# one gender holding at least this share of cabins strains the even split across fleets.
SUSPECTED_GENDER_DOMINANCE_SHARE = 0.75

# Balance vs. minimum: gender balance splits a seatrade's demand across ~2 blocks, so a
# live seatrade whose popularity is under this multiple of its campers_min risks falling
# below the floor in a block once split.
SUSPECTED_BALANCE_MIN_POPULARITY_FACTOR = 2.0


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
