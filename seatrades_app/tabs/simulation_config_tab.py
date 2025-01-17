from dataclasses import dataclass

import numpy as np
import pandas as pd
from random import sample
from seatrades import preferences
from seatrades_app.tabs.optimization_config_tab import _clear_optimization_results


import streamlit as st


@dataclass
class SimulationConfig:
    num_seatrades: int = 16
    num_cabins: int = 8
    num_preferences: int = 4
    camper_per_seatrade_min: int = 8
    camper_per_seatrade_max: int = 15
    camper_per_cabin_min: int = 8
    camper_per_cabin_max: int = 12


class SimulationConfigTab:
    """Component: Simulation Config Form"""

    def generate(self):
        with st.form("Simulation Config") as simulation_config_form:
            st.header("Simulation Config")
            num_seatrades = st.slider(
                "num_seatrades",
                min_value=1,
                max_value=30,
                value=SimulationConfig().num_seatrades,
            )
            num_cabins = st.slider(
                "num_cabins",
                min_value=1,
                max_value=30,
                value=SimulationConfig().num_cabins,
            )
            num_preferences = st.slider(
                "num_preferences",
                min_value=1,
                max_value=30,
                value=SimulationConfig().num_preferences,
            )
            camper_per_seatrade_min = st.slider(
                "camper_per_seatrade_min",
                min_value=1,
                max_value=30,
                value=SimulationConfig().camper_per_seatrade_min,
            )
            camper_per_seatrade_max = st.slider(
                "camper_per_seatrade_max",
                min_value=1,
                max_value=30,
                value=SimulationConfig().camper_per_seatrade_max,
            )
            camper_per_cabin_min = st.slider(
                "camper_per_cabin_min",
                min_value=1,
                max_value=30,
                value=SimulationConfig().camper_per_cabin_min,
            )
            camper_per_cabin_max = st.slider(
                "camper_per_cabin_max",
                min_value=1,
                max_value=30,
                value=SimulationConfig().camper_per_cabin_max,
            )

            simulation_config = SimulationConfig(
                num_seatrades=num_seatrades,
                num_cabins=num_cabins,
                num_preferences=num_preferences,
                camper_per_seatrade_min=camper_per_seatrade_min,
                camper_per_seatrade_max=camper_per_seatrade_max,
                camper_per_cabin_min=camper_per_cabin_min,
                camper_per_cabin_max=camper_per_cabin_max,
            )
            st.form_submit_button(
                "Submit",
                on_click=_update_simulation_config,
                kwargs={"simulation_config": simulation_config},
            )
        st.caption(st.session_state["simulation_config"])
        st.caption(st.session_state["optimization_config"])


def _update_simulation_config(simulation_config: SimulationConfig):
    """Update config for the mock data parameters."""
    if (
        simulation_config.camper_per_seatrade_min
        >= simulation_config.camper_per_seatrade_max
    ):
        st.toast(
            "Error updating simulation configuration.\n Camper per seatrade min must be strictly less than camper per cabin max.\n"
            f"Instead found {simulation_config.camper_per_seatrade_min} >= {simulation_config.camper_per_seatrade_max}.",
            icon="🚨",
        )
        return
    if simulation_config.camper_per_cabin_min >= simulation_config.camper_per_cabin_max:
        st.toast(
            "Error updating simulation configuration.\n Camper per cabin min must be strictly less than camper per cabin max.\n"
            f"Instead found {simulation_config.camper_per_cabin_min} >= {simulation_config.camper_per_cabin_max}.",
            icon="🚨",
        )
        return
    if st.session_state.get("simulation_config") is not None:
        st.toast(f"Updating Simulation Configuration.\n\n{simulation_config}")
    st.session_state["simulation_config"] = simulation_config
    _clear_optimization_results()


@dataclass
class CamperSimulationConfig:
    num_cabins: int = 8
    num_preferences: int = 4
    camper_per_cabin_min: int = 8
    camper_per_cabin_max: int = 12


def _simulate_cabin_camper_preferences(
    camper_simulation_config: CamperSimulationConfig,
    seatrade_preferences: preferences.SeatradesConfig,
) -> preferences.CamperSeatradePreferences:
    """Get our cabin-camper preferences for our optimization problem."""
    all_seatrades = seatrade_preferences["seatrade"].tolist()

    # Mock Cabins
    cabins = [f"Cabin{i:0>2}" for i in range(camper_simulation_config.num_cabins)]

    # Mock Campers and Preferences
    camper_prefs = {}
    num_campers = 0
    for cabin in cabins:
        cabin_info = {}
        for camper in range(
            np.random.randint(
                camper_simulation_config.camper_per_cabin_min,
                camper_simulation_config.camper_per_cabin_max,
            )
        ):
            camper_name = f"Camper{num_campers:0>3}"
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
    # Add Gender based on Cabin
    for cabin in cabin_camper_prefs["cabin"].unique():
        cabin_camper_prefs.loc[cabin_camper_prefs["cabin"] == cabin, "gender"] = (
            np.random.choice(["male", "female"])
        )

    # This is inefficient from a wrangling point of view but it's okay it's just to start.
    cabin_camper_prefs = cabin_camper_prefs.drop(columns="seatrade").join(
        pd.DataFrame(
            cabin_camper_prefs["seatrade"].to_list(),
            columns=[
                f"seatrade_{i+1}"
                for i in range(camper_simulation_config.num_preferences)
            ],
        )
    )
    return preferences.CamperSeatradePreferences.validate(cabin_camper_prefs)


@dataclass
class SeatradeSimulationConfig:
    num_seatrades: int = 16
    camper_per_seatrade_min: int = 8
    camper_per_seatrade_max: int = 15


def _simulate_seatrade_preferences(
    seatrade_simulation_config: SeatradeSimulationConfig,
) -> preferences.SeatradesConfig:
    """Get our seatrade preferences for our optimization problem."""
    # Mock Data for Now
    seatrades_prefs_dict = {
        f"Seatrade{n:0>2}": {
            "campers_min": (temp := np.random.randint(0, 1)),
            "campers_max": temp
            + (
                np.random.randint(
                    seatrade_simulation_config.camper_per_seatrade_min,
                    seatrade_simulation_config.camper_per_seatrade_max,
                )
            ),
        }
        for n in range(seatrade_simulation_config.num_seatrades)
    }
    seatrades_prefs = pd.DataFrame(seatrades_prefs_dict).T.reset_index(names="seatrade")
    return preferences.SeatradesConfig.validate(seatrades_prefs)
