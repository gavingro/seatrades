from dataclasses import dataclass, asdict
from random import sample
from typing import Optional
import logging
import re

import streamlit as st
import pandas as pd
import numpy as np
import pulp

from seatrades import seatrades, preferences, results


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


# Set up logging to capture all info level logs from the root logger
def setup_logging():
    root_logger = logging.getLogger()  # Get the root logger
    log_container = st.container()  # Create a container within which we display logs
    handler = StreamlitLogHandler(log_container)
    handler.setLevel(logging.INFO)
    root_logger.addHandler(handler)
    return handler


@dataclass
class SimulationConfig:
    num_seatrades: int = 16
    num_cabins: int = 24
    num_preferences: int = 4
    camper_per_seatrade_min: int = 8
    camper_per_seatrade_max: int = 15
    camper_per_cabin_min: int = 8
    camper_per_cabin_max: int = 12


@dataclass
class OptimizationConfig:
    preference_weight: int = 3
    cabins_weight: int = 2
    sparsity_weight: int = 1
    max_seatrades_per_fleet: Optional[int] = None
    solver: pulp.apis.LpSolver = pulp.apis.PULP_CBC_CMD(timeLimit=60, gapRel=0.10)


def main():
    # Setup Base Config and Data before Preferences
    _update_optimization_config(OptimizationConfig())
    _update_simulation_config(SimulationConfig())

    # Config
    with st.sidebar as sidebar:
        _optimization_config_form()
        _simulation_config_form()
    # Initialize Mock Data
    seatrade_preferences = _get_seatrade_preferences(
        st.session_state["simulation_config"]
    )
    cabin_camper_prefs = _get_cabin_camper_preferences(
        simulation_config=st.session_state["simulation_config"],
        seatrade_preferences=seatrade_preferences,
    )
    # Initialize Seatrades model
    seatrades_model = _create_seatrades(
        cabin_camper_preferences=cabin_camper_prefs,
        seatrade_preferences=seatrade_preferences,
    )

    # Main Page: Run Optimization
    st.title("Keats Seatrade Scheduler")
    button_pressed = st.button("Assign Seatrades.")
    if button_pressed:
        assigned_seatrades = _assign_seatrades(
            seatrades=seatrades_model,
            optimization_config=st.session_state["optimization_config"],
        )

        # Display results
        results_chart = results.display_assignments(assigned_seatrades)
        st.altair_chart(results_chart)


def _simulation_config_form():
    """Component: Simulation Config Form"""
    with st.form("Simulation Config") as simulation_config_form:
        st.header("Simulation Config")
        num_seatrades = st.slider(
            "num_seatrades",
            min_value=1,
            max_value=30,
            value=SimulationConfig().num_seatrades,
        )
        num_cabins = st.slider(
            "num_cabins",
            min_value=1,
            max_value=30,
            value=SimulationConfig().num_cabins,
        )
        num_preferences = st.slider(
            "num_preferences",
            min_value=1,
            max_value=30,
            value=SimulationConfig().num_preferences,
        )
        camper_per_seatrade_min = st.slider(
            "camper_per_seatrade_min",
            min_value=1,
            max_value=30,
            value=SimulationConfig().camper_per_seatrade_min,
        )
        camper_per_seatrade_max = st.slider(
            "camper_per_seatrade_max",
            min_value=1,
            max_value=30,
            value=SimulationConfig().camper_per_seatrade_max,
        )
        camper_per_cabin_min = st.slider(
            "camper_per_cabin_min",
            min_value=1,
            max_value=30,
            value=SimulationConfig().camper_per_cabin_min,
        )
        camper_per_cabin_max = st.slider(
            "camper_per_cabin_max",
            min_value=1,
            max_value=30,
            value=SimulationConfig().camper_per_cabin_max,
        )

        simulation_config = SimulationConfig(
            num_seatrades=num_seatrades,
            num_cabins=num_cabins,
            num_preferences=num_preferences,
            camper_per_seatrade_min=camper_per_seatrade_min,
            camper_per_seatrade_max=camper_per_seatrade_max,
            camper_per_cabin_min=camper_per_cabin_min,
            camper_per_cabin_max=camper_per_cabin_max,
        )
        st.form_submit_button(
            "Submit",
            on_click=_update_simulation_config,
            kwargs={"simulation_config": simulation_config},
        )


def _get_simulation_config():
    """Generate / Return config for the mock data parameters."""
    return SimulationConfig()


def _update_simulation_config(simulation_config: SimulationConfig):
    """Update config for the mock data parameters."""
    st.session_state["simulation_config"] = simulation_config


def _optimization_config_form():
    """Component: Optimization Config Form"""
    with st.form("Optimization Config") as simulation_config_form:
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
                if "num_seatrades" in st.session_state
                else SimulationConfig().num_seatrades
            ),
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


def _get_optimization_config():
    """Generate / Return config for the optimization parameters."""
    return OptimizationConfig()


def _update_optimization_config(optimization_config: OptimizationConfig):
    """Update config for the optimization parameters."""
    st.session_state["optimization_config"] = optimization_config


def _get_seatrade_preferences(
    simulation_config: SimulationConfig,
) -> preferences.SeatradesConfig:
    """Get our seatrade preferences for our optimization problem."""
    # Mock Data for Now
    seatrades_prefs_dict = {
        f"Seatrade{n:0>2}": {
            "campers_min": (temp := np.random.randint(0, 1)),
            "campers_max": temp
            + (
                np.random.randint(
                    simulation_config.camper_per_seatrade_min,
                    simulation_config.camper_per_seatrade_max,
                )
            ),
        }
        for n in range(simulation_config.num_seatrades)
    }
    seatrades_prefs = pd.DataFrame(seatrades_prefs_dict).T.reset_index(names="seatrade")
    return preferences.SeatradesConfig.validate(seatrades_prefs)


def _get_cabin_camper_preferences(
    simulation_config: SimulationConfig,
    seatrade_preferences: preferences.SeatradesConfig,
) -> preferences.CamperSeatradePreferences:
    """Get our cabin-camper preferences for our optimization problem."""
    # Mock Cabins for Now
    cabins = [f"Cabin{i:0>2}" for i in range(simulation_config.num_cabins)]

    # Mock Campers and Preferences for Now
    camper_prefs = {}
    num_campers = 0
    for cabin in cabins:
        cabin_info = {}
        for camper in range(
            np.random.randint(
                simulation_config.camper_per_cabin_min,
                simulation_config.camper_per_cabin_max,
            )
        ):
            camper_name = f"Camper{num_campers:0>3}"
            seatrade_prefs = sample(
                seatrade_preferences["seatrade"].tolist(),
                simulation_config.num_preferences,
            )
            cabin_info[camper_name] = seatrade_prefs
            num_campers += 1
        camper_prefs[cabin] = cabin_info

    cabin_camper_prefs = (
        pd.DataFrame(camper_prefs)
        .reset_index(names="camper")
        .melt(id_vars=["camper"], var_name="cabin", value_name="seatrade")
        .dropna(subset="seatrade")
        .reset_index(drop=True)
    )
    # Add Gender based on Cabin
    for cabin in cabin_camper_prefs["cabin"].unique():
        cabin_camper_prefs.loc[cabin_camper_prefs["cabin"] == cabin, "gender"] = (
            np.random.choice(["male", "female"])
        )

    # This is inefficient from a wrangling point of view but it's okay it's just to start.
    cabin_camper_prefs = cabin_camper_prefs.drop(columns="seatrade").join(
        pd.DataFrame(
            cabin_camper_prefs["seatrade"].to_list(),
            columns=[
                f"seatrade_{i+1}" for i in range(simulation_config.num_preferences)
            ],
        )
    )
    return preferences.CamperSeatradePreferences.validate(cabin_camper_prefs)


def _create_seatrades(
    cabin_camper_preferences: preferences.CamperSeatradePreferences,
    seatrade_preferences: preferences.SeatradesConfig,
) -> seatrades.Seatrades:
    return seatrades.Seatrades(cabin_camper_preferences, seatrade_preferences)


def _assign_seatrades(
    seatrades: seatrades.Seatrades, optimization_config: OptimizationConfig
) -> seatrades.Seatrades:
    handler = setup_logging()
    with st.spinner("Assigning Seatrades..."):
        solved_problem = seatrades.assign(
            preference_weight=optimization_config.preference_weight,
            cabins_weight=optimization_config.cabins_weight,
            sparsity_weight=optimization_config.sparsity_weight,
            max_seatrades_per_fleet=optimization_config.max_seatrades_per_fleet,
            solver=optimization_config.solver,
        )
    if seatrades.status and seatrades.status > 0:
        print("Solved!")
        handler.clear_logs()  # Clear logs after conversion
    else:
        print("Failed to solve!")
        handler.log_error("Failed to solve!")  # Log error after conversion

    return seatrades


if __name__ == "__main__":
    main()
