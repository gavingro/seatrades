"""Camper setup tab — upload or simulate camper identity and preference data."""

import pandas as pd
import streamlit as st

from seatrades.config import CamperSimulationConfig
from seatrades.preferences import ValidationError, join_and_validate
from seatrades.simulation import ALL_CABIN_DICT, simulate_camper_identity, simulate_camper_preferences
from seatrades_app.tabs.optimization_config_tab import _clear_optimization_results


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
    for key in ("camper_identity", "camper_preferences"):
        if key in st.session_state:
            del st.session_state[key]


class CamperSimulationConfigTab:
    """Component: Simulation Config Form"""

    def generate(self):
        st.subheader("Camper Setup")

        # --- Identity uploader ---
        uploaded_identity = st.file_uploader(
            label="Upload camper identity (cabin, camper, gender).",
            type="csv",
            help="""Upload a .csv with columns: cabin, camper, gender.
            Each row is one camper.""",
            key="identity_uploader",
        )
        if uploaded_identity:
            identity_data = pd.read_csv(uploaded_identity, index_col=None)
            _validate_and_update_identity(identity_data)
        if "camper_identity" in st.session_state:
            st.data_editor(st.session_state["camper_identity"], disabled=True)

        uploaded_prefs = st.file_uploader(
            label="Upload camper preferences (camper, seatrade_1..4).",
            type="csv",
            help="""Upload a .csv with columns: camper, seatrade_1, seatrade_2, seatrade_3, seatrade_4.
            Seatrade names must match those in the Seatrade Setup tab.""",
            key="prefs_uploader",
        )
        if uploaded_prefs:
            prefs_data = pd.read_csv(uploaded_prefs, index_col=None)
            _validate_and_update_preferences(prefs_data)
        if "camper_preferences" in st.session_state:
            st.data_editor(st.session_state["camper_preferences"], disabled=True)

        st.write("")
        st.write("---")
        with st.expander("No Camper Data? Simulate Here."):
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

                camper_simulation_config = CamperSimulationConfig(
                    num_cabins=num_cabins,
                    camper_per_cabin_min=camper_per_cabin_min,
                    camper_per_cabin_max=camper_per_cabin_max,
                )
                st.form_submit_button(
                    "Simulate Campers",
                    on_click=_simulate_campers,
                    kwargs={"camper_simulation_config": camper_simulation_config},
                )


def _validate_and_update_identity(identity_data: pd.DataFrame):
    """Validate camper identity CSV and store in session state."""
    try:
        from seatrades.config import CamperIdentity

        CamperIdentity.validate(identity_data)
        st.session_state["camper_identity"] = identity_data
        _try_join_and_validate()
        st.toast("Updating Camper Identity.")
    except Exception as e:
        _show_validation_error("Camper Identity", e)


def _validate_and_update_preferences(prefs_data: pd.DataFrame):
    """Validate camper preferences CSV and store in session state."""
    try:
        from seatrades.config import CamperPreferences

        CamperPreferences.validate(prefs_data)
        st.session_state["camper_preferences"] = prefs_data
        _try_join_and_validate()
        st.toast("Updating Camper Preferences.")
    except Exception as e:
        _show_validation_error("Camper Preferences", e)


def _try_join_and_validate():
    """If both identity and preferences are present, run cross-reference validation."""
    identity = st.session_state.get("camper_identity")
    preferences = st.session_state.get("camper_preferences")
    seatrades = st.session_state.get("seatrade_preferences")

    if identity is None or preferences is None or seatrades is None:
        return

    try:
        joined_campers, seatrade_setup = join_and_validate(identity, preferences, seatrades)
        st.session_state["cabin_camper_prefs"] = joined_campers
    except ValidationError as e:
        with st.popover("Cross-reference validation failed. Click for details.", icon="🚨"):
            for error in e.errors:
                st.write(error)
        st.toast("Cross-reference validation failed.", icon="🚨")


def _simulate_campers(camper_simulation_config: CamperSimulationConfig):
    """Simulate camper identity and preferences, then cross-validate."""
    if camper_simulation_config.camper_per_cabin_min >= camper_simulation_config.camper_per_cabin_max:
        st.toast(
            "Error simulating campers: min must be less than max.",
            icon="🚨",
        )
        return

    seatrade_prefs = st.session_state.get("seatrade_preferences")
    if seatrade_prefs is None:
        st.toast("Simulate or upload seatrade preferences first.", icon="🚨")
        return

    identity_df = simulate_camper_identity(camper_simulation_config)
    preferences_df = simulate_camper_preferences(identity_df, seatrade_prefs)

    st.session_state["camper_identity"] = identity_df
    st.session_state["camper_preferences"] = preferences_df
    _clear_optimization_results()

    try:
        joined_campers, seatrade_setup = join_and_validate(identity_df, preferences_df, seatrade_prefs)
        st.session_state["cabin_camper_prefs"] = joined_campers
    except ValidationError as e:
        with st.popover("Cross-reference validation failed. Click for details.", icon="🚨"):
            for error in e.errors:
                st.write(error)
        st.toast("Cross-reference validation failed.", icon="🚨")


def _show_validation_error(label: str, error: Exception):
    with st.popover(
        f"Continuing without updating {label}. Click to see Error.",
        icon="🚨",
    ):
        st.write("Uploaded file does not meet expected schema. Error is as follows:")
        st.write(error)
        st.toast(
            f"Continuing without updating {label}.",
            icon="🚨",
        )
