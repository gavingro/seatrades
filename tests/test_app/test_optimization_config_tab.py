"""Optimization config form tests — the same-fleet toggle flows into OptimizationConfig."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_SCRIPT = str(Path(__file__).resolve().parents[2] / "app.py")


def _same_fleet_checkbox(at):
    return next(c for c in at.checkbox if "same fleet" in c.label.lower())


def _submit(at):
    return next(b for b in at.button if b.label == "Submit")


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
