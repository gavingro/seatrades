"""Optimization config form tests — the same-fleet toggle flows into OptimizationConfig."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_SCRIPT = str(Path(__file__).resolve().parents[2] / "app.py")


def _same_fleet_checkbox(at):
    return next(c for c in at.checkbox if "same fleet" in c.label.lower())


def _submit(at):
    return next(b for b in at.button if b.label == "Submit")


def _slider(at, label_substring):
    return next(s for s in at.slider if label_substring.lower() in s.label.lower())


class TestAgeSliders:
    def test_age_weight_slider_feeds_config(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=60)
        at.run()

        _slider(at, "keep similar ages together").set_value(4)
        at.run()
        _submit(at).click()
        at.run()

        assert at.session_state["optimization_config"].age_weight == 4

    def test_age_balance_slider_feeds_config(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=60)
        at.run()

        _slider(at, "favor fleet-wide").set_value(0.9)
        at.run()
        _submit(at).click()
        at.run()

        assert at.session_state["optimization_config"].age_balance == 0.9


class TestSameFleetToggle:
    def test_unchecked_yields_flag_false(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=60)
        at.run()

        _submit(at).click()
        at.run()

        assert at.session_state["optimization_config"].force_same_fleet_all_week is False

    def test_checked_yields_flag_true(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=60)
        at.run()

        _same_fleet_checkbox(at).check()
        at.run()
        _submit(at).click()
        at.run()

        assert at.session_state["optimization_config"].force_same_fleet_all_week is True
