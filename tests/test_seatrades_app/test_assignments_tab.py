"""Tests for the assignments_tab module.

TODO: Remove TestRemovedViews after next release — these ImportError guards are
transitional and will become dead weight once the old function names are fully gone.
"""

import pytest

from seatrades_app.tabs.assignments_tab import render_view


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
        """Selecting By Camper should return wide-form dataframe."""
        result = render_view(seatrade_sort_df, "By Camper")
        assert result.columns.tolist() == [
            "cabin",
            "camper",
            "Seatrade 1a",
            "Seatrade 1b",
            "Seatrade 2a",
            "Seatrade 2b",
        ]

    def test_captains_book_sorts_by_camper_order(self, seatrade_sort_df):
        """By Camper with camper_order should sort rows by that order."""
        camper_order = ["Carol", "Zed", "Bob", "Alice"]
        result = render_view(seatrade_sort_df, "By Camper", camper_order=camper_order)
        assert result["camper"].tolist() == ["Carol", "Zed", "Bob", "Alice"]

    def test_captains_book_without_camper_order_uses_cabin_sort(self, seatrade_sort_df):
        """By Camper without camper_order should sort by cabin → camper."""
        result = render_view(seatrade_sort_df, "By Camper")
        assert result["camper"].tolist() == ["Alice", "Bob", "Carol", "Zed"]

    def test_seatrade_leaders_returns_simplified_longform(self, seatrade_sort_df):
        """Selecting By Seatrade should return block, seatrade, camper, cabin."""
        result = render_view(seatrade_sort_df, "By Seatrade")
        assert result.columns.tolist() == ["block", "seatrade", "camper", "cabin"]

    def test_seatrade_leaders_ignores_camper_order(self, seatrade_sort_df):
        """By Seatrade view should ignore camper_order."""
        result_without = render_view(seatrade_sort_df, "By Seatrade")
        result_with = render_view(seatrade_sort_df, "By Seatrade", camper_order=["Zed", "Alice"])
        assert result_without.equals(result_with)
