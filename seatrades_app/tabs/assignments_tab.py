from copy import deepcopy
import logging
import re

import streamlit as st

from seatrades_app.tabs.optimization_config_tab import OptimizationConfig
from seatrades import preferences, seatrades, results


class AssignmentsTab:
    """Tab Content for Assigning Seatrades"""

    def generate(self):
        st.button(
            "Assign Seatrades.",
            on_click=_assign_seatrades,
            kwargs={
                "seatrades": st.session_state["seatrades_model"],
                "optimization_config": st.session_state["optimization_config"],
            },
        )
        if st.session_state.get("assigned_seatrades"):
            # Display results
            if not st.session_state["optimization_success"]:
                st.write("Optimization not successful.")
            else:
                st.write("Optimization Success. Seatrades assigned for each camper.")
            results_chart = results.display_assignments(
                st.session_state["assigned_seatrades"]
            )
            st.altair_chart(results_chart)


def _assign_seatrades(
    seatrades: seatrades.Seatrades, optimization_config: OptimizationConfig
) -> seatrades.Seatrades:
    handler = setup_logging()
    st.toast("Beginning Seatrade Optimization.")
    with st.status("Assigning Seatrades..."):
        solved_problem = seatrades.assign(
            preference_weight=optimization_config.preference_weight,
            cabins_weight=optimization_config.cabins_weight,
            sparsity_weight=optimization_config.sparsity_weight,
            max_seatrades_per_fleet=optimization_config.max_seatrades_per_fleet,
            solver=optimization_config.solver,
        )
    st.toast("Seatrade Optimization Concluded.")
    if seatrades.status and seatrades.status > 0:
        st.session_state["optimization_success"] = True
        st.toast("Optimization Problem Solved!", icon="🎉")
        handler.clear_logs()  # Clear logs after conversion
    else:
        st.session_state["optimization_success"] = False
        st.toast("Failed to solve optimization problem.", icon="🚨")
        handler.log_error("Failed to solve!")  # Log error after conversion
    st.session_state["assigned_seatrades"] = deepcopy(seatrades)
    return seatrades


def _create_seatrades(
    cabin_camper_preferences: preferences.CamperSeatradePreferences,
    seatrade_preferences: preferences.SeatradesConfig,
) -> seatrades.Seatrades:
    return seatrades.Seatrades(cabin_camper_preferences, seatrade_preferences)


class StreamlitLogHandler(logging.Handler):
    # Initializes a custom log handler with a Streamlit container for displaying logs
    def __init__(self, container):
        super().__init__()
        # Store the Streamlit container for log output
        self.container = container
        self.ansi_escape = re.compile(
            r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])"
        )  # Regex to remove ANSI codes
        self.log_area = (
            self.container.empty()
        )  # Prepare an empty conatiner for log output

    def emit(self, record):
        msg = self.format(record)
        clean_msg = self.ansi_escape.sub("", msg)  # Strip ANSI codes
        self.log_area.markdown(clean_msg)

    def clear_logs(self):
        self.log_area.empty()  # Clear previous logs


def setup_logging():
    root_logger = logging.getLogger()  # Get the root logger
    log_container = st.container()  # Create a container within which we display logs
    handler = StreamlitLogHandler(log_container)
    handler.setLevel(logging.INFO)
    root_logger.addHandler(handler)
    return handler
