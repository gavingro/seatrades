"""Fixtures for seatrades service-layer tests."""

import pandas as pd
import pytest

from seatrades.config import OptimizationConfig
from seatrades.problem import SchedulingProblem
from seatrades.results import AssignmentSolution, SolverState, SolverStatus


@pytest.fixture
def joined_campers_df():
    """DataFrame matching output of join_and_validate().

    4 campers across 2 cabins, 4 seatrade preferences each.
    Plain camper names; SchedulingProblem assigns each an integer camper_id.
    """
    return pd.DataFrame(
        {
            "cabin": ["Cabin1", "Cabin1", "Cabin2", "Cabin2"],
            "camper": ["Alice", "Bob", "Carol", "Dave"],
            "gender": ["F", "M", "F", "M"],
            "age": [13, 14, 15, 16],
            "seatrade_1": ["Archery", "Climbing", "Sailing", "Archery"],
            "seatrade_2": ["Sailing", "Archery", "Archery", "Climbing"],
            "seatrade_3": ["Climbing", "Sailing", "Climbing", "Sailing"],
            "seatrade_4": ["Kayaking", "Kayaking", "Kayaking", "Kayaking"],
        }
    )


@pytest.fixture
def seatrade_setup_df():
    """DataFrame matching the seatrade_setup output of join_and_validate().

    4 seatrades with capacity constraints.
    """
    return pd.DataFrame(
        {
            "seatrade": ["Archery", "Sailing", "Climbing", "Kayaking"],
            "campers_min": [0, 0, 0, 0],
            "campers_max": [10, 10, 10, 10],
        }
    )


@pytest.fixture
def default_config():
    """OptimizationConfig with default values."""
    return OptimizationConfig()


@pytest.fixture
def scheduling_problem(joined_campers_df, seatrade_setup_df):
    """SchedulingProblem constructed from fixture DataFrames."""
    return SchedulingProblem(joined_campers_df, seatrade_setup_df)


@pytest.fixture
def sample_mixed_assignment_df():
    """DataFrame with mix of assigned and unassigned rows."""
    data = {
        "camper": ["Alice", "Bob", "Carol"],
        "cabin": ["Cabin1", "Cabin1", "Cabin2"],
        "block": ["1a", "1a", "1a"],
        "seatrade": ["Archery", "Kayaking", "Archery"],
        "assignment": [1.0, 0.0, 1.0],
        # preference_rank is a pure camper↔seatrade fact carried on every cell, so the
        # unassigned Kayaking row still has the rank the camper gave it — no conflated 0.
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
        "block": ["2a", "1a", "1a", "1a"],
        "seatrade": ["Archery", "Archery", "Climbing", "Archery"],
        "assignment": [1.0, 1.0, 1.0, 1.0],
        "preference_rank": [1, 2, 1, 1],
    }
    return pd.DataFrame(data)


@pytest.fixture
def sample_assignment_solution():
    """Minimal AssignmentSolution matching PuLP output format.

    4 campers across 2 cabins, 2 blocks (1a, 2b), 3 seatrades.
    Campers are keyed by integer camper_id internally; camper_names maps id->name.
    """
    camper_ids = pd.Index([0, 1, 2, 3], name="camper_id")
    assignments_df = pd.DataFrame(
        {
            "1a_Archery": [1.0, 0.0, 0.0, 1.0],
            "1a_Sailing": [0.0, 1.0, 0.0, 0.0],
            "1a_Climbing": [0.0, 0.0, 1.0, 0.0],
            "2b_Archery": [0.0, 0.0, 1.0, 0.0],
            "2b_Sailing": [1.0, 0.0, 0.0, 0.0],
            "2b_Climbing": [0.0, 1.0, 0.0, 1.0],
        },
        index=camper_ids,
    )
    status = SolverStatus(state=SolverState.OPTIMAL)
    return AssignmentSolution(
        assignments=assignments_df,
        status=status,
        cabins=["Cabin1", "Cabin2"],
        campers=["Alice", "Bob", "Carol", "Dave"],
        seatrades_full=["1a_Archery", "1a_Sailing", "1a_Climbing", "2b_Archery", "2b_Sailing", "2b_Climbing"],
        cabin_camper_prefs=pd.DataFrame(
            {"cabin": ["Cabin1", "Cabin1", "Cabin2", "Cabin2"], "age": [13, 14, 15, 16]},
            index=camper_ids,
        ),
        camper_prefs=pd.Series(
            [
                ["Archery", "Sailing", "Climbing", "Kayaking"],
                ["Climbing", "Archery", "Sailing", "Kayaking"],
                ["Sailing", "Archery", "Climbing", "Kayaking"],
                ["Archery", "Climbing", "Sailing", "Kayaking"],
            ],
            index=camper_ids,
        ),
        camper_names=pd.Series(["Alice", "Bob", "Carol", "Dave"], index=camper_ids),
    )
