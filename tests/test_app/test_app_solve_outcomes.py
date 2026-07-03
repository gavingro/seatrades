"""Slow, real-CBC integration test for the infeasible solve outcome.

Most solve outcomes (optimal, timeout, error) are seeded into session_state and
asserted without a real solve. The infeasible path is the one case the solve
itself is under test — so this test feeds a deterministically unsolvable input to
CBC through the whole app and confirms the plain-language failure warning renders
(telling the Captain how to relax a limit) rather than an exception. Spans every
tab plus the solver, so it lives at the package level per ADR 0002.

Determinism (no RNG): each camper must occupy exactly one session per half-week
fleet-pair, and each session holds at most ``campers_max`` campers. With 4
seatrades at ``campers_max = 1``, the first half offers 2 blocks × 4 seatrades = 8
camper-slots; 12 campers cannot fit (pigeonhole), so the model is infeasible
regardless of preferences or fleet split. CBC presolve proves this instantly.
"""

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from seatrades import preferences
from seatrades.config import PREF_COLS
from seatrades.results import SolverState
from tests.test_app.helpers import poll_until_solution

APP_SCRIPT = str(Path(__file__).resolve().parents[2] / "app.py")
SOLVE_TIMEOUT_SECONDS = 180

# 4 seatrades — the minimum a camper needs to fill four unique ranked preferences.
_SEATRADES = ["Archery", "Crafts", "Climbing", "Sailing"]
# Two cabins (one each gender) of 6 → 12 campers. 12 > 8 first-half slots → infeasible.
_CABINS = [("Puffin", "female"), ("Tillikum", "male")]
_CAMPERS_PER_CABIN = 6


def _undersized_capacity_inputs() -> dict[str, pd.DataFrame]:
    """Build a deterministic infeasible week: capacity too small to seat everyone.

    Returns the four session_state frames the solve reads. All pass their Pandera
    schemas and ``join_and_validate`` cross-references; only the solve is infeasible.
    """
    seatrade_preferences = pd.DataFrame({"seatrade": _SEATRADES, "campers_min": 0, "campers_max": 1})

    identity_rows = []
    preference_rows = []
    for cabin, gender in _CABINS:
        for i in range(_CAMPERS_PER_CABIN):
            camper = f"{cabin} Camper {i}"
            identity_rows.append({"cabin": cabin, "camper": camper, "gender": gender, "age": 14})
            preference_rows.append({"camper": camper, **dict(zip(PREF_COLS, _SEATRADES, strict=True))})

    return {
        "seatrade_preferences": preferences.SeatradesConfig.validate(seatrade_preferences),
        "camper_identity": preferences.CamperIdentity.validate(pd.DataFrame(identity_rows)),
        "camper_preferences": preferences.CamperPreferences.validate(pd.DataFrame(preference_rows)),
        "camper_relationships": preferences.empty_relationships(),
    }


@pytest.mark.slow
class TestInfeasibleSolveOutcome:
    def test_infeasible_solve_renders_failure_warning(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=SOLVE_TIMEOUT_SECONDS)

        # Seed defaults, then replace the week with the undersized-capacity input.
        at.run()
        assert not at.exception
        for key, frame in _undersized_capacity_inputs().items():
            at.session_state[key] = frame
        at.session_state["introduced"] = True  # skip the welcome dialog

        # Start the real async solve.
        assign = [button for button in at.button if "Assign" in button.label]
        assert assign, "Assign Seatrades button not found"
        assign[0].click().run()
        assert not at.exception

        # Poll the fragment to completion (assigned_solution is None until finalized).
        poll_until_solution(at, SOLVE_TIMEOUT_SECONDS)

        # The solve finished as infeasible — not a crash, not a timeout.
        solution = at.session_state["assigned_solution"]
        assert solution.status.state is SolverState.INFEASIBLE
        assert at.session_state["optimization_success"] is False

        # The done view shows the plain-language relax-a-hard-limit warning.
        warnings = [w for w in at.warning if "relaxing a hard limit" in w.value]
        assert warnings, "expected the relax-a-hard-limit failure warning"
