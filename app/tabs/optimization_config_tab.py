import pulp
import streamlit as st

from app.components import clear_optimization_results
from seatrades.config import SEATRADES_LOG_PATH, OptimizationConfig

# Default "minimum solution quality" — the how-optimal framing of the solver gap.
# 90% quality == a 10% optimality gap (gapRel=0.10), matching the previous default.
DEFAULT_MIN_QUALITY_PCT = 90


class OptimizationConfigForm:
    """Component: Optimization Setup Form"""

    def generate(self):
        with st.form("Optimization Setup"):
            st.markdown(
                "Tell the optimizer what matters most for this week's schedule. These first sliders below are "
                "_soft preferences_. The optimizer balances them against each other to find the "
                "best overall schedule."
            )

            # --- Basic: the three competing goals ---
            preference_weight = st.slider(
                "Give Campers their Favourite Picks",
                min_value=0,
                max_value=5,
                value=OptimizationConfig().preference_weight,
                help=(
                    "How hard to push for campers' #1–2 ranked seatrades (camper happiness). "
                    "Raising it may pull cabinmates apart or need more distinct seatrades."
                ),
            )
            cabins_weight = st.slider(
                "Keep Cabinmates Together",
                min_value=0,
                max_value=5,
                value=OptimizationConfig().cabins_weight,
                help=(
                    "How hard to keep cabinmates in the same seatrades (cohesion / easier "
                    "supervision). Raising it may cost some campers their top picks."
                ),
            )
            sparsity_weight = st.slider(
                "Fewer seatrades to staff",
                min_value=0,
                max_value=5,
                value=OptimizationConfig().sparsity_weight,
                help=(
                    "How hard to run fewer distinct seatrades, so fewer staff are needed to operate "
                    "them. Raising it eases staffing but may cost top picks or cabin togetherness."
                ),
            )
            age_weight = st.slider(
                "Keep similar ages together",
                min_value=0,
                max_value=5,
                value=OptimizationConfig().age_weight,
                help=(
                    "How hard to group campers of similar age within each seatrade session and each "
                    "fleet block. Raising it tightens age clusters but may cost top picks or cabin "
                    "togetherness."
                ),
            )
            cabin_variety_weight = st.slider(
                "Cabin Variety",
                min_value=0,
                max_value=5,
                value=OptimizationConfig().cabin_variety_weight,
                help=(
                    "How hard to spread each seatrade across more cabins — fairer access, more fun "
                    "to run. The direct counterweight to 'Keep Cabinmates Together': raising it "
                    "stops one cabin from dominating a seatrade, but may pull cabinmates apart."
                ),
            )

            # --- Advanced: hard limits and power-user knobs ---
            with st.expander("Advanced settings (hard limits & solver controls)"):
                st.caption(
                    "These are **hard limits** — absolute rules the schedule must obey — plus "
                    "solver controls. Most weeks you can leave them alone."
                )
                max_seatrades_per_fleet = st.slider(
                    "Max seatrades per fleet (hard limit)",
                    min_value=0,
                    max_value=(
                        st.session_state["num_seatrades"] if st.session_state.get("num_seatrades") is not None else 10
                    ),
                    disabled=st.session_state.get("num_seatrades") is not None,
                    value=OptimizationConfig().max_seatrades_per_fleet,
                    help=(
                        "Hard cap on how many distinct seatrades can run in one fleet. This is an "
                        "absolute rule, not a preference — unlike the 'Fewer seatrades to staff' goal."
                    ),
                )
                age_balance = st.slider(
                    "Age grouping: favor fleet-wide ↔ favor seatrade",
                    min_value=0.0,
                    max_value=1.0,
                    step=0.1,
                    value=OptimizationConfig().age_balance,
                    help=(
                        "Where the 'Keep similar ages together' effort goes. Left (0) favors "
                        "fleet-wide (block) age grouping; right (1) favors per-seatrade (session) "
                        "grouping; the midpoint balances the two."
                    ),
                )
                force_same_fleet_all_week = st.checkbox(
                    "Keep each cabin in the same fleet (Morning/Afternoon) all week.",
                    value=OptimizationConfig().force_same_fleet_all_week,
                    help=(
                        "When on, a cabin that is Morning in the first half of the week stays "
                        "Morning in the second (and Afternoon stays Afternoon) — the simple "
                        "hand-scheduled arrangement. When off, the optimizer may switch a cabin "
                        "between Morning and Afternoon across the two halves for more flexibility."
                    ),
                )
                # Solution quality, framed as "how optimal" (higher = better, slower).
                min_quality_pct = st.slider(
                    "Minimum solution quality",
                    min_value=0,
                    max_value=100,
                    step=1,
                    value=DEFAULT_MIN_QUALITY_PCT,
                    format="%d%%",
                    help=(
                        "Stop once the schedule is at least this good compared to the best possible "
                        "(e.g. 90% = within 10% of optimal). Higher = better schedule, but slower."
                    ),
                )
                timeout_limit_minutes = st.slider(
                    "Solver time limit",
                    min_value=1,
                    max_value=10,
                    value=OptimizationConfig().solver.timeLimit // 60,
                    format="%d minutes",
                    help="Give up after this long and return the best schedule found so far.",
                )
                one_cabin_share_pct = st.slider(
                    "Max one-cabin share of a seatrade (hard limit)",
                    min_value=25,
                    max_value=100,
                    step=5,
                    value=int(OptimizationConfig().max_cabin_share_per_seatrade * 100),
                    format="%d%%",
                    help=(
                        "Hard cap on how much of a single seatrade one cabin may fill. 100% = off "
                        "(no cap). Below 100% forbids a cabin from taking more than this share of "
                        "any seatrade's capacity — a strict backstop beyond the 'Cabin Variety' goal."
                    ),
                )

            # "How optimal" → solver gap: 90% quality == 0.10 gap.
            optimality_gap = (100 - min_quality_pct) / 100
            # Percent slider → fraction; 100% = 1.0 = cap off.
            max_cabin_share_per_seatrade = one_cabin_share_pct / 100

            optimization_config = OptimizationConfig(
                preference_weight=preference_weight,
                cabins_weight=cabins_weight,
                sparsity_weight=sparsity_weight,
                age_weight=age_weight,
                age_balance=age_balance,
                cabin_variety_weight=cabin_variety_weight,
                max_cabin_share_per_seatrade=max_cabin_share_per_seatrade,
                max_seatrades_per_fleet=max_seatrades_per_fleet,
                force_same_fleet_all_week=force_same_fleet_all_week,
                solver=pulp.apis.PULP_CBC_CMD(
                    timeLimit=timeout_limit_minutes * 60,
                    gapRel=optimality_gap,
                    logPath=SEATRADES_LOG_PATH,
                ),
            )

            st.form_submit_button(
                "Submit",
                on_click=_update_optimization_config,
                kwargs={"optimization_config": optimization_config},
            )


def _update_optimization_config(optimization_config: OptimizationConfig):
    """Update config for the optimization parameters."""
    if st.session_state.get("optimization_config") is not None:
        st.toast(f"Updating Optimization Configuration.\n\n{optimization_config}")
    st.session_state["optimization_config"] = optimization_config
    clear_optimization_results()
