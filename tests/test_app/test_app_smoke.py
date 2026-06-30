"""End-to-end smoke test: drive the whole app through a real solve.

Mirrors the manual browser check (ADR 0007) headlessly via Streamlit AppTest:
open the app, dismiss the intro dialog, click "Assign Seatrades.", let the CBC
solver finish, and confirm the run raises no Streamlit exceptions and produces a
schedule. Spans every tab plus the solver, so it lives at the package level per
ADR 0002.

The solve is async (ADR-0004): clicking Assign starts a background SolveRun and
the UI polls it via ``@st.fragment``. AppTest does not auto-advance ``run_every``
timers, so the test polls completion itself — re-running the app until the solve
finalizes its result into session_state.
"""

import time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP_SCRIPT = str(Path(__file__).resolve().parents[2] / "app.py")
# A real CBC solve on the default simulated week; finishes in ~10s locally.
SOLVE_TIMEOUT_SECONDS = 180


@pytest.mark.slow
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

        # Start the async solve.
        assign = [button for button in at.button if "Assign" in button.label]
        assert assign, "Assign Seatrades button not found"
        assign[0].click().run()
        assert not at.exception

        # Poll the fragment to completion: each at.run() re-polls progress(); the
        # finalizing tick fills assigned_solution (None until the solve finishes —
        # the key exists from startup, so poll on the value, not key presence).
        deadline = time.time() + SOLVE_TIMEOUT_SECONDS
        while at.session_state["assigned_solution"] is None and time.time() < deadline:
            time.sleep(2)
            at.run()
            assert not at.exception

        # Confirm the solve finished cleanly with a usable schedule.
        assert at.session_state["assigned_solution"] is not None, "solve did not finish within timeout"
        assert at.session_state["optimization_success"] is True
        assert at.success, "expected a success message after solving"
