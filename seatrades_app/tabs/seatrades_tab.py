from dataclasses import dataclass


import numpy as np
import random
import pandas as pd
import streamlit as st

from seatrades import preferences
from seatrades_app.tabs.optimization_config_tab import _clear_optimization_results

# From Keats Website (and memory)
SEATRADE_EXAMPLES = [
    "Low Ropes",
    "High Ropes",
    "Giant Swing",
    "Laser Tag",
    "Frisbee Golf",
    "Field Sports",  # Lmao
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


@dataclass
class SeatradeSimulationConfig:
    num_seatrades: int = 16
    camper_capacity_min: int = 8
    camper_capacity_max: int = 15


class SeatradeSimulationConfigTab:
    """Component: Simulation Config Form"""

    def generate(self):
        with st.expander("No Seatrades Data? Simulate Seatrades Here."):
            with st.form(
                "Simulation Config", border=False
            ) as seatrade_simulation_config_form:
                st.subheader("Seatrade Simulation Config")
                num_seatrades = st.slider(
                    "num_seatrades",
                    min_value=1,
                    max_value=len(SEATRADE_EXAMPLES),
                    value=SeatradeSimulationConfig().num_seatrades,
                )
                camper_per_seatrade_min = st.slider(
                    "camper_capacity_per_seatrade_min",
                    min_value=1,
                    max_value=30,
                    value=SeatradeSimulationConfig().camper_capacity_min,
                )
                camper_per_seatrade_max = st.slider(
                    "camper_capacity_per_seatrade_max",
                    min_value=1,
                    max_value=30,
                    value=SeatradeSimulationConfig().camper_capacity_max,
                )

                seatrade_simulation_config = SeatradeSimulationConfig(
                    num_seatrades=num_seatrades,
                    camper_capacity_min=camper_per_seatrade_min,
                    camper_capacity_max=camper_per_seatrade_max,
                )
                st.form_submit_button(
                    "Update Seatrade Simulation Settings",
                    on_click=_update_seatrade_simulation_config,
                    kwargs={"seatrade_simulation_config": seatrade_simulation_config},
                )


def _simulate_seatrade_preferences(
    seatrade_simulation_config: SeatradeSimulationConfig,
) -> preferences.SeatradesConfig:
    """Get our seatrade preferences for our optimization problem."""
    # Mock Data for Now
    seatrade_name_sample = random.sample(
        SEATRADE_EXAMPLES, k=seatrade_simulation_config.num_seatrades
    )

    seatrades_prefs_dict = {
        f"{seatrade}": {
            "campers_min": (temp := np.random.randint(0, 2)),
            "campers_max": temp
            + (
                np.random.randint(
                    seatrade_simulation_config.camper_capacity_min,
                    seatrade_simulation_config.camper_capacity_max,
                )
            ),
        }
        for seatrade in seatrade_name_sample
    }
    seatrades_prefs = pd.DataFrame(seatrades_prefs_dict).T.reset_index(names="seatrade")
    return preferences.SeatradesConfig.validate(seatrades_prefs)


def _update_seatrade_simulation_config(
    seatrade_simulation_config: SeatradeSimulationConfig,
):
    """Update config for the mock data parameters."""
    if (
        seatrade_simulation_config.camper_capacity_min
        >= seatrade_simulation_config.camper_capacity_max
    ):
        st.toast(
            "Error updating simulation configuration.\n Camper per Seatrade min must be strictly less than camper per Seatrade max.\n"
            f"Instead found {seatrade_simulation_config.camper_capacity_min} >= {seatrade_simulation_config.camper_capacity_max}.",
            icon="🚨",
        )
        return
    if st.session_state.get("seatrade_simulation_config") is not None:
        st.toast(
            f"Updating Seatrade Simulation Configuration.\n\n{seatrade_simulation_config}"
        )
    st.session_state["seatrade_simulation_config"] = seatrade_simulation_config
    _clear_optimization_results()
    if "seatrade_preferences" in st.session_state:
        del st.session_state["seatrade_preferences"]
