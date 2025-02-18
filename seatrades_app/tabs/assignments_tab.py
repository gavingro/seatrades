from copy import deepcopy
import logging
import threading
import queue
import time

import streamlit as st

from seatrades_app.tabs.optimization_config_tab import (
    OptimizationConfig,
    SEATRADES_LOG_PATH,
)
from seatrades import preferences, seatrades, results

status_queue = queue.Queue()
log_counter = 1


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
    st.toast("Beginning Seatrade Optimization.")
    with st.status("Assigning Seatrades...") as status:

        # Start the solver in a background thread, read logs in real time.
        global log_counter
        log_container = st.empty()
        log_text = ""
        if SEATRADES_LOG_PATH.exists():
            SEATRADES_LOG_PATH.unlink(missing_ok=True)

        solver_thread = threading.Thread(
            target=_run_assignment_and_capture_logs,
            daemon=True,
            args=(seatrades, optimization_config),
        )
        solver_thread.start()
        while solver_thread.is_alive():
            old_log_text = ""
            try:
                if SEATRADES_LOG_PATH.exists():
                    with open(SEATRADES_LOG_PATH, "r") as log_file:
                        log_text = log_file.read()
                    if log_text != old_log_text:
                        log_container.text_area(
                            "Solver Logs",
                            value=log_text,
                            height=300,
                            key=str(log_counter) + log_text,
                        )
                        old_log_text = log_text
            except Exception as e:
                log_container.text_area(
                    "Solver Logs", f"Error reading logs: {e}", height=300
                )
            time.sleep(1)  # Adjust polling frequency
            log_counter += 1
        if SEATRADES_LOG_PATH.exists():
            with open(SEATRADES_LOG_PATH, "r") as log_file:
                log_text = log_file.read()
        if log_text != old_log_text:
            log_container.text_area(
                "Solver Logs",
                value=log_text,
                height=300,
                key=str(log_counter) + log_text,
            )
            old_log_text = log_text

        st.toast("Seatrade Optimization Concluded.")
        if not status_queue.empty() and status_queue.get() > 0:
            st.session_state["optimization_success"] = True
            st.toast("Optimization Problem Solved!", icon="🎉")
            status.update(state="complete", label="Seatrades assigned successfully.")
            seatrades.status = 1
        else:
            st.session_state["optimization_success"] = False
            st.toast("Failed to solve optimization problem.", icon="🚨")
            status.update(state="error", label="Seatrades failed to be assigned.")
            seatrades.status = -1
    st.session_state["assigned_seatrades"] = deepcopy(seatrades)
    return seatrades


def _run_assignment_and_capture_logs(
    seatrades: seatrades.Seatrades, optimization_config: OptimizationConfig
):
    """Run seatrades assignment and capture status to status_queue, intended to be run in a separate thread."""
    try:
        print("Test Print.")
        logging.info("Logging Info Print.")
        solved_problem = seatrades.assign(
            preference_weight=optimization_config.preference_weight,
            cabins_weight=optimization_config.cabins_weight,
            sparsity_weight=optimization_config.sparsity_weight,
            max_seatrades_per_fleet=optimization_config.max_seatrades_per_fleet,
            solver=optimization_config.solver,
        )
        if seatrades.status:
            status_queue.put(seatrades.status)
        else:
            status_queue.put(0)

    except Exception as e:
        print(f"Error: {e}")
        status_queue.put(-1)


def _create_seatrades(
    cabin_camper_preferences: preferences.CamperSeatradePreferences,
    seatrade_preferences: preferences.SeatradesConfig,
) -> seatrades.Seatrades:
    return seatrades.Seatrades(cabin_camper_preferences, seatrade_preferences)
