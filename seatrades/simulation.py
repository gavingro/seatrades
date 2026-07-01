"""Simulation data generators for Seatrades — produces DataFrames matching real upload schemas.

No Streamlit imports. All generators are pure functions that take config objects
and return validated pandas DataFrames.
"""

import random
from typing import Callable, NamedTuple, Optional

import numpy as np
import pandas as pd
from faker import Faker

from seatrades import preferences
from seatrades.config import (
    BESTIES_MIN_SHARED_SEATRADES,
    FRIENDS_MIN_SHARED_SEATRADES,
    NUM_PREFERENCES,
    PREF_COLS,
    CamperSimulationConfig,
    SeatradeSimulationConfig,
)

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
        # One base age per cabin (inclusive of both bounds) so cabins cluster in age
        # but the camp still spans younger and older cabins.
        base_age = np.random.randint(
            camper_simulation_config.base_age_min,
            camper_simulation_config.base_age_max + 1,
        )
        for _ in range(
            np.random.randint(
                camper_simulation_config.camper_per_cabin_min,
                camper_simulation_config.camper_per_cabin_max,
            )
        ):
            name = name_faker.name_male() if cabin_gender == "male" else name_faker.name_female()
            # Jitter around the cabin base; no clamp to the base range, only stay positive.
            age = max(1, int(base_age + round(np.random.normal(0, camper_simulation_config.age_spread))))
            rows.append({"cabin": cabin, "camper": name, "gender": cabin_gender, "age": age})

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


class Camper(NamedTuple):
    """A camper's identity and preferred seatrades, for pair selection."""

    cabin: str
    name: str
    prefs: set[str]

    @property
    def key(self) -> tuple[str, str]:
        return (self.cabin, self.name)


def simulate_camper_relationships(
    identity_df: pd.DataFrame,
    preferences_df: pd.DataFrame,
) -> pd.DataFrame:
    """Generate one mock pair of each relationship type, guaranteed solver-feasible.

    Each pair uses distinct campers, so the three constraints can never form a
    contradictory friend/frenemy chain. The pairs are picked to stay individually
    feasible: besties and friends from a same-cabin pair (always the same fleet, so a
    shared schedule/session is achievable) sharing enough preferred seatrades, and
    frenemies from a cross-cabin pair (separable into different fleets, so they need
    never overlap). Any type with no qualifying pair is skipped; an empty (but
    schema-valid) frame is returned when none can be seeded.
    """
    merged = identity_df.merge(preferences_df, on="camper")
    campers = [
        Camper(str(row.cabin), str(row.camper), {getattr(row, col) for col in PREF_COLS})
        for row in merged.itertuples(index=False)
    ]
    used: set[tuple[str, str]] = set()

    def reserve_pair(
        predicate: Callable[[Camper, Camper], bool],
    ) -> Optional[tuple[tuple[str, str], tuple[str, str]]]:
        """Return the first unused pair matching predicate and mark both campers used.

        Mutates ``used`` so later calls can't reuse a camper — distinct campers per
        pair preclude contradictory friend/frenemy chains.
        """
        for i in range(len(campers)):
            for j in range(i + 1, len(campers)):
                a, b = campers[i], campers[j]
                if a.key in used or b.key in used or not predicate(a, b):
                    continue
                used.update({a.key, b.key})
                return a.key, b.key
        return None

    def same_cabin(a: Camper, b: Camper) -> bool:
        return a.cabin == b.cabin

    def shared(a: Camper, b: Camper) -> int:
        return len(a.prefs & b.prefs)

    # Order is load-bearing: besties reserves first because its ≥2-shared pairs are
    # scarcer than friends' ≥1-shared pairs; reordering could starve besties.
    selections = {
        "besties": reserve_pair(lambda a, b: same_cabin(a, b) and shared(a, b) >= BESTIES_MIN_SHARED_SEATRADES),
        "friends": reserve_pair(lambda a, b: same_cabin(a, b) and shared(a, b) >= FRIENDS_MIN_SHARED_SEATRADES),
        "frenemies": reserve_pair(lambda a, b: not same_cabin(a, b)),
    }

    rows = [
        {
            "cabin_1": pair[0][0],
            "camper_1": pair[0][1],
            "cabin_2": pair[1][0],
            "camper_2": pair[1][1],
            "relationship": relationship,
        }
        for relationship, pair in selections.items()
        if pair is not None
    ]
    if not rows:
        return preferences.empty_relationships()
    return preferences.CamperRelationships.validate(pd.DataFrame(rows))  # type: ignore[return-value]
