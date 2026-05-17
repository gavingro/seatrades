import queue
import re
import threading
import time
from copy import deepcopy
from typing import List, Literal, Optional

import pandas as pd
import streamlit as st

from seatrades.config import SEATRADES_LOG_PATH, OptimizationConfig
from seatrades.preferences import ValidationError, join_and_validate
from seatrades.results import (
    AssignmentSolution,
    display_assignments,
    prepare_seatrade_leaders,
    wrangle_assignments_to_longform,
    wrangle_assignments_to_wideform,
)
from seatrades.seatrades import Seatrades

status_queue: queue.Queue[int] = queue.Queue()
log_counter = 1


class AssignmentsTab:
    """Tab Content for Assigning Seatrades"""

    def generate(self):
        if "introduced" not in st.session_state or not st.session_state["introduced"]:
            _generate_intro_dialogue()
        st.button(
            "Assign Seatrades.",
            on_click=_assign_seatrades,
            kwargs={
                "optimization_config": st.session_state["optimization_config"],
            },
        )
        if st.session_state.get("assigned_seatrades"):
            # Display results
            if not st.session_state["optimization_success"]:
                st.write("Optimization not successful.")
            else:
                st.write("Optimization Success. Seatrades assigned for each camper.")
                seatrades_obj = st.session_state["assigned_seatrades"]
                solution = AssignmentSolution.from_seatrades(seatrades_obj)
                results_chart = display_assignments(solution)
                st.altair_chart(results_chart)

                longform_df = wrangle_assignments_to_longform(solution)

                st.divider()
                st.subheader("Assignment Data")

                view_options: list[Literal["By Camper", "By Seatrade"]] = ["By Camper", "By Seatrade"]
                selected_view = st.selectbox(
                    "View",
                    options=view_options,
                    index=0,
                    key="assignment_view_selector",
                )
                assert selected_view in view_options

                st.dataframe(render_view(longform_df, selected_view, camper_order=solution.campers))


@st.dialog("Welcome to the Keats Seatrade Scheduler", width="large")
def _generate_intro_dialogue():
    """
    Generate intro dialog if not seen already.
    """
    st.markdown(
        """
    This web application is designed to help the **Scheduling Captain** to optimally assign
    campers to seatrades, balancing cabin cohesion, camper preferences, and activity
    availability.

    Each week, Keats Camps hosts ~250 campers across ~22 cabins, and on the first day of
    camp, each camper submits their top Seatrade preferences. Your daunting task as the
    Scheduling Captain is to assign cabins to two fleets, assign seatrades to each fleet,
    and assign each camper to the seatrades.

    This app streamlines the process, optimizing assignments to create the best experience
    for campers while saving you time and effort.

    Some example mock data has already been preloaded for example, so you can see what it
    looks like to assign seatrades. There are 3 steps to repeat this process with your own
    data for a week at camp:
    """
    )
    cols = st.columns(3)
    with cols[0]:
        st.info(
            "Upload your own **Seatrade preferences** you might have to describe your week"
            " at camp in the **Seatrade Setup** tab.",
            icon=":material/camping:",
        )
    with cols[1]:
        st.success(
            "Upload your own **Preferences per Camper** for this week's campers in the **Camper Setup** tab.",
            icon=":material/child_care:",
        )
    with cols[2]:
        st.warning(
            "Adjust your **constraints and preferences** to describe this week's goals"
            " in the **Optimization Config** tab.",
            icon=":material/tune:",
        )
    st.markdown("Happy scheduling!")
    if st.button("Don't show this again.", use_container_width=True):
        st.session_state["introduced"] = True
        st.rerun()


def _assign_seatrades(
    optimization_config: OptimizationConfig,
) -> None:
    identity = st.session_state.get("camper_identity")
    camper_prefs = st.session_state.get("camper_preferences")
    seatrade_prefs = st.session_state.get("seatrade_preferences")

    if identity is None or camper_prefs is None or seatrade_prefs is None:
        st.toast("Missing camper or seatrade data. Upload or simulate first.", icon="🚨")
        return

    try:
        joined_campers, seatrade_setup = join_and_validate(identity, camper_prefs, seatrade_prefs)
    except ValidationError as e:
        st.toast("Cross-reference validation failed.", icon="🚨")
        with st.popover("Validation errors. Click for details.", icon="🚨"):
            for error in e.errors:
                st.write(error)
        return

    st.session_state["cabin_camper_prefs"] = joined_campers
    st.toast("Beginning Seatrade Optimization.")
    seatrades = Seatrades(joined_campers, seatrade_setup)  # type: ignore[arg-type]
    with st.status("Step 1/3: Setting Up Optimization Problem") as status:
        # CAUTION: Does not actually stop the solver subthread which will keep running.
        # This will be a problem later if a user starts a ton of solver threads behind the scenes.
        stop_button = st.empty()

        def _stop_optimizing() -> None:
            raise KeyboardInterrupt

        stop_button.button("Stop Optimizing", on_click=_stop_optimizing)

        progress_bar = st.progress(0, "Setting up Optimization Problem.")

        # Start the solver in a background thread, read logs in real time.
        global log_counter
        log_container = st.empty()
        log_text = ""
        if SEATRADES_LOG_PATH.exists():
            SEATRADES_LOG_PATH.unlink(missing_ok=True)
        started = time.time()
        timeout = False
        solver_thread = threading.Thread(
            target=_run_assignment_and_capture_logs,
            daemon=True,
            args=(seatrades, optimization_config),
        )
        solver_thread.start()
        while solver_thread.is_alive():
            elapsed_seconds = int(time.time() - started)
            elapsed_pct_of_time_limit = elapsed_seconds / optimization_config.solver.timeLimit
            if elapsed_pct_of_time_limit > 1.0:
                timeout = True
            progress_bar.progress(
                min(elapsed_pct_of_time_limit, 1.0),
                ("Optimization Progress" if not timeout else "Stopping Optimization."),
            )
            old_log_text = ""
            try:
                if SEATRADES_LOG_PATH.exists():
                    with open(SEATRADES_LOG_PATH, "r") as log_file:
                        log_text = "".join([line for line in log_file.readlines()][::-1])
                    if log_text != old_log_text:
                        log_container.text_area(
                            "Solver Logs.",
                            value=log_text,
                            height=300,
                            key=str(log_counter) + log_text,
                        )
                        old_log_text = log_text
                        if re.compile("Result - Stopped on time limit").search(old_log_text):
                            timeout = True

                        if not timeout:
                            status.update(label="Step 2/3: Optimizing Seatrade Assignments.")
                        elif timeout:
                            status.update(label="Step 3/3: Stopping Optimization based on timeout duration.")

            except Exception as e:
                log_container.text_area(
                    "Solver Logs.",
                    f"Error reading logs: {e}",
                    height=300,
                )
            time.sleep(2)  # Adjust polling frequency
            log_counter += 1
        if SEATRADES_LOG_PATH.exists():
            with open(SEATRADES_LOG_PATH, "r") as log_file:
                log_text = log_file.read()
        log_container.text_area(
            "Solver Logs",
            value=log_text,
            height=300,
            key="logs",
        )
        timeout_kwd_match = re.search(r"(Result - Stopped on time limit)", string=log_text)
        timeout = bool(timeout or timeout_kwd_match)
        timeout_status = " - Timeout Reached" if timeout else ""
        actual_gap_kwd = re.search(
            r"(?<=Gap:                            )(\d+\.?\d*)",
            string=log_text,
        )
        actual_gap = float(actual_gap_kwd.group()) if actual_gap_kwd else 1.0
        actual_optimality = 1.0 - actual_gap
        optimality_status = f" - {actual_optimality:.0%} Optimal Solution found"
        progress_bar.progress(
            1.0,
            ("Optimization Concluded."),
        )
        st.toast("Seatrade Optimization Concluded.")
        if not status_queue.empty() and status_queue.get() > 0:
            st.session_state["optimization_success"] = True
            st.toast("Optimization Problem Solved!", icon="🎉")
            status.update(
                state="complete",
                label=("Seatrades assigned successfully" + timeout_status + optimality_status + "."),
                expanded=False,
            )
            seatrades.status = 1
        else:
            st.session_state["optimization_success"] = False
            st.toast("Failed to solve optimization problem.", icon="🚨")
            status.update(state="error", label="Seatrades failed to be assigned.")
            seatrades.status = -1
    st.session_state["assigned_seatrades"] = deepcopy(seatrades)
    stop_button.empty()


def _run_assignment_and_capture_logs(seatrades: Seatrades, optimization_config: OptimizationConfig):
    """Run seatrades assignment and capture status to status_queue, intended to be run in a separate thread."""
    try:
        seatrades.assign(
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


def render_view(
    longform_df: pd.DataFrame,
    view_name: Literal["By Camper", "By Seatrade"],
    camper_order: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Render the selected assignment view.

    Parameters
    ----------
    longform_df : pd.DataFrame
        Longform assignments dataframe.
    view_name : Literal["By Camper", "By Seatrade"]
        Which assignment view to render.
    camper_order : Optional[List[str]]
        Ordered camper names for "By Camper" sort. Passed through to
        wrangle_assignments_to_wideform. Ignored for "By Seatrade".

    Returns
    -------
    pd.DataFrame
        Filtered, sorted, and re-ordered dataframe for display.
    """
    if view_name == "By Camper":
        return wrangle_assignments_to_wideform(longform_df, camper_order=camper_order)
    return prepare_seatrade_leaders(longform_df)
