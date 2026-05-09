"""Camper preferences tab — upload, validate, or simulate camper-seatrade preference data.

Pandera mypy suppressions:
- type: ignore[index] on SeatradesConfig bracket indexing (line ~164): pandera
  DataFrameModel subclasses are indexable DataFrames at runtime but mypy can't verify this.
- type: ignore[return-value] on CamperSeatradePreferences.validate (line ~209): pandera
  validate() returns DataFrame[X] but the function signature declares X. The runtime
  behavior is correct since validate() returns the validated DataFrame.

Revisit if pandera mypy plugin improves or pandas-stubs adds DataFrameModel support.
"""

from dataclasses import dataclass
from random import sample

import numpy as np
import pandas as pd
import streamlit as st
from faker import Faker
from pandera import Field

from seatrades import preferences
from seatrades_app.tabs.optimization_config_tab import _clear_optimization_results


@dataclass
class CamperSimulationConfig:
    num_cabins: int = 8
    num_preferences: int = 4
    camper_per_cabin_min: int = 8
    camper_per_cabin_max: int = 12


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


def _update_camper_simulation_config(camper_simulation_config: CamperSimulationConfig):
    """Update config for the mock data parameters."""
    if camper_simulation_config.camper_per_cabin_min >= camper_simulation_config.camper_per_cabin_max:
        st.toast(
            "Error updating simulation configuration.\n"
            " Camper per cabin min must be strictly less than camper per cabin max.\n"
            f"Instead found {camper_simulation_config.camper_per_cabin_min}"
            f" >= {camper_simulation_config.camper_per_cabin_max}.",
            icon="🚨",
        )
        return
    if st.session_state.get("camper_simulation_config") is not None:
        st.toast(f"Updating Camper Simulation Configuration.\n\n{camper_simulation_config}")
    st.session_state["camper_simulation_config"] = camper_simulation_config
    _clear_optimization_results()
    if "cabin_camper_prefs" in st.session_state:
        del st.session_state["cabin_camper_prefs"]


class CamperSimulationConfigTab:
    """Component: Simulation Config Form"""

    def generate(self):
        st.subheader("Camper Preferences")
        uploaded_camper_prefs = st.file_uploader(
            label="Upload your seatrade preferences for each camper.",
            type="csv",
            help="""Upload preferences as a .csv file.
            Uploaded data **must** have the same columns as seen below, and an example form
            can be downloaded by interacting with the displayed data below.
            Current camper preferences include their name, cabin, gender, as well as the top
            4 seatrades each camper wants to attend, in order.
            Seatrades must match the seatrades listed in the Seatrade Preferences tab, which
            are assumed to contain all seatrades for the week.
            """,
        )
        if uploaded_camper_prefs:
            camper_prefs_data = pd.read_csv(uploaded_camper_prefs, index_col=None)
            _validate_and_update_camper_preferences(camper_prefs_data)

        st.data_editor(st.session_state["cabin_camper_prefs"], disabled=True)

        st.write("")
        st.write("---")
        with st.expander("No Camper Data? Simulate Cabins Here."):
            with st.form("Camper Simulation Config", border=False):
                st.subheader("Camper Simulation Config")
                num_cabins = st.slider(
                    "num_cabins",
                    min_value=1,
                    max_value=len(ALL_CABIN_DICT),
                    value=CamperSimulationConfig().num_cabins,
                )
                camper_per_cabin_min = st.slider(
                    "camper_per_cabin_min",
                    min_value=1,
                    max_value=30,
                    value=CamperSimulationConfig().camper_per_cabin_min,
                )
                camper_per_cabin_max = st.slider(
                    "camper_per_cabin_max",
                    min_value=1,
                    max_value=30,
                    value=CamperSimulationConfig().camper_per_cabin_max,
                )
                num_preferences = st.slider(
                    "num_seatrade_preferences_per_camper",
                    min_value=1,
                    max_value=30,
                    value=CamperSimulationConfig().num_preferences,
                )

                camper_simulation_config = CamperSimulationConfig(
                    num_cabins=num_cabins,
                    num_preferences=num_preferences,
                    camper_per_cabin_min=camper_per_cabin_min,
                    camper_per_cabin_max=camper_per_cabin_max,
                )
                st.form_submit_button(
                    "Update Camper Simulation Settings",
                    on_click=_update_camper_simulation_config,
                    kwargs={"camper_simulation_config": camper_simulation_config},
                )


def _validate_and_update_camper_preferences(camper_preferences: pd.DataFrame):
    try:
        available_seatrades = st.session_state["seatrade_preferences"]["seatrade"].tolist()

        class UpdatedCamperPrefs(preferences.CamperSeatradePreferences):
            seatrade_1: str = Field(ignore_na=False, isin=available_seatrades)
            seatrade_2: str = Field(ignore_na=False, isin=available_seatrades)
            seatrade_3: str = Field(ignore_na=False, isin=available_seatrades)
            seatrade_4: str = Field(ignore_na=False, isin=available_seatrades)

        UpdatedCamperPrefs.validate(camper_preferences)
        st.session_state["cabin_camper_prefs"] = camper_preferences
        st.toast("Updating Camper Preferences.")
    except Exception as e:
        with st.popover(
            "Continuing without updating Camper Config. Click to see Error.",
            icon="🚨",
        ):
            st.write("Uploaded file does not meet expected schema. Error is as follows:")
            st.write(e)
            st.toast(
                "Continuing without updating Camper Config.",
                icon="🚨",
            )


def _simulate_cabin_camper_preferences(
    camper_simulation_config: CamperSimulationConfig,
    seatrade_preferences: preferences.SeatradesConfig,
) -> preferences.CamperSeatradePreferences:
    """Get our cabin-camper preferences for our optimization problem."""
    all_seatrades = seatrade_preferences["seatrade"].tolist()  # type: ignore[index]

    # Mock Cabins -- Assume bigender for now.
    cabins = sample(list(ALL_CABIN_DICT.keys()), k=camper_simulation_config.num_cabins)
    # cabins = [f"Cabin{i:0>2}" for i in range(camper_simulation_config.num_cabins)]

    # Mock Campers and Preferences
    camper_prefs = {}
    num_campers = 0
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
            # camper_name = f"Camper{num_campers:0>3}"
            camper_name = name_faker.name_male() if cabin_gender == "male" else name_faker.name_female()
            seatrade_prefs = sample(
                all_seatrades,
                camper_simulation_config.num_preferences,
            )
            cabin_info[camper_name] = seatrade_prefs
            num_campers += 1
        camper_prefs[cabin] = cabin_info

    cabin_camper_prefs = (
        pd.DataFrame(camper_prefs)
        .reset_index(names="camper")
        .melt(id_vars=["camper"], var_name="cabin", value_name="seatrade")
        .dropna(subset="seatrade")
        .reset_index(drop=True)
    )
    cabin_camper_prefs.loc[:, "gender"] = cabin_camper_prefs["cabin"].map(ALL_CABIN_DICT)

    # This is inefficient from a wrangling point of view but it's okay it's just to start.
    cabin_camper_prefs = cabin_camper_prefs.drop(columns="seatrade").join(
        pd.DataFrame(
            cabin_camper_prefs["seatrade"].to_list(),
            columns=[f"seatrade_{i + 1}" for i in range(camper_simulation_config.num_preferences)],
        )
    )
    return preferences.CamperSeatradePreferences.validate(cabin_camper_prefs)  # type: ignore[return-value]
