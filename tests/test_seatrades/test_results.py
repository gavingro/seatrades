"""Tests for seatrades/results.py."""
from unittest.mock import MagicMock

import pytest

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

        with pytest.raises(ValueError, match="not found\\. Did"):
            display_assignments(seatrades)

    def test_returns_chart_on_success(self):
        """display_assignments returns a chart when optimization succeeded."""
        seatrades = MagicMock()
        seatrades.status = 1
        seatrades.assignments = MagicMock()
        seatrades.wrangle_assignments_to_longform.return_value = MagicMock()

        result = display_assignments(seatrades)

        assert result is not None