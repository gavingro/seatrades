"""Tests for the assignments_tab module."""
import pytest
from seatrades_app.tabs.assignments_tab import prepare_assignment_view


class TestAssignmentView:
    def test_filters_unassigned_rows(self, sample_mixed_assignment_df):
        """Should filter out rows where assignment == 0."""
        # Act
        result = prepare_assignment_view(sample_mixed_assignment_df, view="camper")

        # Assert: Only Alice and Carol (assigned campers)
        assert len(result) == 2
        assert result["camper"].tolist() == ["Alice", "Carol"]
        assert "assignment" not in result.columns

    def test_captains_book_view_sorts_by_camper(self, sample_assigned_df):
        """Captain's Book view should sort by camper with correct column order."""
        # Act
        result = prepare_assignment_view(sample_assigned_df, view="camper")

        # Assert: Sorted by camper, correct columns (no 'assignment')
        assert result.columns.tolist() == [
            "camper",
            "cabin",
            "block",
            "seatrade",
            "preference",
        ]
        assert result["camper"].tolist() == ["Alice", "Bob", "Carol", "Dave", "Zed"]

    def test_sort_by_cabin(self, sample_assigned_df):
        """Cabin Leaders view should sort by cabin → block → camper."""
        # Act
        result = prepare_assignment_view(sample_assigned_df, view="cabin")

        # Assert: Sorted by cabin → block → camper
        assert result["cabin"].tolist() == ["Cabin1", "Cabin1", "Cabin2", "Cabin2", "Cabin2"]
        assert result["block"].tolist() == ["1a", "2a", "1a", "1a", "1a"]
        assert result["camper"].tolist() == ["Bob", "Alice", "Carol", "Dave", "Zed"]

    def test_seatrade_leaders_view_sorts_by_block_seatrade_cabin_camper(
        self, seatrade_sort_df
    ):
        """Seatrade Leaders view should sort by block → seatrade → cabin → camper."""
        # Act
        result = prepare_assignment_view(seatrade_sort_df, view="seatrade")

        # Assert: Sorted by block → seatrade → cabin → camper
        # Block 1a before 2a
        assert result["block"].tolist() == ["1a", "1a", "1a", "2a"]
        # Within 1a: Archery before Climbing (alphabetically)
        assert result["seatrade"].tolist() == ["Archery", "Archery", "Climbing", "Archery"]
        # Within 1a+Archery: Cabin1 before Cabin2
        assert result["cabin"].tolist() == ["Cabin1", "Cabin2", "Cabin1", "Cabin2"]
        # Within each group, campers sorted alphabetically
        assert result["camper"].tolist() == ["Alice", "Carol", "Bob", "Zed"]
