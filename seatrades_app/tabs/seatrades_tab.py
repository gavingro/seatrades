"""Seatrade preferences tab — upload, validate, or simulate available seatrades."""

import pandas as pd
import streamlit as st

from seatrades import preferences
from seatrades.config import SeatradeSimulationConfig
from seatrades.simulation import SEATRADE_EXAMPLES
from seatrades_app.tabs.optimization_config_tab import _clear_optimization_results


class SeatradeSimulationConfigTab:
    """Component: Simulation Config Form"""

    def generate(self):
        st.subheader("Seatrade Preferences")
        uploaded_seatrade_prefs = st.file_uploader(
            label="Upload your preferences for this weeks seatrades.",
            type="csv",
            help="""Upload preferences as a .csv file.
            Uploaded data **must** have the same columns as seen below, and an example form
            can be downloaded by interacting with the displayed data below.
            Seatrades preferences are the list of available seatrades, as well as the
            minimum and maximum campers that seatrade needs to run.
            Setting a minimum above 0 for a seatrade will ensure that seatrade is always
            selected.
            """,
        )
        if uploaded_seatrade_prefs:
            seatrade_prefs_data = pd.read_csv(uploaded_seatrade_prefs, index_col=None)
            _validate_and_update_seatrade_preferences(seatrade_prefs_data)
        st.data_editor(st.session_state["seatrade_preferences"], disabled=True)

        st.write("")
        st.write("---")
        with st.expander("No Seatrades Data? Simulate Seatrades Here."):
            with st.form("Simulation Config", border=False):
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


def _validate_and_update_seatrade_preferences(seatrades_preferences: pd.DataFrame):
    try:
        preferences.SeatradesConfig.validate(seatrades_preferences)
        st.session_state["seatrade_preferences"] = seatrades_preferences
        st.toast("Updating Seatrade Preferences.")
    except Exception as e:
        with st.popover(
            "Continuing without updating Seatrades Config. Click to see Error.",
            icon="🚨",
        ):
            st.write("Uploaded file does not meet expected schema. Error is as follows:")
            st.write(e)
            st.toast(
                "Continuing without updating Seatrades Config.",
                icon="🚨",
            )


def _update_seatrade_simulation_config(
    seatrade_simulation_config: SeatradeSimulationConfig,
):
    """Update config for the mock data parameters."""
    if seatrade_simulation_config.camper_capacity_min >= seatrade_simulation_config.camper_capacity_max:
        st.toast(
            "Error updating simulation configuration.\n"
            " Camper per Seatrade min must be strictly less than camper per Seatrade max.\n"
            f"Instead found {seatrade_simulation_config.camper_capacity_min}"
            f" >= {seatrade_simulation_config.camper_capacity_max}.",
            icon="🚨",
        )
        return
    if st.session_state.get("seatrade_simulation_config") is not None:
        st.toast(f"Updating Seatrade Simulation Configuration.\n\n{seatrade_simulation_config}")
    st.session_state["seatrade_simulation_config"] = seatrade_simulation_config
    _clear_optimization_results()
    if "seatrade_preferences" in st.session_state:
        del st.session_state["seatrade_preferences"]
