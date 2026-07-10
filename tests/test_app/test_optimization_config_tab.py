"""Optimization config form tests — the same-fleet toggle flows into OptimizationConfig."""

from streamlit.testing.v1 import AppTest

from tests.test_app.helpers import (
    APP_SCRIPT,
    PRESOLVE_TIMEOUT_SECONDS,
    find_button,
    find_checkbox,
    find_slider,
)


class TestAgeSliders:
    def test_age_weight_slider_feeds_config(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()

        find_slider(at, "keep similar ages together").set_value(4)
        at.run()
        find_button(at, "Submit").click()
        at.run()

        assert at.session_state["optimization_config"].age_weight == 4

    def test_age_balance_slider_feeds_config(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()

        find_slider(at, "favor fleet-wide").set_value(0.9)
        at.run()
        find_button(at, "Submit").click()
        at.run()

        assert at.session_state["optimization_config"].age_balance == 0.9


class TestCabinVarietySliders:
    def test_variety_weight_slider_feeds_config(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()

        find_slider(at, "cabin variety").set_value(5)
        at.run()
        find_button(at, "Submit").click()
        at.run()

        assert at.session_state["optimization_config"].cabin_variety_weight == 5

    def test_one_cabin_share_slider_feeds_config(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()

        find_slider(at, "max one-cabin share").set_value(50)
        at.run()
        find_button(at, "Submit").click()
        at.run()

        assert at.session_state["optimization_config"].max_cabin_share_per_seatrade == 0.5

    def test_one_cabin_share_defaults_to_off(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()

        find_button(at, "Submit").click()
        at.run()

        assert at.session_state["optimization_config"].max_cabin_share_per_seatrade == 1.0


class TestSameFleetToggle:
    def test_unchecked_yields_flag_false(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()

        find_button(at, "Submit").click()
        at.run()

        assert at.session_state["optimization_config"].force_same_fleet_all_week is False

    def test_checked_yields_flag_true(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()

        find_checkbox(at, "same fleet").check()
        at.run()
        find_button(at, "Submit").click()
        at.run()

        assert at.session_state["optimization_config"].force_same_fleet_all_week is True
