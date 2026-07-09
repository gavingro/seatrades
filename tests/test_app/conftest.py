"""Shared fixtures for the app-integration (AppTest) tests."""

from typing import Optional

import pandas as pd
import pytest

from seatrades.config import OptimizationConfig
from seatrades.problem import SchedulingProblem
from seatrades.results import AssignmentSolution
from seatrades.solve_run import SolveProgress


class _NoSolveRun:
    """SolveRun stand-in: captures the built problem/config, never spawns a CBC solve.

    Lets pre-solve tests click "Assign" and assert on the resulting run/config without
    paying for a real solve. Reports ``running=True`` so the poll fragment renders and
    never finalizes. ``problem``/``config``/``started`` are public test spies — the real
    SolveRun keeps problem/config private — so leave them public for the assertions.
    """

    def __init__(self, problem: SchedulingProblem, config: OptimizationConfig) -> None:
        self.problem = problem
        self.config = config
        self.started = False

    def start(self) -> None:
        self.started = True

    def progress(self) -> SolveProgress:
        return SolveProgress(
            running=True,
            percent=0.0,
            message="Optimizing seatrade assignments…",
            log_text="",
            timed_out=False,
        )

    def result(self) -> Optional[AssignmentSolution]:
        return None


@pytest.fixture
def no_cbc_solve(monkeypatch):
    """Swap SolveRun for a no-solve fake so clicking Assign starts no real solve."""
    import app.tabs.assignments_tab as assignments_tab

    monkeypatch.setattr(assignments_tab, "SolveRun", _NoSolveRun)


@pytest.fixture
def sample_mixed_assignment_df():
    """DataFrame with mix of assigned and unassigned rows."""
    data = {
        "camper": ["Alice", "Bob", "Carol"],
        "cabin": ["Cabin1", "Cabin1", "Cabin2"],
        "block": ["1a", "1a", "1a"],
        "seatrade": ["Archery", "Kayaking", "Archery"],
        "assignment": [1.0, 0.0, 1.0],
        # preference_rank is carried on every cell (a pure camper↔seatrade fact), so the
        # unassigned Kayaking row keeps its rank — no conflated 0.
        "preference_rank": [1, 4, 1],
    }
    return pd.DataFrame(data)


@pytest.fixture
def seatrade_sort_df():
    """DataFrame for testing seatrade sort order.

    Designed to verify block → seatrade → cabin → camper sorting.
    """
    data = {
        "camper": ["Zed", "Alice", "Bob", "Carol"],
        "cabin": ["Cabin2", "Cabin1", "Cabin1", "Cabin2"],
        "age": [16, 13, 14, 15],
        "block": ["2a", "1a", "1a", "1a"],
        "seatrade": ["Archery", "Archery", "Climbing", "Archery"],
        "assignment": [1.0, 1.0, 1.0, 1.0],
        "preference_rank": [1, 2, 1, 1],
    }
    return pd.DataFrame(data)
