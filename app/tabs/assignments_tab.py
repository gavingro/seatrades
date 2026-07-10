from collections.abc import MutableMapping, Sequence
from typing import Any, Literal, Optional, Protocol

import pandas as pd
import streamlit as st

from seatrades.blocks import BLOCK_DECODER_CAPTION
from seatrades.config import OptimizationConfig
from seatrades.diagnostics import Finding
from seatrades.preferences import ValidationError, join_and_validate
from seatrades.problem import SchedulingProblem
from seatrades.results import (
    AssignmentSolution,
    SolverState,
    SolverStatus,
    prepare_seatrade_leaders,
    wrangle_assignments_to_longform,
    wrangle_assignments_to_wideform,
    wrangle_fleet_assignments,
    wrangle_seatrade_staffing,
)
from seatrades.scoring import score
from seatrades.solve_run import SolveRun
from seatrades.visualization import (
    display_assignments,
    display_fleet_assignments,
    display_metric_detail,
    display_optimality_donut,
    display_quality_summary,
    display_seatrade_staffing,
    metric_label,
)

# session_state key holding the active SolveRun. Its presence *is* "a solve is in
# flight" — the single source of truth for the concurrency guard (no separate flag).
ACTIVE_RUN_KEY = "solve_run"

# How often the fragment re-polls SolveRun.progress() while a solve runs.
_POLL_INTERVAL_SECONDS = 2

# Plain-language glossary for the Schedule Quality report card, shown in an expander so a
# non-technical Captain can decode every area and term without leaving the page. Kept here
# (presentation copy) rather than in the scoring/visualization service layer.
_QUALITY_GLOSSARY = """
**What do these scores mean?**

**Overview** compares all seven areas at once; pick an area to drill into a detailed display:

- **Preference** — the percentage of campers that got *good picks* (their #1 choice in at least one of their two
  seatrades).
- **Cohesion** — the percentage of campers that are with a cabinmate in their seatrade session(s). Technically,
  this is scored twice for each camper: once for each of their seatrade assignments.
- **Sparsity** — the percentage of seatrades you have to staff of the total available seatrades.
  *Fewer is better* — less staffing load.
- **Cabin variety** — in each seatrade session, how much does the biggest cabin dominate?
  *Less domination is better* — many cabins mixed together, not one cabin taking over the session.
- **Age spread** — how close in age the campers in each seatrade are. *Age range = oldest minus
  youngest* (0 = everyone the same age; 16- and 17-year-olds together = 1).
- **Within-cabin fairness** — inside a cabin, did everyone get similarly good picks, or did one
  camper get a raw deal?
- **Between-cabin fairness** — across cabins, did some whole cabins get better picks than others?

Every area is framed so **higher is better**. *Fairness* areas score high when schedules
are *even*, even if they are evenly mediocre. Preference is what shows the overall level,
and is probably the most important score here.

One glossary term: Each camper ranks four seatrades and is assigned two of them. Their **pick rank** combines those
two picks to range from: **3 = seatrade pick number 1 and number 2 (best)**, **6 = pick 2 and 4 (worst)**.
The preference and fairness areas above reference this "**pick rank**" value.

"""


class _CompletedRun(Protocol):
    """A finished SolveRun: ``result()`` yields its solution (None only mid-solve)."""

    def result(self) -> Optional[AssignmentSolution]: ...


def solve_view_state(
    session_state: MutableMapping[Any, Any],
) -> Literal["idle", "running", "done"]:
    """Which assignments view to render, derived purely from session_state.

    "running" while a SolveRun is active (takes precedence over a lingering prior
    solution), "done" once a solution is stored with no active run, else "idle".
    """
    if session_state.get(ACTIVE_RUN_KEY):
        return "running"
    if session_state.get("assigned_solution"):
        return "done"
    return "idle"


def finalize_solve(run: _CompletedRun, log_text: str, session_state: MutableMapping[Any, Any]) -> None:
    """Move a finished run's result into session_state and clear the active run.

    Called once the run's solve has completed. Stores the solution, a success flag
    (True only when optimal), and the final solver log (so the done view can show
    it after solving), then deletes the active-run key so the concurrency guard
    re-enables the Assign button and polling stops.
    """
    solution = run.result()
    if solution is not None:
        session_state["assigned_solution"] = solution
        session_state["optimization_success"] = solution.status.state == SolverState.OPTIMAL
    session_state["solver_log"] = log_text
    del session_state[ACTIVE_RUN_KEY]


class AssignmentsTab:
    """Tab Content for Assigning Seatrades"""

    def generate(self) -> None:
        if "introduced" not in st.session_state or not st.session_state["introduced"]:
            _generate_intro_dialogue()
        view_state = solve_view_state(st.session_state)
        st.button(
            "Assign Seatrades.",
            on_click=_assign_seatrades,
            kwargs={
                "optimization_config": st.session_state["optimization_config"],
            },
            # Single-run guard: disabled while a solve is in flight (run present).
            disabled=view_state == "running",
        )
        if view_state == "running":
            # An active solve: poll it without blocking the script.
            _solve_progress_fragment()
        elif view_state == "done":
            # Display results
            if not st.session_state["optimization_success"]:
                solution = st.session_state["assigned_solution"]
                st.warning(assignment_failure_warning(solution.status, solution.findings))
            else:
                solution = st.session_state["assigned_solution"]

                # Verdict — did it work? Confirmation + the solver-optimality % inline, branched
                # on whether the result is proven or a stopped-on-time incumbent. The Solver
                # Optimality donut itself now lives beside the Overview summary below.
                st.success(assignment_success_banner(solution.status))

                # The Schedule — here's the artifact, before any report card.
                st.divider()
                st.subheader("The Schedule")

                # Fleet Assignments — coarse Cabin × Block overview first, so the Captain reads
                # each cabin's week shape (Seatrade vs Fleet Time) before the dense camper grid.
                st.subheader("Fleet Assignments")
                st.caption("Each cabin's week at a glance — on a Seatrade or on Fleet Time each block.")
                st.altair_chart(display_fleet_assignments(wrangle_fleet_assignments(solution)))

                # Seatrade Staffing Schedule — which seatrades run in which blocks, so the Captain
                # sees what there is to staff. A full "Not offered" row = a seatrade with zero uptake.
                st.subheader("Seatrade Staffing Schedule")
                st.caption("Which seatrades run each block — a fully Not-offered row got zero uptake this week.")
                st.altair_chart(display_seatrade_staffing(wrangle_seatrade_staffing(solution)))

                results_chart = display_assignments(solution)
                st.altair_chart(results_chart)
                st.caption(f"Blocks: {BLOCK_DECODER_CAPTION}")
                st.caption("Color = camper satisfaction (green = 1st choice pick → red = lower ranked choices). ")
                st.caption("Numbers indicate camper-submitted seatrade preferences.")

                # Schedule Quality — the report card. One slot: Overview summary or a
                # single metric's drill-down, never both. Only reached on an optimal solve.
                st.divider()
                st.subheader("Schedule Quality")
                st.caption(
                    "How good is this schedule in practice? View the quality of the generated "
                    "schedule across a range of independent scheduling goals."
                )
                scorecard = score(solution)
                # Options are single-sourced from the scorecard; a unit test asserts every metric
                # also has a detail chart, so a selectable area can never lack a drill-down.
                quality_options = [
                    "Overview",
                    *(metric.name for metric in scorecard.metrics),
                ]
                quality_view = st.selectbox(
                    "Area",
                    options=quality_options,
                    index=0,
                    format_func=metric_label,
                    help=_QUALITY_GLOSSARY,
                    key="quality_view_selector",
                )
                if quality_view == "Overview":
                    # Overview shows the seven-area summary alongside the Solver Optimality donut,
                    # both framed as at-a-glance "summary" artifacts of the solve.
                    optimality_col, summary_col = st.columns([1, 2])
                    with optimality_col:
                        st.altair_chart(display_optimality_donut(solution.status.optimality))
                        st.caption(
                            "*Solver Optimality* is how close the solver proved it got to the mathematical optimum."
                        )
                    with summary_col:
                        st.altair_chart(display_quality_summary(scorecard))
                        st.caption(
                            "*Schedule Quality* is how well the schedule supports camp goals.\n "
                            "Each score is on it's own scale for ease of display."
                        )
                else:
                    st.altair_chart(display_metric_detail(scorecard.metric(quality_view)))

                # Assignment Data — the take-away/export view.
                longform_df = wrangle_assignments_to_longform(solution)

                st.divider()
                st.subheader("Assignment Data")

                view_options: list[Literal["By Camper", "By Seatrade"]] = [
                    "By Camper",
                    "By Seatrade",
                ]
                selected_view = st.selectbox(
                    "View",
                    options=view_options,
                    index=0,
                    key="assignment_view_selector",
                )
                assert selected_view in view_options

                st.dataframe(render_view(longform_df, selected_view, camper_order=solution.campers))

            # Final CBC log, kept for post-solve inspection (no longer live-updating).
            # Chronological — read top-to-bottom — unlike the reversed live stream.
            solver_log = st.session_state.get("solver_log")
            if solver_log:
                with st.expander("Show technical details (solver logs)"):
                    st.text_area(
                        "Solver Logs",
                        value=solver_log,
                        height=300,
                        key="final_solver_logs",
                    )


@st.dialog("Welcome to the Keats Seatrade Scheduler", width="large")
def _generate_intro_dialogue() -> None:
    """
    Generate intro dialog if not seen already.
    """
    st.markdown("""
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
    """)
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
    # Construct, start, and store the run; its presence guards against a second solve.
    # The fragment polls it, renders progress, and finalizes on completion.
    run = SolveRun(problem, optimization_config)
    run.start()
    st.session_state[ACTIVE_RUN_KEY] = run


@st.fragment(run_every=_POLL_INTERVAL_SECONDS)
def _solve_progress_fragment() -> None:
    """Poll the active SolveRun, render live progress, and finalize on completion.

    Invoked only while an active run is present (from ``generate``). Each tick it
    redraws the progress bar + collapsible solver logs. When the solve finishes it
    stores the result and clears the active run, then triggers a full-script rerun
    so the main script leaves this fragment branch and polling stops cleanly.
    """
    run = st.session_state.get(ACTIVE_RUN_KEY)
    if run is None:
        return
    progress = run.progress()
    if not progress.running:
        finalize_solve(run, progress.log_text, st.session_state)
        st.rerun()
        return
    with st.status(progress.message, expanded=True):
        st.progress(progress.percent, progress.message)
        # Newest log lines on top while streaming, so the latest CBC output is
        # visible without scrolling. No widget key: a keyed text_area pins to its
        # first-poll value and ignores later `value=` updates (Streamlit widget-state
        # rule), which froze the log empty for the whole solve. Keyless re-applies
        # `value` each poll, so the panel tracks the growing log.
        live_log = "".join(progress.log_text.splitlines(keepends=True)[::-1])
        with st.expander("Show technical details (solver logs)"):
            st.text_area("Solver Logs", value=live_log, height=300)
        st.caption("This solve finishes on its own or stops at the configured time limit.")


def assignment_success_banner(status: SolverStatus) -> str:
    """User-facing success copy for a solve that produced a full schedule.

    Branches on the stop reason so a *proven* near-optimal result is not confused with a
    schedule the solver merely *stopped on* at the time limit: the latter is the best
    incumbent so far, and a longer solve may improve it — say so rather than overstating
    it with the proven "X% optimal" copy.
    """
    if status.timed_out:
        return (
            "Every camper is assigned — best schedule so far (stopped at the time limit); "
            "a longer solve may improve it."
        )
    return f"Every camper is assigned — proven {round(status.optimality * 100)}% optimal."


def assignment_failure_warning(status: SolverStatus, findings: Sequence[Finding] = ()) -> str:
    """User-facing copy for a non-optimal solve.

    Branches on the outcome: a crash (ERROR) surfaces its message so the Captain is
    never shown an untrustworthy result without explanation (story #73-16); a timeout
    is a *feasible* problem that ran out of time — a scale/time issue, never an
    "unexpected error"; an infeasible solve prepends any diagnosed causes above the
    retained generic guidance, or admits it couldn't pinpoint the cause when none fired.
    """
    if status.state == SolverState.ERROR:
        return f"The optimizer hit an unexpected error and couldn't finish: {status.message}"
    if status.state == SolverState.TIMEOUT:
        return (
            "The solver ran out of time before it could finish — this schedule may well be "
            "possible, it just needs more time or a smaller problem. Raise the *time limit* "
            "or loosen the *Minimum solution quality* under **Advanced settings** in "
            "Optimization Setup, or reduce the number of cabins, seatrades, or relationships, "
            "then assign again."
        )
    generic = (
        "No schedule could satisfy all the rules this time. Try relaxing a hard limit "
        "under **Advanced settings** in Optimization Setup (e.g. raise *Max seatrades "
        "per fleet*), or lower the *Minimum solution quality*, then assign again."
    )
    # Prepend the specific causes above the retained generic catch-all — add to it, never
    # replace it. When nothing fired, be honest rather than silent (story #73-21).
    if findings:
        causes = "\n\n".join(f"**{finding.cause}**\n\n*Fix:* {finding.fix}" for finding in findings)
        return f"{causes}\n\n{generic}"
    return f"We couldn't identify the exact cause this time. {generic}"


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
