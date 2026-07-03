"""App-integration tests for the post-solve done view (issue #88).

Drives the whole app via Streamlit AppTest but jumps past the solver: a finished
``AssignmentSolution`` is seeded into ``session_state`` (pattern from
test_assignments_guard.py) so the done view renders without paying for a solve.
One real tiny CBC solve runs in a session-scoped fixture and is reused by every
test, so these stay fast and carry no ``slow`` marker.
"""

import dataclasses
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from seatrades import solver
from seatrades.config import (
    CamperSimulationConfig,
    OptimizationConfig,
    SeatradeSimulationConfig,
)
from seatrades.problem import SchedulingProblem
from seatrades.results import SolverState, SolverStatus
from tests.test_app.helpers import PRESOLVE_TIMEOUT_SECONDS

APP_SCRIPT = str(Path(__file__).resolve().parents[2] / "app.py")


@pytest.fixture(scope="session")
def solved_solution():
    """One real CBC solve on a tiny feasible roster, cached for the whole session.

    The 4-camper / 2-cabin roster mirrors tests/test_seatrades/conftest.py and is
    known to solve OPTIMAL under the default config, so the post-solve tests seed
    this fully-populated AssignmentSolution instead of solving themselves.
    """
    joined_campers = pd.DataFrame(
        {
            "cabin": ["Cabin1", "Cabin1", "Cabin2", "Cabin2"],
            "camper": ["Alice", "Bob", "Carol", "Dave"],
            "gender": ["F", "M", "F", "M"],
            "age": [13, 14, 15, 16],
            "seatrade_1": ["Archery", "Climbing", "Sailing", "Archery"],
            "seatrade_2": ["Sailing", "Archery", "Archery", "Climbing"],
            "seatrade_3": ["Climbing", "Sailing", "Climbing", "Sailing"],
            "seatrade_4": ["Kayaking", "Kayaking", "Kayaking", "Kayaking"],
        }
    )
    seatrade_setup = pd.DataFrame(
        {
            "seatrade": ["Archery", "Sailing", "Climbing", "Kayaking"],
            "campers_min": [0, 0, 0, 0],
            "campers_max": [10, 10, 10, 10],
        }
    )
    problem = SchedulingProblem(joined_campers, seatrade_setup)
    return solver.run(problem, OptimizationConfig())


def _seed_done_view(solution, success, log="Cbc0010I solved\nDone"):
    """Seed a finished solve into a fresh AppTest and render the done view."""
    at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
    # Pre-seed the config objects so _initial_page_setup skips its _update_* handlers;
    # those call clear_optimization_results(), which would wipe the seeded solution.
    at.session_state["optimization_config"] = OptimizationConfig()
    at.session_state["seatrade_simulation_config"] = SeatradeSimulationConfig()
    at.session_state["camper_simulation_config"] = CamperSimulationConfig()
    at.session_state["assigned_solution"] = solution
    at.session_state["optimization_success"] = success
    at.session_state["solver_log"] = log
    at.session_state["introduced"] = True  # skip the intro dialog
    at.run()
    return at


class TestDoneView:
    def test_by_camper_table_renders_with_schedule_data(self, solved_solution):
        """The done view opens on the By Camper table with schedule rows, no error."""
        at = _seed_done_view(solved_solution, success=True)

        assert not at.exception
        view = at.selectbox(key="assignment_view_selector")
        assert view.value == "By Camper"
        assert at.dataframe, "expected a rendered assignments table"
        assert not at.dataframe[0].value.empty, "By Camper table should hold schedule data"

    def test_toggle_to_by_seatrade_renders_without_error(self, solved_solution):
        """Switching the View selectbox to By Seatrade re-renders a table, no error."""
        at = _seed_done_view(solved_solution, success=True)

        at.selectbox(key="assignment_view_selector").set_value("By Seatrade").run()

        assert not at.exception
        assert at.selectbox(key="assignment_view_selector").value == "By Seatrade"
        assert at.dataframe, "expected a rendered assignments table"
        assert not at.dataframe[0].value.empty, "By Seatrade table should hold schedule data"

    def test_solver_log_expander_shows_the_final_log(self, solved_solution):
        """The done view keeps the final CBC log in a Solver Logs text_area."""
        at = _seed_done_view(solved_solution, success=True, log="Cbc0010I solved\nDone")

        assert not at.exception
        log_areas = [area for area in at.text_area if area.label == "Solver Logs"]
        assert log_areas, "solver log not shown in the done view"
        assert log_areas[0].value == at.session_state["solver_log"]

    def test_error_status_renders_finished_abnormally_warning(self, solved_solution):
        """A seeded ERROR solution surfaces the crash copy, not the tables, no exception."""
        error_solution = dataclasses.replace(
            solved_solution,
            status=SolverStatus(state=SolverState.ERROR, message="solver blew up"),
        )
        at = _seed_done_view(error_solution, success=False)

        assert not at.exception
        assert at.warning, "expected a failure warning"
        warning_text = at.warning[0].value
        assert "couldn't finish" in warning_text
        assert "solver blew up" in warning_text
