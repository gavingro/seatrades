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

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from seatrades import preferences
from seatrades.config import (
    PREF_COLS,
    CamperSimulationConfig,
    OptimizationConfig,
    SeatradeSimulationConfig,
)
from seatrades.results import AssignmentSolution, SolverState, SolverStatus
from tests.test_app.helpers import (
    APP_SCRIPT,
    PRESOLVE_TIMEOUT_SECONDS,
    SOLVE_TIMEOUT_SECONDS,
    click_assign,
    poll_until_solution,
)

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


def _seed_failed_solve(status: SolverStatus) -> AppTest:
    """Seed a finished, unsuccessful solve into a fresh app and render the done view.

    A timeout returns no schedule, so only the status matters — the assignments and domain
    frames are empty. Config objects are pre-seeded so ``_initial_page_setup`` doesn't wipe
    the seeded solution (same guard as the done-view tests). No real solve runs, so this is
    fast — the TIMEOUT copy is a pure ``status -> message`` seam.
    """
    solution = AssignmentSolution(
        assignments=pd.DataFrame(),
        status=status,
        cabins=[],
        campers=[],
        seatrades_full=[],
        cabin_camper_prefs=pd.DataFrame(),
        camper_prefs=pd.Series(dtype=object),
        camper_names=pd.Series(dtype=object),
    )
    at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
    at.session_state["optimization_config"] = OptimizationConfig()
    at.session_state["seatrade_simulation_config"] = SeatradeSimulationConfig()
    at.session_state["camper_simulation_config"] = CamperSimulationConfig()
    at.session_state["assigned_solution"] = solution
    at.session_state["optimization_success"] = False
    at.session_state["solver_log"] = "Result - Stopped on time limit"
    at.session_state["introduced"] = True
    at.run()
    return at


class TestTimeoutSolveOutcome:
    def test_timeout_renders_time_size_message_not_a_crash(self):
        at = _seed_failed_solve(SolverStatus(state=SolverState.TIMEOUT, timed_out=True))

        assert not at.exception
        warnings = [w.value for w in at.warning]
        assert any("time limit" in w.lower() for w in warnings), "expected the time/size message"
        assert not any("unexpected error" in w.lower() for w in warnings)


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
        click_assign(at)
        assert not at.exception

        # Poll the fragment to completion (assigned_solution is None until finalized).
        poll_until_solution(at, SOLVE_TIMEOUT_SECONDS)

        # The solve finished as infeasible — not a crash, not a timeout — and the
        # post-mortem named the capacity shortfall as a proven cause.
        solution = at.session_state["assigned_solution"]
        assert solution.status.state is SolverState.INFEASIBLE
        assert at.session_state["optimization_success"] is False
        assert any("Too many campers" in f.cause for f in solution.findings), (
            "the capacity-shortfall cause should be diagnosed"
        )

        # The done view prepends the named cause + fix above the retained generic warning.
        warning = next(w.value for w in at.warning if "relaxing a hard limit" in w.value)
        assert "Too many campers" in warning
        assert warning.index("Too many campers") < warning.index("relaxing a hard limit")
