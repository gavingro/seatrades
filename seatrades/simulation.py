"""Simulation data generators for Seatrades — produces DataFrames matching real upload schemas.

No Streamlit imports. All generators are pure functions that take config objects
and return validated pandas DataFrames.
"""

import random

import numpy as np
import pandas as pd
from faker import Faker

from seatrades import preferences
from seatrades.config import (
    NUM_PREFERENCES,
    PREF_COLS,
    CamperRelationships,
    CamperSimulationConfig,
    SeatradeSimulationConfig,
)

# A besties pair needs two identical sessions, so its members must share >= 2
# preferred seatrades for the identical-schedule constraint to stay feasible.
_BESTIES_MIN_SHARED_SEATRADES = 2

_RELATIONSHIP_COLUMNS = ["cabin_1", "camper_1", "cabin_2", "camper_2", "relationship"]

# Real cabin names from Keats Camp
GIRL_CABIN_EXAMPLES = [
    "Puffin",
    "Pelican",
    "Merganser",
    "Kingfisher",
    "Cormorant",
    "Britannia",
    "Acadia",
    "Sovereign",
    "Bounty",
    "Santa Maria",
]
BOY_CABIN_EXAMPLES = [
    "Tillikum",
    "Caledonia",
    "Girona",
    "Grafton",
    "Spindrift",
    "Amherst",
    "Buonaventure",
    "Columbia",
    "Terra Nova",
]
ALL_CABIN_DICT = {cabin: "female" for cabin in GIRL_CABIN_EXAMPLES} | {cabin: "male" for cabin in BOY_CABIN_EXAMPLES}

SEATRADE_EXAMPLES = [
    "Low Ropes",
    "High Ropes",
    "Giant Swing",
    "Laser Tag",
    "Frisbee Golf",
    "Field Sports",
    "Climbing",
    "Crafts",
    "Archery",
    "Seal Spotting",
    "Wakeboarding",
    "Tubing",
    "Swimming",
    "Sailing",
    "Paddleboarding",
    "Canoeing and Kayaking",
    "Wibit",
]


def simulate_seatrade_preferences(
    config: SeatradeSimulationConfig,
) -> pd.DataFrame:
    """Generate simulated seatrade preferences DataFrame."""
    seatrade_name_sample = random.sample(SEATRADE_EXAMPLES, k=config.num_seatrades)

    seatrades_prefs_dict = {
        seatrade: {
            "campers_min": (base_min := np.random.randint(0, 2)),
            "campers_max": base_min
            + (
                np.random.randint(
                    config.camper_capacity_min,
                    config.camper_capacity_max,
                )
            ),
        }
        for seatrade in seatrade_name_sample
    }
    seatrades_prefs = pd.DataFrame(seatrades_prefs_dict).T.reset_index(names="seatrade")
    return preferences.SeatradesConfig.validate(seatrades_prefs)  # type: ignore[return-value]


def simulate_camper_identity(
    camper_simulation_config: CamperSimulationConfig,
) -> pd.DataFrame:
    """Generate simulated camper identity DataFrame (cabin, camper, gender)."""
    cabins = random.sample(list(ALL_CABIN_DICT.keys()), k=camper_simulation_config.num_cabins)
    name_faker = Faker(locale=["en", "es", "it_IT", "fr_FR", "fr_QC"])

    rows = []
    for cabin in cabins:
        cabin_gender = ALL_CABIN_DICT[cabin]
        for _ in range(
            np.random.randint(
                camper_simulation_config.camper_per_cabin_min,
                camper_simulation_config.camper_per_cabin_max,
            )
        ):
            name = name_faker.name_male() if cabin_gender == "male" else name_faker.name_female()
            rows.append({"cabin": cabin, "camper": name, "gender": cabin_gender})

    result = pd.DataFrame(rows)
    return preferences.CamperIdentity.validate(result)  # type: ignore[return-value]


def simulate_camper_preferences(
    identity_df: pd.DataFrame,
    seatrade_preferences: pd.DataFrame,
) -> pd.DataFrame:
    """Generate simulated camper preferences DataFrame (camper, seatrade_1..4).

    identity_df should come from simulate_camper_identity — camper names are
    taken from it to guarantee a match between identity and preferences.

    seatrade_preferences should be a SeatradesConfig-conforming DataFrame
    (e.g. from simulate_seatrade_preferences) — used to pick valid seatrade names.
    """
    all_seatrades = seatrade_preferences["seatrade"].tolist()  # type: ignore[index]

    rows = []
    for name in identity_df["camper"]:
        prefs = random.sample(all_seatrades, NUM_PREFERENCES)
        rows.append({"camper": name} | {col: prefs[i] for i, col in enumerate(PREF_COLS)})

    result = pd.DataFrame(rows)
    return preferences.CamperPreferences.validate(result)  # type: ignore[return-value]


def simulate_camper_relationships(
    identity_df: pd.DataFrame,
    preferences_df: pd.DataFrame,
) -> pd.DataFrame:
    """Generate one mock besties pair, guaranteed solver-feasible.

    Picks the first same-cabin pair of campers sharing at least two preferred
    seatrades. A same-cabin pair avoids fleet-balance conflicts at any cabin count,
    and the shared preferences make an identical schedule achievable — so the seeded
    besties relationship always solves. Returns an empty (but schema-valid)
    CamperRelationships frame if no such pair exists.
    """
    merged = identity_df.merge(preferences_df, on="camper")
    for cabin, group in merged.groupby("cabin"):
        members = list(group.itertuples(index=False))
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                shared = {getattr(a, col) for col in PREF_COLS} & {getattr(b, col) for col in PREF_COLS}
                if len(shared) >= _BESTIES_MIN_SHARED_SEATRADES:
                    row = pd.DataFrame(
                        [
                            {
                                "cabin_1": cabin,
                                "camper_1": a.camper,
                                "cabin_2": cabin,
                                "camper_2": b.camper,
                                "relationship": "besties",
                            }
                        ]
                    )
                    return CamperRelationships.validate(row)  # type: ignore[return-value]

    empty = pd.DataFrame({col: pd.Series(dtype="object") for col in _RELATIONSHIP_COLUMNS})
    return CamperRelationships.validate(empty)  # type: ignore[return-value]
