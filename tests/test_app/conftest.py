"""Fixtures for assignments_tab tests."""

import pandas as pd
import pytest

from seatrades.solve_run import SolveProgress


class _NoSolveRun:
    """SolveRun stand-in: captures the built problem/config, never spawns a CBC solve.

    Lets pre-solve tests click "Assign" and assert on the resulting run/config without
    paying for a real solve. Reports ``running=True`` so the poll fragment renders and
    never finalizes.
    """

    def __init__(self, problem, config):
        self.problem = problem
        self.config = config
        self.started = False

    def start(self):
        self.started = True

    def progress(self) -> SolveProgress:
        return SolveProgress(
            running=True,
            percent=0.0,
            message="Optimizing seatrade assignments…",
            log_text="",
            timed_out=False,
        )

    def result(self):
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
        "preference": [1, 0, 1],
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
        "preference": [1, 2, 1, 1],
    }
    return pd.DataFrame(data)
