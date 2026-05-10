"""Simulation data generators for Seatrades — produces DataFrames matching real upload schemas.

No Streamlit imports. All generators are pure functions that take config objects
and return validated pandas DataFrames.
"""

from random import sample

import numpy as np
import pandas as pd
from faker import Faker

from seatrades import preferences
from seatrades.config import CamperSimulationConfig, SeatradeSimulationConfig

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
    import random

    seatrade_name_sample = random.sample(SEATRADE_EXAMPLES, k=config.num_seatrades)

    seatrades_prefs_dict = {
        f"{seatrade}": {
            "campers_min": (temp := np.random.randint(0, 2)),
            "campers_max": temp
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
    cabins = sample(list(ALL_CABIN_DICT.keys()), k=camper_simulation_config.num_cabins)
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
        prefs = sample(all_seatrades, 4)
        rows.append(
            {
                "camper": name,
                "seatrade_1": prefs[0],
                "seatrade_2": prefs[1],
                "seatrade_3": prefs[2],
                "seatrade_4": prefs[3],
            }
        )

    result = pd.DataFrame(rows)
    return preferences.CamperPreferences.validate(result)  # type: ignore[return-value]


def simulate_cabin_camper_preferences(
    camper_simulation_config: CamperSimulationConfig,
    seatrade_preferences: pd.DataFrame,
) -> pd.DataFrame:
    """Generate simulated cabin-camper preferences DataFrame.

    seatrade_preferences should be a SeatradesConfig-conforming DataFrame
    (e.g. from simulate_seatrade_preferences) — used to pick valid seatrade names.
    """
    all_seatrades = seatrade_preferences["seatrade"].tolist()  # type: ignore[index]

    cabins = sample(list(ALL_CABIN_DICT.keys()), k=camper_simulation_config.num_cabins)

    camper_prefs = {}
    name_faker = Faker(locale=["en", "es", "it_IT", "fr_FR", "fr_QC"])
    for cabin in cabins:
        cabin_info = {}
        cabin_gender = ALL_CABIN_DICT[cabin]
        for _camper in range(
            np.random.randint(
                camper_simulation_config.camper_per_cabin_min,
                camper_simulation_config.camper_per_cabin_max,
            )
        ):
            camper_name = name_faker.name_male() if cabin_gender == "male" else name_faker.name_female()
            seatrade_prefs = sample(
                all_seatrades,
                camper_simulation_config.num_preferences,
            )
            cabin_info[camper_name] = seatrade_prefs
        camper_prefs[cabin] = cabin_info

    cabin_camper_prefs = (
        pd.DataFrame(camper_prefs)
        .reset_index(names="camper")
        .melt(id_vars=["camper"], var_name="cabin", value_name="seatrade")
        .dropna(subset="seatrade")
        .reset_index(drop=True)
    )
    cabin_camper_prefs.loc[:, "gender"] = cabin_camper_prefs["cabin"].map(ALL_CABIN_DICT)

    cabin_camper_prefs = cabin_camper_prefs.drop(columns="seatrade").join(
        pd.DataFrame(
            cabin_camper_prefs["seatrade"].to_list(),
            columns=[f"seatrade_{i + 1}" for i in range(camper_simulation_config.num_preferences)],
        )
    )
    return preferences.CamperSeatradePreferences.validate(cabin_camper_prefs)  # type: ignore[return-value]
