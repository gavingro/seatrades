"""Tests for the SolveRun service-layer seam."""

from seatrades.solve_run import detect_timeout, percent_from_elapsed


class TestPercentFromElapsed:
    def test_returns_fraction_of_time_limit(self):
        """Halfway through the time limit reports 0.5."""
        assert percent_from_elapsed(30.0, 60.0) == 0.5

    def test_caps_at_one_past_the_limit(self):
        """Elapsed beyond the time limit never exceeds 1.0."""
        assert percent_from_elapsed(90.0, 60.0) == 1.0


class TestDetectTimeout:
    def test_true_when_log_has_time_limit_line(self):
        """CBC's time-limit line marks the solve as timed out."""
        log_text = "Cbc0010I After 0 nodes\nResult - Stopped on time limit\nTotal time 60.0"
        assert detect_timeout(log_text) is True

    def test_false_when_log_lacks_time_limit_line(self):
        """A normal optimal log is not a timeout."""
        log_text = "Result - Optimal solution found\nObjective value 42.0"
        assert detect_timeout(log_text) is False
