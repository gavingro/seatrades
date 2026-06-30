import time
from typing import Literal, Optional

import pandas as pd
import streamlit as st

from seatrades.blocks import BLOCK_DECODER_CAPTION
from seatrades.config import OptimizationConfig
from seatrades.preferences import ValidationError, join_and_validate
from seatrades.problem import SchedulingProblem
from seatrades.results import (
    SolverState,
    SolverStatus,
    prepare_seatrade_leaders,
    wrangle_assignments_to_longform,
    wrangle_assignments_to_wideform,
)
from seatrades.solve_run import SolveRun
from seatrades.visualization import display_assignments

# Makes Streamlit log-widget keys unique across reruns (presentation concern only).
log_counter = 1


class AssignmentsTab:
    """Tab Content for Assigning Seatrades"""

    def generate(self) -> None:
        if "introduced" not in st.session_state or not st.session_state["introduced"]:
            _generate_intro_dialogue()
        st.button(
            "Assign Seatrades.",
            on_click=_assign_seatrades,
            kwargs={
                "optimization_config": st.session_state["optimization_config"],
            },
        )
        if st.session_state.get("assigned_solution"):
            # Display results
            if not st.session_state["optimization_success"]:
                st.warning(assignment_failure_warning(st.session_state["assigned_solution"].status))
            else:
                solution = st.session_state["assigned_solution"]
                optimality = solution.status.optimality
                st.success(
                    f"Every camper is assigned. Schedule is {optimality:.0%} optimal based on optimization preferences."
                )
                results_chart = display_assignments(solution)
                st.altair_chart(results_chart)
                st.caption(f"Blocks: {BLOCK_DECODER_CAPTION}")
                st.caption("Color = camper satisfaction (green = 1st choice pick → red = lower ranked choices). ")

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
def _generate_intro_dialogue() -> None:
    """
    Generate intro dialog if not seen already.
    """
    st.markdown(
        """
    This web application is designed to help the **Scheduling Captain** to optimally assign
    campers to seatrades, balancing cabin cohesion, camper preferences, and seatrade
    availability.

    Each week, Keats Camps hosts ~250 campers across ~22 cabins, and on the first day of
    camp, each camper submits their top Seatrade preferences. Your daunting task as the
    Scheduling Captain is to assign cabins to two fleets, assign seatrades to each fleet,
    and assign each camper to the seatrades.

    This app streamlines the process, optimizing assignments to create the best experience
    for campers while saving you time and effort.

    **Example mock data is already loaded** so you can try assigning seatrades right away — it's
    only a sample, and you can replace it with your own week any time. There are 3 steps to do that:
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
            "Adjust your **goals and limits** to describe this week's priorities in the **Scheduling Setup** tab.",
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
    relationships = st.session_state.get("camper_relationships")

    if identity is None or camper_prefs is None or seatrade_prefs is None:
        st.toast("Missing camper or seatrade data. Upload or simulate first.", icon="🚨")
        return

    try:
        joined_campers, seatrade_setup, validated_relationships = join_and_validate(
            identity, camper_prefs, seatrade_prefs, relationships
        )
    except ValidationError as e:
        st.toast("Cross-reference validation failed.", icon="🚨")
        with st.popover("Validation errors. Click for details.", icon="🚨"):
            for error in e.errors:
                st.write(error)
        return

    st.session_state["cabin_camper_prefs"] = joined_campers
    st.toast("Beginning Seatrade Optimization.")
    problem = SchedulingProblem(joined_campers, seatrade_setup, relationships=validated_relationships)
    run = SolveRun(problem, optimization_config)
    with st.status("Setting up the optimization…") as status:
        # CAUTION: Stopping only interrupts this UI loop — the daemon solve thread keeps
        # running. Real cancellation is tracked in #61 / Spec B.
        stop_button = st.empty()

        def _stop_optimizing() -> None:
            raise KeyboardInterrupt

        stop_button.button("Stop Optimizing", on_click=_stop_optimizing)

        progress_bar = st.progress(0, "Setting up the optimization…")

        # Raw solver logs are tucked into a collapsed expander so the default view stays friendly.
        global log_counter
        with st.expander("Show technical details (solver logs)"):
            log_container = st.empty()

        # SolveRun owns the thread + log file; the UI just polls and renders.
        run.start()
        progress = run.progress()
        while progress.running:
            progress_bar.progress(progress.percent, progress.message)
            live_log = "".join(progress.log_text.splitlines(keepends=True)[::-1])
            if live_log:
                log_container.text_area(
                    "Solver Logs.",
                    value=live_log,
                    height=300,
                    key=str(log_counter) + live_log,
                )
                status.update(label=progress.message)
            time.sleep(2)  # Adjust polling frequency
            log_counter += 1
            progress = run.progress()

        log_container.text_area(
            "Solver Logs",
            value=progress.log_text,
            height=300,
            key="logs",
        )
        solution = run.result()
        timeout_status = " - Timeout Reached" if progress.timed_out else ""
        solution_optimality = solution.status.optimality if solution is not None else 1.0
        optimality_status = f" - {solution_optimality:.0%} Optimal Solution found"
        progress_bar.progress(1.0, "Optimization Concluded.")
        st.toast("Seatrade Optimization Concluded.")
        if solution is not None and solution.status.state == SolverState.OPTIMAL:
            st.session_state["optimization_success"] = True
            st.toast("Optimization Problem Solved!", icon="🎉")
            status.update(
                state="complete",
                label=("Seatrades assigned successfully" + timeout_status + optimality_status + "."),
                expanded=False,
            )
        else:
            st.session_state["optimization_success"] = False
            st.toast("Failed to solve optimization problem.", icon="🚨")
            status.update(state="error", label="Seatrades failed to be assigned.")
    if solution is not None:
        st.session_state["assigned_solution"] = solution
    stop_button.empty()


def assignment_failure_warning(status: SolverStatus) -> str:
    """User-facing copy for a non-optimal solve.

    A crash (ERROR) surfaces its message so the Captain is never shown an
    untrustworthy result without explanation (story #73-16); an infeasible solve
    keeps the relax-a-hard-limit guidance.
    """
    if status.state == SolverState.ERROR:
        return f"The optimizer hit an unexpected error and couldn't finish: {status.message}"
    return (
        "No schedule could satisfy all the rules this time. Try relaxing a hard limit "
        "under **Advanced settings** in Optimization Setup (e.g. raise *Max seatrades "
        "per fleet*), or lower the *Minimum solution quality*, then assign again."
    )


def render_view(
    longform_df: pd.DataFrame,
    view_name: Literal["By Camper", "By Seatrade"],
    camper_order: Optional[list[str]] = None,
) -> pd.DataFrame:
    """Render the selected assignment view.

    Parameters
    ----------
    longform_df : pd.DataFrame
        Longform assignments dataframe.
    view_name : Literal["By Camper", "By Seatrade"]
        Which assignment view to render.
    camper_order : Optional[list[str]]
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
