"""Shared AppTest helpers (widget lookups and solve polling) for the app-integration tests."""

import time
from pathlib import Path

from streamlit.testing.v1 import AppTest

# The app under test, resolved from this file's location (no external input).
APP_SCRIPT = str(Path(__file__).resolve().parents[2] / "app.py")
# A real CBC solve finishes in well under a minute locally; 180s is generous headroom.
SOLVE_TIMEOUT_SECONDS = 180


def click_assign(at: AppTest) -> None:
    """Click the "Assign Seatrades" button, starting the async solve."""
    buttons = [button for button in at.button if "Assign" in button.label]
    assert buttons, "Assign Seatrades button not found"
    buttons[0].click().run()


def poll_until_solution(at: AppTest, timeout_seconds: float, interval_seconds: float = 2) -> None:
    """Re-run the app until the async solve finalizes ``assigned_solution``.

    The solve is async (ADR-0004): clicking Assign starts a background SolveRun the
    UI polls via ``@st.fragment``. AppTest does not auto-advance ``run_every`` timers,
    so poll it here — re-running until the solve fills ``assigned_solution`` (None
    until finalized; the key exists from startup, so poll on the value). Asserts the
    solve finished within ``timeout_seconds``.
    """
    deadline = time.time() + timeout_seconds
    while at.session_state["assigned_solution"] is None and time.time() < deadline:
        time.sleep(interval_seconds)
        at.run()
        assert not at.exception
    assert at.session_state["assigned_solution"] is not None, "solve did not finish within timeout"


def find_slider(at, label_substring):
    """Return the first slider whose label contains ``label_substring`` (case-insensitive)."""
    return next(s for s in at.slider if label_substring.lower() in s.label.lower())


def find_button(at, label_substring):
    """Return the first button whose label contains ``label_substring`` (case-insensitive)."""
    return next(b for b in at.button if label_substring.lower() in b.label.lower())
