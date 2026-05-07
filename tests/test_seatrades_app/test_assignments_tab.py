"""Tests for the assignments_tab module."""
import pytest
from seatrades_app.tabs.assignments_tab import prepare_assignment_view


class TestAssignmentView:
    def test_filters_unassigned_rows(self, sample_mixed_assignment_df):
        result = prepare_assignment_view(sample_mixed_assignment_df, view="camper")

        assert len(result) == 2
        assert result["camper"].tolist() == ["Alice", "Carol"]
        assert "assignment" not in result.columns

    def test_get_view_name_default(self):
        """Default view selection should be Captain's Book."""
        from seatrades_app.tabs.assignments_tab import get_view_selection

        view = get_view_selection()

        assert view == "camper"

    def test_get_view_name_captains_book(self):
        from seatrades_app.tabs.assignments_tab import get_view_selection

        view = get_view_selection("Captain's Book")

        assert view == "camper"

    def test_get_view_name_cabin_leaders(self):
        from seatrades_app.tabs.assignments_tab import get_view_selection

        view = get_view_selection("Cabin Leaders")

        assert view == "cabin"

    def test_get_view_name_seatrade_leaders(self):
        from seatrades_app.tabs.assignments_tab import get_view_selection

        view = get_view_selection("Seatrade Leaders")

        assert view == "seatrade"

    def test_get_view_name_invalid_falls_back_to_camper(self):
        from seatrades_app.tabs.assignments_tab import get_view_selection

        view = get_view_selection("Invalid Option")

        assert view == "camper"

    def test_render_view_captains_book(self, sample_assigned_df):
        from seatrades_app.tabs.assignments_tab import render_view

        result = render_view(sample_assigned_df, "Captain's Book")

        assert result["camper"].tolist() == ["Alice", "Bob", "Carol", "Dave", "Zed"]
        assert result.columns.tolist() == ["camper", "cabin", "block", "seatrade", "preference"]

    def test_render_view_cabin_leaders(self, sample_assigned_df):
        from seatrades_app.tabs.assignments_tab import render_view

        result = render_view(sample_assigned_df, "Cabin Leaders")

        assert result["cabin"].tolist() == ["Cabin1", "Cabin1", "Cabin2", "Cabin2", "Cabin2"]
        assert result["camper"].tolist() == ["Bob", "Alice", "Carol", "Dave", "Zed"]

    def test_render_view_seatrade_leaders(self, sample_assigned_df):
        from seatrades_app.tabs.assignments_tab import render_view

        result = render_view(sample_assigned_df, "Seatrade Leaders")

        assert result["block"].tolist() == ["1a", "1a", "1a", "1a", "2a"]
        assert result["seatrade"].tolist() == ["Archery", "Archery", "Climbing", "Sailing", "Kayaking"]

    def test_captains_book_view_sorts_by_camper(self, sample_assigned_df):
        """Captain's Book view should sort by camper with correct column order."""
        result = prepare_assignment_view(sample_assigned_df, view="camper")

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
        result = prepare_assignment_view(sample_assigned_df, view="cabin")

        assert result["cabin"].tolist() == ["Cabin1", "Cabin1", "Cabin2", "Cabin2", "Cabin2"]
        assert result["block"].tolist() == ["1a", "2a", "1a", "1a", "1a"]
        assert result["camper"].tolist() == ["Bob", "Alice", "Carol", "Dave", "Zed"]

    def test_seatrade_leaders_view_sorts_by_block_seatrade_cabin_camper(
        self, seatrade_sort_df
    ):
        result = prepare_assignment_view(seatrade_sort_df, view="seatrade")

        assert result["block"].tolist() == ["1a", "1a", "1a", "2a"]
        assert result["seatrade"].tolist() == ["Archery", "Archery", "Climbing", "Archery"]
        assert result["cabin"].tolist() == ["Cabin1", "Cabin2", "Cabin1", "Cabin2"]
        assert result["camper"].tolist() == ["Alice", "Carol", "Bob", "Zed"]
