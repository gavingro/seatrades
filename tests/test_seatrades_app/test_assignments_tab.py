"""Tests for the assignments_tab module.

TODO: Remove TestRemovedViews after next release — these ImportError guards are
transitional and will become dead weight once the old function names are fully gone.
"""
import pytest


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