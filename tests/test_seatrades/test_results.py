"""Tests for seatrades/results.py."""
import pytest
from unittest.mock import MagicMock

from seatrades.results import display_assignments


class TestDisplayAssignmentsFailureGuard:
    def test_raises_on_failed_status(self):
        """display_assignments must raise ValueError when optimization failed."""
        seatrades = MagicMock()
        seatrades.status = -1

        with pytest.raises(ValueError, match="not successfully solved"):
            display_assignments(seatrades)

    def test_raises_on_unsolved_status(self):
        """display_assignments must raise ValueError when status is 0 (not yet solved)."""
        seatrades = MagicMock()
        seatrades.status = 0

        with pytest.raises(ValueError):
            display_assignments(seatrades)