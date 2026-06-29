"""End-to-end smoke test: drive the whole app through a real solve.

Mirrors the manual browser check (ADR 0007) headlessly via Streamlit AppTest:
open the app, dismiss the intro dialog, click "Assign Seatrades.", let the CBC
solver finish, and confirm the run raises no Streamlit exceptions and produces a
schedule. Spans every tab plus the solver, so it lives at the package level per
ADR 0002.
"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_SCRIPT = str(Path(__file__).resolve().parents[2] / "app.py")
# A real CBC solve on the default simulated week; finishes in ~10s locally.
SOLVE_TIMEOUT_SECONDS = 180


class TestAppSmoke:
    def test_assign_seatrades_end_to_end(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=SOLVE_TIMEOUT_SECONDS)

        # Open the app — auto-seeds mock data, shows the welcome dialog.
        at.run()
        assert not at.exception

        # Dismiss the welcome dialog (sets introduced=True, same as the ✕).
        dismiss = [button for button in at.button if "Don't show" in button.label]
        assert dismiss, "intro dialog dismiss button not found"
        dismiss[0].click().run()
        assert not at.exception

        # Run the solve.
        assign = [button for button in at.button if "Assign" in button.label]
        assert assign, "Assign Seatrades button not found"
        assign[0].click().run()

        # Confirm the solve finished cleanly with a usable schedule.
        assert not at.exception
        assert at.session_state["optimization_success"] is True
        assert "assigned_solution" in at.session_state
        assert at.success, "expected a success message after solving"
