"""Tests for the assignments_tab module."""
import pandas as pd
from seatrades_app.tabs.assignments_tab import prepare_assignment_view

class TestAssignmentView:
    def test_captains_book_view_sorts_by_camper(self):
        """Captain's Book view should sort by camper (upload order) with correct column order."""
        # Arrange: Create sample longform dataframe
        data = {
            "camper": ["Zed", "Alice", "Bob"],
            "cabin": ["Cabin1", "Cabin2", "Cabin1"],
            "block": ["1a", "1a", "1a"],
            "seatrade": ["Archery", "Kayaking", "Archery"],
            "assignment": [1.0, 1.0, 1.0],
            "preference": [1, 2, 1],
        }
        df = pd.DataFrame(data)

        # Act: Prepare Captain's Book view
        result = prepare_assignment_view(df, view="camper")

        # Assert: Sorted by camper, columns in correct order
        assert result.columns.tolist() == [
            "camper",
            "cabin",
            "block",
            "seatrade",
            "assignment",
            "preference",
        ]
        assert result["camper"].tolist() == ["Alice", "Bob", "Zed"]  # Alphabetically sorted


    def test_sort_by_cabin(self):
        """Cabin Leaders view should sort by cabin → block → camper."""
        # Arrange: Create sample longform dataframe with unsorted data
        data = {
            "camper": ["Zed", "Alice", "Bob", "Carol", "Dave"],
            "cabin": ["Cabin2", "Cabin1", "Cabin1", "Cabin2", "Cabin2"],
            "block": ["1a", "2a", "1a", "1a", "1a"],
            "seatrade": ["Archery", "Kayaking", "Archery", "Climbing", "Sailing"],
            "assignment": [1.0, 1.0, 1.0, 1.0, 1.0],
            "preference": [1, 2, 1, 1, 1],
        }
        df = pd.DataFrame(data)

        # Act: Prepare Cabin Leaders view
        result = prepare_assignment_view(df, view="cabin")

        # Assert: Sorted by cabin → block → camper
        assert result["cabin"].tolist() == ["Cabin1", "Cabin1", "Cabin2", "Cabin2", "Cabin2"]
        # Within Cabin1: block 1a before 2a
        assert result["block"].tolist() == ["1a", "2a", "1a", "1a", "1a"]
        # Within each cabin+block group, campers sorted alphabetically
        # Cabin1+1a: Bob, Cabin1+2a: Alice, Cabin2+1a: Carol, Dave, Zed
        assert result["camper"].tolist() == ["Bob", "Alice", "Carol", "Dave", "Zed"]


    def test_seatrade_leaders_view_sorts_by_block_seatrade_cabin_camper(self):
        """Seatrade Leaders view should sort by block → seatrade → cabin → camper."""
        # Arrange: Create sample longform dataframe
        data = {
            "camper": ["Zed", "Alice", "Bob", "Carol"],
            "cabin": ["Cabin2", "Cabin1", "Cabin1", "Cabin2"],
            "block": ["2a", "1a", "1a", "1a"],
            "seatrade": ["Archery", "Archery", "Climbing", "Archery"],
            "assignment": [1.0, 1.0, 1.0, 1.0],
            "preference": [1, 2, 1, 1],
        }
        df = pd.DataFrame(data)

        # Act: Prepare Seatrade Leaders view
        result = prepare_assignment_view(df, view="seatrade")

        # Assert: Sorted by block → seatrade → cabin → camper
        # Block 1a before 2a
        assert result["block"].tolist() == ["1a", "1a", "1a", "2a"]
        # Within 1a: Archery before Climbing (alphabetically)
        assert result["seatrade"].tolist() == ["Archery", "Archery", "Climbing", "Archery"]
        # Within 1a+Archery: Cabin1 before Cabin2
        assert result["cabin"].tolist() == ["Cabin1", "Cabin2", "Cabin1", "Cabin2"]
        # Within each group, campers sorted alphabetically
        assert result["camper"].tolist() == ["Alice", "Carol", "Bob", "Zed"]
