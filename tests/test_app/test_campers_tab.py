"""Camper simulation form tests — age sliders render and the base-age guard binds."""

from streamlit.testing.v1 import AppTest

from tests.test_app.helpers import APP_SCRIPT, PRESOLVE_TIMEOUT_SECONDS, find_button, find_slider


class TestAgeSimulationSliders:
    def test_three_age_sliders_render_with_defaults(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()

        assert not at.exception
        assert find_slider(at, "base age (min)").value == 13
        assert find_slider(at, "base age (max)").value == 16
        assert find_slider(at, "age spread").value == 0.7

    def test_rejects_base_age_min_not_less_than_max(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()

        find_slider(at, "base age (min)").set_value(18)
        find_slider(at, "base age (max)").set_value(14)
        at.run()
        find_button(at, "Simulate Campers").click()
        at.run()

        assert not at.exception
        assert any("base age" in t.value.lower() for t in at.toast)
