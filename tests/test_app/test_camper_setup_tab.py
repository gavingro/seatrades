"""Camper Setup tab pre-solve workflows: regenerate, resize, guard — no CBC solve."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tests.test_app.helpers import PRESOLVE_TIMEOUT_SECONDS, find_button, find_slider

APP_SCRIPT = str(Path(__file__).resolve().parents[2] / "app.py")


class TestRegenerateCampers:
    @pytest.mark.usefixtures("no_cbc_solve")
    def test_regenerate_campers_then_assign_starts_run(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()

        find_button(at, "Simulate Campers").click()
        at.run()
        find_button(at, "Assign Seatrades").click()
        at.run()

        assert not at.exception
        assert "solve_run" in at.session_state
        assert at.session_state["solve_run"].started is True

    def test_regenerate_campers_clears_previous_schedule(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()

        at.session_state["assigned_solution"] = object()  # a prior schedule
        find_button(at, "Simulate Campers").click()
        at.run()

        assert not at.exception
        assert at.session_state["assigned_solution"] is None


class TestSimulationSliders:
    def test_camper_sliders_resize_roster(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()

        find_slider(at, "Number of cabins").set_value(3)
        at.run()
        find_button(at, "Simulate Campers").click()
        at.run()

        assert not at.exception
        assert at.session_state["camper_identity"]["cabin"].nunique() == 3

    def test_invalid_camper_config_warns_no_crash(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()
        roster_before = at.session_state["camper_identity"].copy()

        find_slider(at, "Campers per cabin (min)").set_value(20)
        find_slider(at, "Campers per cabin (max)").set_value(10)
        at.run()
        find_button(at, "Simulate Campers").click()
        at.run()

        assert not at.exception
        assert any("min must be less than max" in t.value for t in at.toast)
        # Early return: the roster was not regenerated.
        assert at.session_state["camper_identity"].equals(roster_before)


class TestOptimizationConfigReachesRun:
    @pytest.mark.usefixtures("no_cbc_solve")
    def test_optimization_sliders_flow_into_run(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()

        find_slider(at, "keep similar ages together").set_value(5)
        next(c for c in at.checkbox if "same fleet" in c.label.lower()).check()
        at.run()
        find_button(at, "Submit").click()
        at.run()

        find_button(at, "Assign Seatrades").click()
        at.run()

        assert not at.exception
        run_config = at.session_state["solve_run"].config
        assert run_config.age_weight == 5
        assert run_config.force_same_fleet_all_week is True
