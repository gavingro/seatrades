"""Tests for the assignments_tab module.

TODO: Remove TestRemovedViews after next release — these ImportError guards are
transitional and will become dead weight once the old function names are fully gone.
"""
import pytest

from seatrades_app.tabs.assignments_tab import render_view
from seatrades.seatrades import wrangle_assignments_to_wideform, prepare_seatrade_leaders


class TestRemovedViews:
    def test_prepare_assignment_view_removed(self):
        """prepare_assignment_view should no longer be importable."""
        with pytest.raises(ImportError):
            from seatrades_app.tabs.assignments_tab import prepare_assignment_view  # noqa: F401

    def test_get_view_selection_removed(self):
        """get_view_selection should no longer be importable."""
        with pytest.raises(ImportError):
            from seatrades_app.tabs.assignments_tab import get_view_selection  # noqa: F401


class TestRenderView:
    def test_captains_book_returns_wideform(self, seatrade_sort_df):
        """Selecting Captain's Book should return wide-form dataframe."""
        result = render_view(seatrade_sort_df, "Captain's Book")
        assert result.columns.tolist() == [
            "cabin", "camper",
            "Seatrade 1a", "Seatrade 1b",
            "Seatrade 2a", "Seatrade 2b",
        ]

    def test_seatrade_leaders_returns_simplified_longform(self, seatrade_sort_df):
        """Selecting Seatrade Leaders should return block, seatrade, camper, cabin."""
        result = render_view(seatrade_sort_df, "Seatrade Leaders")
        assert result.columns.tolist() == ["block", "seatrade", "camper", "cabin"]