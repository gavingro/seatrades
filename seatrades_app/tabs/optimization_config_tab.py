from dataclasses import dataclass
from typing import Optional
from pathlib import Path

import streamlit as st
import pulp

SEATRADES_LOG_PATH = Path("seatrades_assignment.log")


@dataclass
class OptimizationConfig:
    preference_weight: int = 3
    cabins_weight: int = 2
    sparsity_weight: int = 1
    max_seatrades_per_fleet: Optional[int] = None
    solver: pulp.apis.LpSolver = pulp.apis.PULP_CBC_CMD(
        timeLimit=60, gapRel=0.10, logPath=SEATRADES_LOG_PATH
    )


class OptimizationConfigForm:
    """Component: Optimization Config Form"""

    def generate(self):
        with st.form("Optimization Config") as optimization_config_form:
            st.header("Optimization Config")
            preference_weight = st.slider(
                "preference_weight",
                min_value=0,
                max_value=5,
                value=OptimizationConfig().preference_weight,
            )
            cabins_weight = st.slider(
                "cabins_weight",
                min_value=0,
                max_value=5,
                value=OptimizationConfig().cabins_weight,
            )
            sparsity_weight = st.slider(
                "sparsity_weight",
                min_value=0,
                max_value=5,
                value=OptimizationConfig().sparsity_weight,
            )
            max_seatrades_per_fleet = st.slider(
                "max_seatrades_per_fleet",
                min_value=0,
                max_value=(
                    st.session_state["num_seatrades"]
                    if st.session_state.get("num_seatrades") != None
                    else 10
                ),
                disabled=st.session_state.get("num_seatrades") != None,
                value=OptimizationConfig().max_seatrades_per_fleet,
            )
            timeout_limit_minutes = st.slider(
                "timeout_limit_minutes",
                min_value=1,
                max_value=10,
                value=OptimizationConfig().solver.timeLimit // 60,
                format="%d minutes",
            )
            optimality_gap = st.slider(
                "optimization_gap_pct",
                min_value=0,
                max_value=100,
                step=1,
                value=10,
                format="%d%%",
            )

            optimization_config = OptimizationConfig(
                preference_weight=preference_weight,
                cabins_weight=cabins_weight,
                sparsity_weight=sparsity_weight,
                max_seatrades_per_fleet=max_seatrades_per_fleet,
                solver=pulp.apis.PULP_CBC_CMD(
                    timeLimit=timeout_limit_minutes * 60, gapRel=optimality_gap / 100
                ),
            )

            st.form_submit_button(
                "Submit",
                on_click=_update_optimization_config,
                kwargs={"optimization_config": optimization_config},
            )


def _clear_optimization_results():
    if st.session_state.get("assigned_seatrades") is not None:
        st.toast("Clearing Previous Optimization Results.")
    st.session_state["optimization_success"] = None
    st.session_state["assigned_seatrades"] = None


def _update_optimization_config(optimization_config: OptimizationConfig):
    """Update config for the optimization parameters."""
    if st.session_state.get("optimization_config") is not None:
        st.toast(f"Updating Optimization Configuration.\n\n{optimization_config}")
    st.session_state["optimization_config"] = optimization_config
    _clear_optimization_results()
