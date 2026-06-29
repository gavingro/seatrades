import streamlit as st

from app.tabs.assignments_tab import AssignmentsTab
from app.tabs.campers_tab import CamperSimulationConfigTab, _update_camper_simulation_config
from app.tabs.optimization_config_tab import (
    OptimizationConfigForm,
    _update_optimization_config,
)
from app.tabs.seatrades_tab import (
    SeatradeSimulationConfigTab,
    _update_seatrade_simulation_config,
)
from seatrades.config import CamperSimulationConfig, OptimizationConfig, SeatradeSimulationConfig
from seatrades.preferences import join_and_validate
from seatrades.simulation import (
    simulate_camper_identity,
    simulate_camper_preferences,
    simulate_seatrade_preferences,
)


# Set up logging to capture all info level logs from the root logger
def main():
    _initial_page_setup()

    # Page Content
    st.title("Keats Seatrade Scheduler")

    # Setup Tabs
    (
        assignments_tab,
        seatrades_tab,
        camper_pref_tab,
        optimization_config_tab,
    ) = st.tabs(
        [
            ":material/date_range: Assignments",
            ":material/camping: Seatrade Setup",
            ":material/child_care: Camper Setup",
            ":material/tune: Scheduling Setup",
        ]
    )
    with assignments_tab:
        AssignmentsTab().generate()
    with seatrades_tab:
        SeatradeSimulationConfigTab().generate()
    with camper_pref_tab:
        CamperSimulationConfigTab().generate()
    with optimization_config_tab:
        st.subheader("Scheduling Setup")
        OptimizationConfigForm().generate()


def _initial_page_setup():
    """Setup initial config and simulation preferences before user input."""
    # Setup Base Config and Data before Preferences
    if "optimization_config" not in st.session_state:
        _update_optimization_config(optimization_config=OptimizationConfig())
    if "seatrade_simulation_config" not in st.session_state:
        _update_seatrade_simulation_config(seatrade_simulation_config=SeatradeSimulationConfig())
    if "camper_simulation_config" not in st.session_state:
        _update_camper_simulation_config(camper_simulation_config=CamperSimulationConfig())

    # Initialize Mock Data
    if "seatrade_preferences" not in st.session_state:
        st.session_state["seatrade_preferences"] = simulate_seatrade_preferences(
            st.session_state["seatrade_simulation_config"]
        )
    if "camper_identity" not in st.session_state:
        identity_df = simulate_camper_identity(st.session_state["camper_simulation_config"])
        st.session_state["camper_identity"] = identity_df
        st.session_state["camper_preferences"] = simulate_camper_preferences(
            identity_df, st.session_state["seatrade_preferences"]
        )
    # cabin_camper_prefs is the joined result used by Seatrades
    if "cabin_camper_prefs" not in st.session_state:
        joined_campers, _seatrade_setup = join_and_validate(
            st.session_state["camper_identity"],
            st.session_state["camper_preferences"],
            st.session_state["seatrade_preferences"],
        )
        st.session_state["cabin_camper_prefs"] = joined_campers


if __name__ == "__main__":
    main()
