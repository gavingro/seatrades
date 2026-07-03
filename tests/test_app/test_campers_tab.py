"""Camper simulation form tests — age sliders render and the base-age guard binds."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from tests.test_app.helpers import PRESOLVE_TIMEOUT_SECONDS

APP_SCRIPT = str(Path(__file__).resolve().parents[2] / "app.py")


def _slider(at, needle):
    return next(s for s in at.slider if needle in s.label.lower())


def _simulate_button(at):
    return next(b for b in at.button if b.label == "Simulate Campers")


class TestAgeSimulationSliders:
    def test_three_age_sliders_render_with_defaults(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()

        assert not at.exception
        assert _slider(at, "base age (min)").value == 13
        assert _slider(at, "base age (max)").value == 16
        assert _slider(at, "age spread").value == 0.7

    def test_rejects_base_age_min_not_less_than_max(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()

        _slider(at, "base age (min)").set_value(18)
        _slider(at, "base age (max)").set_value(14)
        at.run()
        _simulate_button(at).click()
        at.run()

        assert not at.exception
        assert any("base age" in t.value.lower() for t in at.toast)
