"""Fixtures for assignments_tab tests."""
import pandas as pd
import pytest


@pytest.fixture
def sample_assigned_df():
    """DataFrame with all campers assigned (assignment == 1.0).

    Suitable for testing sort orders. Data:
    - 5 campers across 2 cabins
    - All in block 1a except Alice (2a)
    """
    data = {
        "camper": ["Zed", "Alice", "Bob", "Carol", "Dave"],
        "cabin": ["Cabin2", "Cabin1", "Cabin1", "Cabin2", "Cabin2"],
        "block": ["1a", "2a", "1a", "1a", "1a"],
        "seatrade": ["Archery", "Kayaking", "Archery", "Climbing", "Sailing"],
        "assignment": [1.0, 1.0, 1.0, 1.0, 1.0],
        "preference": [1, 2, 1, 1, 1],
    }
    return pd.DataFrame(data)


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
