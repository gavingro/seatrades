"""Camper setup tab — upload or simulate camper identity and preference data."""

import pandas as pd
import streamlit as st

from app.components import clear_optimization_results, show_validation_error, try_join_and_validate
from seatrades.config import CamperIdentity, CamperPreferences, CamperSimulationConfig
from seatrades.preferences import ValidationError, join_and_validate, read_csv_for_schema, validate_schema
from seatrades.simulation import (
    ALL_CABIN_DICT,
    simulate_camper_identity,
    simulate_camper_preferences,
    simulate_camper_relationships,
)


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
    if camper_simulation_config.base_age_min >= camper_simulation_config.base_age_max:
        st.toast(
            "Error updating simulation configuration.\n"
            " Base age min must be strictly less than base age max.\n"
            f"Instead found {camper_simulation_config.base_age_min}"
            f" >= {camper_simulation_config.base_age_max}.",
            icon="🚨",
        )
        return
    if st.session_state.get("camper_simulation_config") is not None:
        st.toast(f"Updating Camper Simulation Configuration.\n\n{camper_simulation_config}")
    st.session_state["camper_simulation_config"] = camper_simulation_config
    clear_optimization_results()
    # Relationships reference specific campers; drop them so they're re-seeded for the new roster.
    for key in ("camper_identity", "camper_preferences", "camper_relationships"):
        if key in st.session_state:
            del st.session_state[key]


class CamperSimulationConfigTab:
    """Component: Simulation Config Form"""

    def generate(self):
        st.subheader("Camper Setup")

        # --- Identity uploader ---
        uploaded_identity = st.file_uploader(
            label="Upload camper identity (cabin, camper, gender, age).",
            type="csv",
            help="""Upload a .csv with columns: cabin, camper, gender, age.
            Each row is one camper. Age is a whole number of years.""",
            key="identity_uploader",
        )
        if uploaded_identity:
            try:
                identity_data = read_csv_for_schema(uploaded_identity, CamperIdentity)
            except ValidationError as e:
                show_validation_error("Camper Identity", e)
            else:
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
            try:
                prefs_data = read_csv_for_schema(uploaded_prefs, CamperPreferences)
            except ValidationError as e:
                show_validation_error("Camper Preferences", e)
            else:
                _validate_and_update_preferences(prefs_data)
        if "camper_preferences" in st.session_state:
            st.data_editor(st.session_state["camper_preferences"], disabled=True)

        st.write("")
        st.write("---")
        with st.expander("No Camper Data? Simulate Here."):
            with st.form("Camper Simulation Config", border=False):
                st.subheader("Camper Simulation Config")
                num_cabins = st.slider(
                    "Number of cabins",
                    min_value=1,
                    max_value=len(ALL_CABIN_DICT),
                    value=CamperSimulationConfig().num_cabins,
                    help="How many cabins of campers to generate for this example week.",
                )
                camper_per_cabin_min = st.slider(
                    "Campers per cabin (min)",
                    min_value=1,
                    max_value=30,
                    value=CamperSimulationConfig().camper_per_cabin_min,
                    help="Fewest campers a generated cabin can have. Must be below the max.",
                )
                camper_per_cabin_max = st.slider(
                    "Campers per cabin (max)",
                    min_value=1,
                    max_value=30,
                    value=CamperSimulationConfig().camper_per_cabin_max,
                    help="Most campers a generated cabin can have. Must be above the min.",
                )
                base_age_min = st.slider(
                    "Cabin base age (min)",
                    min_value=8,
                    max_value=20,
                    value=CamperSimulationConfig().base_age_min,
                    help="Lowest base age a generated cabin can cluster around. Must be below the max.",
                )
                base_age_max = st.slider(
                    "Cabin base age (max)",
                    min_value=8,
                    max_value=20,
                    value=CamperSimulationConfig().base_age_max,
                    help="Highest base age a generated cabin can cluster around. Must be above the min.",
                )
                age_spread = st.slider(
                    "Age spread (jitter years)",
                    min_value=0.0,
                    max_value=3.0,
                    step=0.1,
                    value=CamperSimulationConfig().age_spread,
                    help="How far campers scatter around their cabin's base age. Higher = more mixed ages per cabin.",
                )

                camper_simulation_config = CamperSimulationConfig(
                    num_cabins=num_cabins,
                    camper_per_cabin_min=camper_per_cabin_min,
                    camper_per_cabin_max=camper_per_cabin_max,
                    base_age_min=base_age_min,
                    base_age_max=base_age_max,
                    age_spread=age_spread,
                )
                st.form_submit_button(
                    "Simulate Campers",
                    on_click=_simulate_campers,
                    kwargs={"camper_simulation_config": camper_simulation_config},
                )


def _validate_and_update_identity(identity_data: pd.DataFrame):
    """Validate camper identity CSV and store in session state."""
    try:
        validate_schema(CamperIdentity, identity_data, "Camper Identity")
        st.session_state["camper_identity"] = identity_data
        try_join_and_validate()
        st.toast("Updating Camper Identity.")
    except ValidationError as e:
        show_validation_error("Camper Identity", e)


def _validate_and_update_preferences(prefs_data: pd.DataFrame):
    """Validate camper preferences CSV and store in session state."""
    try:
        validate_schema(CamperPreferences, prefs_data, "Camper Preferences")
        st.session_state["camper_preferences"] = prefs_data
        try_join_and_validate()
        st.toast("Updating Camper Preferences.")
    except ValidationError as e:
        show_validation_error("Camper Preferences", e)


def _simulate_campers(camper_simulation_config: CamperSimulationConfig):
    """Simulate camper identity and preferences, then cross-validate."""
    if camper_simulation_config.camper_per_cabin_min >= camper_simulation_config.camper_per_cabin_max:
        st.toast(
            "Error simulating campers: min must be less than max.",
            icon="🚨",
        )
        return
    if camper_simulation_config.base_age_min >= camper_simulation_config.base_age_max:
        st.toast(
            "Error simulating campers: base age min must be strictly less than base age max.",
            icon="🚨",
        )
        return

    seatrade_prefs = st.session_state.get("seatrade_preferences")
    if seatrade_prefs is None:
        st.toast("Simulate or upload seatrade preferences first.", icon="🚨")
        return

    identity_df = simulate_camper_identity(camper_simulation_config)
    preferences_df = simulate_camper_preferences(identity_df, seatrade_prefs)
    relationships_df = simulate_camper_relationships(identity_df, preferences_df)

    st.session_state["camper_identity"] = identity_df
    st.session_state["camper_preferences"] = preferences_df
    st.session_state["camper_relationships"] = relationships_df
    clear_optimization_results()

    try:
        joined_campers, _seatrade_setup, _relationships = join_and_validate(
            identity_df, preferences_df, seatrade_prefs, relationships_df
        )
        st.session_state["cabin_camper_prefs"] = joined_campers
    except ValidationError as e:
        show_validation_error("Cross-reference Validation", e)
