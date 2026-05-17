"""Fixtures for seatrades service-layer tests."""

import pandas as pd
import pytest

from seatrades.results import AssignmentSolution, SolverState, SolverStatus


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
        "block": ["2a", "1a", "1a", "1a"],
        "seatrade": ["Archery", "Archery", "Climbing", "Archery"],
        "assignment": [1.0, 1.0, 1.0, 1.0],
        "preference": [1, 2, 1, 1],
    }
    return pd.DataFrame(data)


@pytest.fixture
def sample_assignment_solution():
    """Minimal AssignmentSolution matching PuLP output format.

    4 campers across 2 cabins, 2 blocks (1a, 2b), 3 seatrades.
    """
    assignments_df = pd.DataFrame(
        {
            "1a_Archery": [1.0, 0.0, 0.0, 1.0],
            "1a_Sailing": [0.0, 1.0, 0.0, 0.0],
            "1a_Climbing": [0.0, 0.0, 1.0, 0.0],
            "2b_Archery": [0.0, 0.0, 1.0, 0.0],
            "2b_Sailing": [1.0, 0.0, 0.0, 0.0],
            "2b_Climbing": [0.0, 1.0, 0.0, 1.0],
        },
        index=pd.Index(["Alice_0", "Bob_0", "Carol_0", "Dave_0"], name="camper"),
    )
    status = SolverStatus(state=SolverState.OPTIMAL)
    return AssignmentSolution(
        assignments=assignments_df,
        status=status,
        cabins=["Cabin1", "Cabin2"],
        campers=["Alice_0", "Bob_0", "Carol_0", "Dave_0"],
        seatrades_full=["1a_Archery", "1a_Sailing", "1a_Climbing", "2b_Archery", "2b_Sailing", "2b_Climbing"],
        cabin_camper_prefs=pd.DataFrame(
            {"cabin": ["Cabin1", "Cabin1", "Cabin2", "Cabin2"]},
            index=pd.Index(["Alice_0", "Bob_0", "Carol_0", "Dave_0"], name="camper"),
        ),
        camper_prefs=pd.Series(
            [
                ["Archery", "Sailing", "Climbing", "Kayaking"],
                ["Climbing", "Archery", "Sailing", "Kayaking"],
                ["Sailing", "Archery", "Climbing", "Kayaking"],
                ["Archery", "Climbing", "Sailing", "Kayaking"],
            ],
            index=pd.Index(["Alice_0", "Bob_0", "Carol_0", "Dave_0"], name="camper"),
        ),
    )
