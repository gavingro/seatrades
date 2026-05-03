"""Tests for the assignments_tab module."""
import pandas as pd
from seatrades_app.tabs.assignments_tab import prepare_assignment_view


class TestAssignmentView:
    def test_filters_unassigned_rows(self):
        """Should filter out rows where assignment == 0."""
        # Arrange: Mix of assigned and unassigned rows
        data = {
            "camper": ["Alice", "Bob", "Carol"],
            "cabin": ["Cabin1", "Cabin1", "Cabin2"],
            "block": ["1a", "1a", "1a"],
            "seatrade": ["Archery", "Kayaking", "Archery"],
            "assignment": [1.0, 0.0, 1.0],  # Bob is unassigned
            "preference": [1, 0, 1],
        }
        df = pd.DataFrame(data)

        # Act
        result = prepare_assignment_view(df, view="camper")

        # Assert: Only Alice and Carol (assigned campers)
        assert len(result) == 2
        assert result["camper"].tolist() == ["Alice", "Carol"]
        assert "assignment" not in result.columns

    def test_captains_book_view_sorts_by_camper(self):
        """Captain's Book view should sort by camper with correct column order."""
        # Arrange
        data = {
            "camper": ["Zed", "Alice", "Bob"],
            "cabin": ["Cabin1", "Cabin2", "Cabin1"],
            "block": ["1a", "1a", "1a"],
            "seatrade": ["Archery", "Kayaking", "Archery"],
            "assignment": [1.0, 1.0, 1.0],
            "preference": [1, 2, 1],
        }
        df = pd.DataFrame(data)

        # Act
        result = prepare_assignment_view(df, view="camper")

        # Assert: Sorted by camper, correct columns (no 'assignment')
        assert result.columns.tolist() == [
            "camper",
            "cabin",
            "block",
            "seatrade",
            "preference",
        ]
        assert result["camper"].tolist() == ["Alice", "Bob", "Zed"]

    def test_sort_by_cabin(self):
        """Cabin Leaders view should sort by cabin → block → camper."""
        # Arrange
        data = {
            "camper": ["Zed", "Alice", "Bob", "Carol", "Dave"],
            "cabin": ["Cabin2", "Cabin1", "Cabin1", "Cabin2", "Cabin2"],
            "block": ["1a", "2a", "1a", "1a", "1a"],
            "seatrade": ["Archery", "Kayaking", "Archery", "Climbing", "Sailing"],
            "assignment": [1.0, 1.0, 1.0, 1.0, 1.0],
            "preference": [1, 2, 1, 1, 1],
        }
        df = pd.DataFrame(data)

        # Act
        result = prepare_assignment_view(df, view="cabin")

        # Assert: Sorted by cabin → block → camper
        assert result["cabin"].tolist() == ["Cabin1", "Cabin1", "Cabin2", "Cabin2", "Cabin2"]
        assert result["block"].tolist() == ["1a", "2a", "1a", "1a", "1a"]
        assert result["camper"].tolist() == ["Bob", "Alice", "Carol", "Dave", "Zed"]

    def test_seatrade_leaders_view_sorts_by_block_seatrade_cabin_camper(self):
        """Seatrade Leaders view should sort by block → seatrade → cabin → camper."""
        # Arrange
        data = {
            "camper": ["Zed", "Alice", "Bob", "Carol"],
            "cabin": ["Cabin2", "Cabin1", "Cabin1", "Cabin2"],
            "block": ["2a", "1a", "1a", "1a"],
            "seatrade": ["Archery", "Archery", "Climbing", "Archery"],
            "assignment": [1.0, 1.0, 1.0, 1.0],
            "preference": [1, 2, 1, 1],
        }
        df = pd.DataFrame(data)

        # Act
        result = prepare_assignment_view(df, view="seatrade")

        # Assert: Sorted by block → seatrade → cabin → camper
        assert result["block"].tolist() == ["1a", "1a", "1a", "2a"]
        assert result["seatrade"].tolist() == ["Archery", "Archery", "Climbing", "Archery"]
        assert result["cabin"].tolist() == ["Cabin1", "Cabin2", "Cabin1", "Cabin2"]
        assert result["camper"].tolist() == ["Alice", "Carol", "Bob", "Zed"]
