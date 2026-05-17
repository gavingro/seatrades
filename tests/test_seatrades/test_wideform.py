"""Tests for Seatrades.wrangle_assignments_to_wideform.

TODO: Add a test fixture with mixed assigned/unassigned rows (assignment == 0.0) to
verify wrangle_assignments_to_wideform correctly filters them out. Currently only
prepare_seatrade_leaders has this test coverage via sample_mixed_assignment_df.
"""

import pandas as pd
import pytest

from seatrades.results import prepare_seatrade_leaders, wrangle_assignments_to_wideform


@pytest.fixture
def longform_assigned():
    """Long-form assignments DataFrame with all campers assigned.

    Each camper is assigned to one seatrade in one block (1a or 1b, 2a or 2b).
    Camper gets exactly 2 assignments across 4 possible blocks.
    """
    rows = [
        # Cabin1 campers
        {
            "camper": "Alice",
            "cabin": "Cabin1",
            "block": "1a",
            "seatrade": "Archery",
            "assignment": 1.0,
            "preference": 1,
        },
        {
            "camper": "Alice",
            "cabin": "Cabin1",
            "block": "2b",
            "seatrade": "Sailing",
            "assignment": 1.0,
            "preference": 2,
        },
        {"camper": "Bob", "cabin": "Cabin1", "block": "1b", "seatrade": "Climbing", "assignment": 1.0, "preference": 1},
        {"camper": "Bob", "cabin": "Cabin1", "block": "2a", "seatrade": "Archery", "assignment": 1.0, "preference": 3},
        # Cabin2 campers
        {
            "camper": "Carol",
            "cabin": "Cabin2",
            "block": "1a",
            "seatrade": "Sailing",
            "assignment": 1.0,
            "preference": 1,
        },
        {
            "camper": "Carol",
            "cabin": "Cabin2",
            "block": "2b",
            "seatrade": "Archery",
            "assignment": 1.0,
            "preference": 2,
        },
        {"camper": "Dave", "cabin": "Cabin2", "block": "1b", "seatrade": "Archery", "assignment": 1.0, "preference": 1},
        {"camper": "Dave", "cabin": "Cabin2", "block": "2a", "seatrade": "Sailing", "assignment": 1.0, "preference": 2},
    ]
    return pd.DataFrame(rows)


class TestWideformShape:
    """Wide-form has 1 row per camper, 4 seatrade block columns."""

    def test_one_row_per_camper(self, longform_assigned):
        """Wide-form should have exactly 1 row per camper."""
        result = wrangle_assignments_to_wideform(longform_assigned)
        assert len(result) == 4  # Alice, Bob, Carol, Dave

    def test_column_order(self, longform_assigned):
        """Wide-form columns: cabin, camper, Seatrade 1a, Seatrade 1b, Seatrade 2a, Seatrade 2b."""
        result = wrangle_assignments_to_wideform(longform_assigned)
        assert result.columns.tolist() == [
            "cabin",
            "camper",
            "Seatrade 1a",
            "Seatrade 1b",
            "Seatrade 2a",
            "Seatrade 2b",
        ]


class TestWideformBlanks:
    """Each camper fills exactly 2 of 4 seatrade columns; the rest are Fleet Time."""

    def test_camper_fills_two_columns(self, longform_assigned):
        """Each camper has exactly 2 non-blank seatrade columns."""
        result = wrangle_assignments_to_wideform(longform_assigned)
        seatrade_cols = ["Seatrade 1a", "Seatrade 1b", "Seatrade 2a", "Seatrade 2b"]
        for _, row in result.iterrows():
            filled = sum(row[col] != "Fleet Time" for col in seatrade_cols)
            assert filled == 2, f"{row['camper']} should have 2 filled columns, got {filled}"

    def test_alice_assigned_correctly(self, longform_assigned):
        """Alice: 1a=Archery, 2b=Sailing, others blank."""
        result = wrangle_assignments_to_wideform(longform_assigned)
        alice = result[result["camper"] == "Alice"].iloc[0]
        assert alice["Seatrade 1a"] == "Archery"
        assert alice["Seatrade 1b"] == "Fleet Time"
        assert alice["Seatrade 2a"] == "Fleet Time"
        assert alice["Seatrade 2b"] == "Sailing"

    def test_bob_assigned_correctly(self, longform_assigned):
        """Bob: 1b=Climbing, 2a=Archery, others blank."""
        result = wrangle_assignments_to_wideform(longform_assigned)
        bob = result[result["camper"] == "Bob"].iloc[0]
        assert bob["Seatrade 1a"] == "Fleet Time"
        assert bob["Seatrade 1b"] == "Climbing"
        assert bob["Seatrade 2a"] == "Archery"
        assert bob["Seatrade 2b"] == "Fleet Time"


class TestWideformSort:
    """Wide-form sorted by cabin → camper."""

    def test_sorted_by_cabin_then_camper(self, longform_assigned):
        """Rows sorted by cabin, then camper alphabetically."""
        result = wrangle_assignments_to_wideform(longform_assigned)
        assert result["camper"].tolist() == ["Alice", "Bob", "Carol", "Dave"]
        assert result["cabin"].tolist() == ["Cabin1", "Cabin1", "Cabin2", "Cabin2"]


class TestCamperOrderSort:
    """When camper_order is provided, rows follow that order."""

    def test_sorts_by_camper_order(self, longform_assigned):
        """Rows follow camper_order, not cabin → camper."""
        camper_order = ["Dave", "Carol", "Bob", "Alice"]
        result = wrangle_assignments_to_wideform(longform_assigned, camper_order=camper_order)
        assert result["camper"].tolist() == ["Dave", "Carol", "Bob", "Alice"]

    def test_camper_order_missing_camper_raises(self, longform_assigned):
        """ValueError if camper in wideform is missing from camper_order."""
        incomplete_order = ["Alice", "Bob"]
        with pytest.raises(ValueError, match="camper_order"):
            wrangle_assignments_to_wideform(longform_assigned, camper_order=incomplete_order)

    def test_camper_order_none_preserves_cabin_sort(self, longform_assigned):
        """camper_order=None preserves current cabin → camper sort."""
        result = wrangle_assignments_to_wideform(longform_assigned, camper_order=None)
        assert result["camper"].tolist() == ["Alice", "Bob", "Carol", "Dave"]


class TestSeatradeLeaders:
    def test_columns_are_block_seatrade_camper_cabin(self, seatrade_sort_df):
        """Seatrade Leaders should have columns: block, seatrade, camper, cabin."""
        result = prepare_seatrade_leaders(seatrade_sort_df)
        assert result.columns.tolist() == ["block", "seatrade", "camper", "cabin"]

    def test_no_preference_or_assignment_columns(self, seatrade_sort_df):
        """Seatrade Leaders should not include preference or assignment columns."""
        result = prepare_seatrade_leaders(seatrade_sort_df)
        assert "preference" not in result.columns
        assert "assignment" not in result.columns

    def test_filters_unassigned_rows(self, sample_mixed_assignment_df):
        """Should filter out rows where assignment == 0."""
        result = prepare_seatrade_leaders(sample_mixed_assignment_df)
        assert result["camper"].tolist() == ["Alice", "Carol"]

    def test_sorts_by_block_seatrade_cabin_camper(self, seatrade_sort_df):
        """Seatrade Leaders sorted by block → seatrade → cabin → camper."""
        result = prepare_seatrade_leaders(seatrade_sort_df)
        assert result["block"].tolist() == ["1a", "1a", "1a", "2a"]
        assert result["seatrade"].tolist() == ["Archery", "Archery", "Climbing", "Archery"]
        assert result["cabin"].tolist() == ["Cabin1", "Cabin2", "Cabin1", "Cabin2"]
        assert result["camper"].tolist() == ["Alice", "Carol", "Bob", "Zed"]
