"""Tests for seatrades/visualization.py."""

import dataclasses
import json

import pytest

from seatrades.results import SolverState, SolverStatus
from seatrades.visualization import (
    SATISFACTION_RANGE,
    display_assignments,
    display_optimality_donut,
)


class TestDisplayAssignmentsFailureGuard:
    def test_raises_on_infeasible_status(self, sample_assignment_solution):
        """display_assignments must raise ValueError when optimization was infeasible."""

        infeasible = dataclasses.replace(
            sample_assignment_solution,
            status=SolverStatus(state=SolverState.INFEASIBLE),
        )
        with pytest.raises(ValueError, match="not successfully solved"):
            display_assignments(infeasible)

    def test_raises_on_error_status(self, sample_assignment_solution):
        """display_assignments must raise ValueError when status is ERROR (unsolved)."""

        error_solution = dataclasses.replace(
            sample_assignment_solution,
            status=SolverStatus(state=SolverState.ERROR, message="Not solved"),
        )
        with pytest.raises(ValueError, match="No solution found"):
            display_assignments(error_solution)

    def test_returns_chart_on_optimal(self, sample_assignment_solution):
        """display_assignments returns a chart when optimization succeeded."""
        result = display_assignments(sample_assignment_solution)
        assert result is not None


class TestDisplayAssignmentsLegibility:
    """The optimal-path chart must read clearly for a non-technical Scheduling Captain."""

    def test_chart_has_meaningful_title(self, sample_assignment_solution):
        """Title names what the Captain is looking at — not the bare word 'Seatrades.'."""
        spec = display_assignments(sample_assignment_solution).to_dict()
        assert spec["title"]["text"] == "Camper Seatrade Assignments"

    def test_subtitle_is_white(self, sample_assignment_solution):
        """Subtitle is white so it reads on the dark app theme."""
        spec = display_assignments(sample_assignment_solution).to_dict()
        assert spec["title"]["subtitleColor"] == "white"

    def test_color_encodes_camper_satisfaction(self, sample_assignment_solution):
        """Cells are colored by a satisfaction field (top choice → low/unranked), not raw preference."""
        spec = display_assignments(sample_assignment_solution).to_dict()
        color_fields = [layer.get("encoding", {}).get("color", {}).get("field") for layer in spec["spec"]["layer"]]
        assert "satisfaction" in color_fields

    def test_unassigned_cells_have_background_fill(self, sample_assignment_solution):
        """Every cell gets a neutral fill so the grid stays readable on a dark app theme.

        Regression: drawing only assigned cells left unassigned cells transparent, so the
        whole grid vanished against the dark background.
        """
        spec = display_assignments(sample_assignment_solution).to_dict()
        rect_layers = [layer for layer in spec["spec"]["layer"] if layer.get("mark", {}).get("type") == "rect"]
        # A background layer fills every cell with a fixed colour and has no data-driven
        # colour encoding — distinct from the satisfaction-coloured layer.
        has_background = any(
            layer["mark"].get("color") and "color" not in layer.get("encoding", {}) for layer in rect_layers
        )
        assert has_background

    def test_rank_text_layer_present(self, sample_assignment_solution):
        """A text layer prints the exact choice rank on each assigned cell."""
        spec = display_assignments(sample_assignment_solution).to_dict()
        marks = [layer.get("mark", {}).get("type") for layer in spec["spec"]["layer"]]
        assert "text" in marks

    def test_block_columns_use_compact_labels(self, sample_assignment_solution):
        """Block facet columns show compact labels (e.g. '1st·AM'), not raw codes alone."""
        spec = display_assignments(sample_assignment_solution).to_dict()
        assert "1st·AM" in json.dumps(spec, ensure_ascii=False)


class TestOptimalityDonut:
    """The Solver Optimality headline: a donut showing the solver's proof-of-optimum N/100."""

    def test_returns_chart(self):
        """A normal optimality fraction produces a chart."""
        assert display_optimality_donut(0.98) is not None

    def test_is_a_donut_arc(self):
        """The gauge is drawn as an arc/donut, not bars or a line."""
        spec = display_optimality_donut(0.98).to_dict()
        mark_types = [layer.get("mark", {}).get("type") for layer in spec["layer"]]
        assert "arc" in mark_types

    def test_shows_percent_in_center(self):
        """The rounded percent (e.g. '98%') is printed as the headline number."""
        spec = display_optimality_donut(0.98).to_dict()
        assert "98%" in json.dumps(spec)

    def test_rounds_percent_to_whole_number(self):
        """A fractional percent is rounded for a clean headline (0.975 → '98%', never '97.5%')."""
        spec = display_optimality_donut(0.975).to_dict()
        assert "98%" in json.dumps(spec)
        assert "97.5" not in json.dumps(spec)

    def test_arc_size_is_data_driven(self):
        """The filled arc encodes the optimality value, so 0.5 and 0.98 render different sweeps."""
        spec = display_optimality_donut(0.98).to_dict()
        arc_layer = next(layer for layer in spec["layer"] if layer.get("mark", {}).get("type") == "arc")
        assert arc_layer["encoding"]["theta"]["field"] == "value"

    def test_fill_is_the_top_pick_green(self):
        """The filled arc reuses the top-pick satisfaction green — visually 'as good as proven'."""
        spec = display_optimality_donut(0.98).to_dict()
        arc_layer = next(layer for layer in spec["layer"] if layer.get("mark", {}).get("type") == "arc")
        fill_color = arc_layer["encoding"]["color"]["scale"]["range"][0]
        assert fill_color == SATISFACTION_RANGE[0]
