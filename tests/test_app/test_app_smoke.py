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

import pytest
from streamlit.testing.v1 import AppTest

from tests.test_app.helpers import (
    APP_SCRIPT,
    SOLVE_TIMEOUT_SECONDS,
    click_assign,
    poll_until_solution,
)


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
        click_assign(at)
        assert not at.exception

        # Poll the fragment to completion: each at.run() re-polls progress(); the
        # finalizing tick fills assigned_solution.
        poll_until_solution(at, SOLVE_TIMEOUT_SECONDS)

        # Confirm the solve finished cleanly with a usable schedule.
        assert at.session_state["optimization_success"] is True
        assert at.success, "expected a success message after solving"

        # The final CBC log is retained and viewable after the solve concludes.
        assert at.session_state["solver_log"], "solver log not retained after solve"
        log_areas = [area for area in at.text_area if area.label == "Solver Logs"]
        assert log_areas, "solver log not shown in the done view"
        assert log_areas[0].value == at.session_state["solver_log"]
