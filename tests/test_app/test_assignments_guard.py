"""Single-run guard: the Assign button is disabled while a solve is in flight.

Drives the real app via Streamlit AppTest (prior art: test_friends_tab.py) with a
fake SolveRun seeded into session_state, so the guard is exercised without a real
solve. Asserting through the rendered button keeps the test on observable behavior.
"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from app.tabs.assignments_tab import ACTIVE_RUN_KEY
from seatrades.solve_run import SolveProgress
from tests.test_app.helpers import PRESOLVE_TIMEOUT_SECONDS

APP_SCRIPT = str(Path(__file__).resolve().parents[2] / "app.py")


class _RunningRun:
    """Fake SolveRun the fragment can poll: always reports an in-flight solve."""

    def progress(self) -> SolveProgress:
        return SolveProgress(
            running=True,
            percent=0.5,
            message="Optimizing seatrade assignments…",
            log_text="",
            timed_out=False,
        )

    def result(self) -> None:
        return None


class TestAssignGuard:
    def test_assign_disabled_while_a_run_is_active(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.session_state[ACTIVE_RUN_KEY] = _RunningRun()
        at.run()

        assert not at.exception
        assign = [button for button in at.button if "Assign" in button.label]
        assert assign, "Assign Seatrades button not found"
        assert assign[0].disabled, "Assign button should be disabled while a solve runs"

    def test_assign_enabled_when_idle(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()

        assert not at.exception
        assign = [button for button in at.button if "Assign" in button.label]
        assert assign, "Assign Seatrades button not found"
        assert not assign[0].disabled, "Assign button should be enabled when no solve runs"
