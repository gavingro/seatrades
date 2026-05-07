"""Tests for the assignments_tab module."""
import pytest
from seatrades_app.tabs.assignments_tab import prepare_seatrade_leaders


class TestRemovedViews:
    def test_prepare_assignment_view_removed(self):
        """prepare_assignment_view should no longer be importable."""
        with pytest.raises(ImportError):
            from seatrades_app.tabs.assignments_tab import prepare_assignment_view  # noqa: F401

    def test_get_view_selection_removed(self):
        """get_view_selection should no longer be importable."""
        with pytest.raises(ImportError):
            from seatrades_app.tabs.assignments_tab import get_view_selection  # noqa: F401

    def test_render_view_removed(self):
        """render_view should no longer be importable."""
        with pytest.raises(ImportError):
            from seatrades_app.tabs.assignments_tab import render_view  # noqa: F401


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
        # Only Alice and Carol (assigned campers)
        assert result["camper"].tolist() == ["Alice", "Carol"]

    def test_sorts_by_block_seatrade_cabin_camper(self, seatrade_sort_df):
        """Seatrade Leaders sorted by block → seatrade → cabin → camper."""
        result = prepare_seatrade_leaders(seatrade_sort_df)
        # Block 1a before 2a
        assert result["block"].tolist() == ["1a", "1a", "1a", "2a"]
        # Within 1a: Archery before Climbing (alphabetically)
        assert result["seatrade"].tolist() == ["Archery", "Archery", "Climbing", "Archery"]
        # Within 1a+Archery: Cabin1 before Cabin2
        assert result["cabin"].tolist() == ["Cabin1", "Cabin2", "Cabin1", "Cabin2"]
        # Within each group, campers sorted alphabetically
        assert result["camper"].tolist() == ["Alice", "Carol", "Bob", "Zed"]