"""Seatrade Setup tab pre-solve workflows: regenerate, resize, Assign guards — no CBC solve."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tests.test_app.helpers import PRESOLVE_TIMEOUT_SECONDS, find_button, find_slider

APP_SCRIPT = str(Path(__file__).resolve().parents[2] / "app.py")


class TestRegenerateSeatrades:
    @pytest.mark.usefixtures("no_cbc_solve")
    def test_regenerate_seatrades_then_assign_starts_run(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()

        find_button(at, "Update Seatrade Simulation Settings").click()
        at.run()  # re-seeds all data from the updated config
        find_button(at, "Assign Seatrades").click()
        at.run()

        assert not at.exception
        assert "solve_run" in at.session_state
        assert at.session_state["solve_run"].started is True


class TestSimulationSliders:
    def test_seatrade_slider_resizes_offerings(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()

        find_slider(at, "Number of seatrades").set_value(4)
        at.run()
        find_button(at, "Update Seatrade Simulation Settings").click()
        at.run()

        assert not at.exception
        assert len(at.session_state["seatrade_preferences"]) == 4

    def test_invalid_seatrade_capacity_warns_no_crash(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()
        seatrades_before = at.session_state["seatrade_preferences"].copy()

        find_slider(at, "Camper capacity per seatrade (min)").set_value(20)
        find_slider(at, "Camper capacity per seatrade (max)").set_value(10)
        at.run()
        find_button(at, "Update Seatrade Simulation Settings").click()
        at.run()

        assert not at.exception
        assert any("strictly less than" in t.value for t in at.toast)
        assert at.session_state["seatrade_preferences"].equals(seatrades_before)


class TestAssignGuards:
    def test_assign_missing_data_prompts(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()

        del at.session_state["camper_identity"]
        find_button(at, "Assign Seatrades").click()
        at.run()

        assert not at.exception
        assert any("Missing camper or seatrade data" in t.value for t in at.toast)
        assert "solve_run" not in at.session_state

    def test_assign_mismatched_data_cross_reference_error(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()

        # A camper in preferences that identity doesn't know → cross-reference fails.
        bad_prefs = at.session_state["camper_preferences"].copy()
        bad_prefs.iloc[0, bad_prefs.columns.get_loc("camper")] = "GHOST_CAMPER"
        at.session_state["camper_preferences"] = bad_prefs
        find_button(at, "Assign Seatrades").click()
        at.run()

        assert not at.exception
        assert any("Cross-reference validation failed" in t.value for t in at.toast)
        assert "solve_run" not in at.session_state
