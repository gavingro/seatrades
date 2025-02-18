import streamlit as st
import pandas as pd

from seatrades_app.tabs.assignments_tab import AssignmentsTab
from seatrades_app.tabs.assignments_tab import _create_seatrades
from seatrades_app.tabs.optimization_config_tab import OptimizationConfig
from seatrades_app.tabs.optimization_config_tab import OptimizationConfigForm
from seatrades_app.tabs.optimization_config_tab import _update_optimization_config
from seatrades_app.tabs.seatrades_tab import (
    SeatradeSimulationConfig,
    SeatradeSimulationConfigTab,
    _update_seatrade_simulation_config,
)
from seatrades_app.tabs.campers_tab import (
    CamperSimulationConfigTab,
)
from seatrades_app.tabs.campers_tab import (
    CamperSimulationConfig,
)
from seatrades_app.tabs.campers_tab import (
    _update_camper_simulation_config,
)
from seatrades_app.tabs.campers_tab import _simulate_cabin_camper_preferences
from seatrades_app.tabs.seatrades_tab import _simulate_seatrade_preferences


# Set up logging to capture all info level logs from the root logger
def main():
    _initial_page_setup()

    # Page Content
    st.title("Keats Seatrade Scheduler")

    with st.sidebar as sidebar:
        st.text("Sidebar Placeholder.")

    # Setup Tabs
    (
        assignments_tab,
        seatrades_tab,
        camper_pref_tab,
        optimization_config_tab,
    ) = st.tabs(
        [
            "Assignments",
            "Seatrade Setup",
            "Camper Setup",
            "Optimization Setup",
        ]
    )
    with assignments_tab:
        AssignmentsTab().generate()
    with seatrades_tab:
        st.subheader("Seatrade Preferences")
        st.data_editor(st.session_state["seatrade_preferences"])
        SeatradeSimulationConfigTab().generate()
    with camper_pref_tab:
        st.subheader("Camper Preferences")
        st.data_editor(st.session_state["cabin_camper_prefs"])
        CamperSimulationConfigTab().generate()
    with optimization_config_tab:
        OptimizationConfigForm().generate()
    # Temp for Debugging
    st.write("---")
    st.caption("Camper Simulation Config")
    st.dataframe(st.session_state["camper_simulation_config"])
    st.caption("Seatrade Simulation Config")
    st.dataframe(st.session_state["seatrade_simulation_config"])
    st.caption("Optimization Config")
    st.dataframe(st.session_state["optimization_config"])
    st.write("")


def _initial_page_setup():
    """Setup initial config and simulation preferences before user imput."""
    # Setup Base Config and Data before Preferences
    if "optimization_config" not in st.session_state:
        _update_optimization_config(optimization_config=OptimizationConfig())
    if "seatrade_simulation_config" not in st.session_state:
        _update_seatrade_simulation_config(
            seatrade_simulation_config=SeatradeSimulationConfig()
        )
    if "camper_simulation_config" not in st.session_state:
        _update_camper_simulation_config(
            camper_simulation_config=CamperSimulationConfig()
        )

    # Initialize Mock Data
    if "seatrade_preferences" not in st.session_state:
        st.session_state["seatrade_preferences"] = _simulate_seatrade_preferences(
            st.session_state["seatrade_simulation_config"]
        )
    if "cabin_camper_prefs" not in st.session_state:
        st.session_state["cabin_camper_prefs"] = _simulate_cabin_camper_preferences(
            camper_simulation_config=st.session_state["camper_simulation_config"],
            seatrade_preferences=st.session_state["seatrade_preferences"],
        )
    # Initialize Seatrades model
    st.session_state["seatrades_model"] = _create_seatrades(
        cabin_camper_preferences=st.session_state["cabin_camper_prefs"],
        seatrade_preferences=st.session_state["seatrade_preferences"],
    )


if __name__ == "__main__":
    main()
