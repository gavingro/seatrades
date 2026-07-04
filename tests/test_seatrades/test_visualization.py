"""Tests for seatrades/visualization.py."""

import dataclasses
import json

import pytest

from seatrades.results import SolverState, SolverStatus
from seatrades.scoring import score
from seatrades.visualization import (
    METRIC_ORDER,
    SATISFACTION_RANGE,
    display_age_spread_detail,
    display_assignments,
    display_cohesion_detail,
    display_metric_detail,
    display_optimality_donut,
    display_preference_detail,
    display_quality_summary,
    display_sparsity_detail,
    normalize_to_band,
)


def _flatten(spec):
    """All layer encoding dicts (chart may or may not be layered)."""
    if "layer" in spec:
        return [layer.get("encoding", {}) for layer in spec["layer"]]
    return [spec.get("encoding", {})]


def _summary_metric_names(spec):
    """The metric names carried in a chart spec's inline data (Altair inlines small frames)."""
    data = spec.get("data", {})
    rows: list[dict] = data.get("values") or next(iter(spec.get("datasets", {}).values()), [])
    return {row["name"] for row in rows if "name" in row}


class TestDisplayQualitySummary:
    """The six-metric overview: normalized 0–100 on an ordinal x, raw value in the tooltip."""

    def test_x_uses_the_canonical_metric_order(self, sample_assignment_solution):
        spec = display_quality_summary(score(sample_assignment_solution)).to_dict()
        x_sorts = [enc["x"].get("sort") for enc in _flatten(spec) if "x" in enc]
        assert METRIC_ORDER in x_sorts

    def test_y_encodes_the_normalized_position(self, sample_assignment_solution):
        spec = display_quality_summary(score(sample_assignment_solution)).to_dict()
        y_fields = [enc["y"].get("field") for enc in _flatten(spec) if "y" in enc]
        assert "normalized" in y_fields

    def test_tooltip_carries_the_raw_value_not_the_position(self, sample_assignment_solution):
        spec = display_quality_summary(score(sample_assignment_solution)).to_dict()
        tooltip_fields = []
        for enc in _flatten(spec):
            for entry in enc.get("tooltip", []):
                tooltip_fields.append(entry.get("field"))
        assert "raw_value" in tooltip_fields

    def test_rendered_as_area_for_v1(self, sample_assignment_solution):
        spec = display_quality_summary(score(sample_assignment_solution)).to_dict()
        marks = [spec["mark"]] if "mark" in spec else [layer.get("mark") for layer in spec.get("layer", [])]
        mark_types = [mark.get("type") if isinstance(mark, dict) else mark for mark in marks]
        assert "area" in mark_types

    def test_every_built_metric_is_a_known_order_name(self, sample_assignment_solution):
        """Every metric score() builds must be a METRIC_ORDER name, so the summary plot
        places it deliberately. Guards the name↔order drift the KeyError dispatch can't:
        an unlisted name doesn't error, it just sorts silently to the end of the axis.
        """
        names = [metric.name for metric in score(sample_assignment_solution).metrics]
        assert set(names) <= set(METRIC_ORDER)

    def test_cohesion_is_plotted_on_the_summary(self, sample_assignment_solution):
        """Cohesion shows on the Overview summary plot (issue #93 acceptance criterion)."""
        spec = display_quality_summary(score(sample_assignment_solution)).to_dict()
        assert "Cohesion" in _summary_metric_names(spec)

    def test_sparsity_is_plotted_on_the_summary(self, sample_assignment_solution):
        """Sparsity shows on the Overview summary plot (issue #94 acceptance criterion)."""
        spec = display_quality_summary(score(sample_assignment_solution)).to_dict()
        assert "Sparsity" in _summary_metric_names(spec)

    def test_age_spread_is_plotted_on_the_summary(self, sample_assignment_solution):
        """Age spread shows on the Overview summary plot (issue #95 acceptance criterion)."""
        spec = display_quality_summary(score(sample_assignment_solution)).to_dict()
        assert "Age spread" in _summary_metric_names(spec)


def _preference_metric(solution):
    return score(solution).metric("Preference")


def _cohesion_metric(solution):
    return score(solution).metric("Cohesion")


def _sparsity_metric(solution):
    return score(solution).metric("Sparsity")


def _age_spread_metric(solution):
    return score(solution).metric("Age spread")


class TestDisplayPreferenceDetail:
    """The Preference drill-down: camper counts per CPR, with the CPR-5 split visible."""

    def test_x_encodes_cpr(self, sample_assignment_solution):
        spec = display_preference_detail(_preference_metric(sample_assignment_solution)).to_dict()
        assert spec["encoding"]["x"]["field"] == "cpr"

    def test_x_shows_all_cpr_buckets(self, sample_assignment_solution):
        """All four CPR buckets (3–6) stay on the axis even when one has zero campers."""
        spec = display_preference_detail(_preference_metric(sample_assignment_solution)).to_dict()
        assert spec["encoding"]["x"]["scale"]["domain"] == [3, 4, 5, 6]

    def test_y_is_a_camper_count(self, sample_assignment_solution):
        spec = display_preference_detail(_preference_metric(sample_assignment_solution)).to_dict()
        assert spec["encoding"]["y"]["aggregate"] == "count"

    def test_cpr_five_is_split_by_cause(self, sample_assignment_solution):
        """Colour encodes the cause so the CPR-5 bar splits into 1+4 vs 2+3."""
        spec = display_preference_detail(_preference_metric(sample_assignment_solution)).to_dict()
        assert spec["encoding"]["color"]["field"] == "cause"


class TestDisplayCohesionDetail:
    """The Cohesion drill-down: camper counts per same-cabin cohort size (1 = solo)."""

    def test_x_encodes_cohort_size(self, sample_assignment_solution):
        spec = display_cohesion_detail(_cohesion_metric(sample_assignment_solution)).to_dict()
        assert spec["encoding"]["x"]["field"] == "cohort_size"

    def test_y_is_a_camper_count(self, sample_assignment_solution):
        spec = display_cohesion_detail(_cohesion_metric(sample_assignment_solution)).to_dict()
        assert spec["encoding"]["y"]["aggregate"] == "count"


class TestDisplaySparsityDetail:
    """The Sparsity drill-down: running-seatrade count per block."""

    def test_x_encodes_block(self, sample_assignment_solution):
        spec = display_sparsity_detail(_sparsity_metric(sample_assignment_solution)).to_dict()
        assert spec["encoding"]["x"]["field"] == "block"

    def test_y_is_a_running_seatrade_count(self, sample_assignment_solution):
        spec = display_sparsity_detail(_sparsity_metric(sample_assignment_solution)).to_dict()
        assert spec["encoding"]["y"]["aggregate"] == "count"


class TestDisplayAgeSpreadDetail:
    """The Age Spread drill-down: seatrade counts per age range."""

    def test_x_encodes_spread(self, sample_assignment_solution):
        spec = display_age_spread_detail(_age_spread_metric(sample_assignment_solution)).to_dict()
        assert spec["encoding"]["x"]["field"] == "spread"

    def test_y_is_a_seatrade_count(self, sample_assignment_solution):
        spec = display_age_spread_detail(_age_spread_metric(sample_assignment_solution)).to_dict()
        assert spec["encoding"]["y"]["aggregate"] == "count"

    def test_tooltip_identifies_the_seatrade_and_block(self, sample_assignment_solution):
        """Hovering a bar surfaces which seatrade x block has a large range."""
        spec = display_age_spread_detail(_age_spread_metric(sample_assignment_solution)).to_dict()
        tooltip_fields = [entry.get("field") for entry in spec["encoding"]["tooltip"]]
        assert "seatrade" in tooltip_fields
        assert "block" in tooltip_fields


class TestDisplayMetricDetail:
    """The name→builder dispatcher: one coherent 'add a metric' seam."""

    def test_routes_preference_to_its_builder(self, sample_assignment_solution):
        metric = _preference_metric(sample_assignment_solution)
        assert display_metric_detail(metric).to_dict() == display_preference_detail(metric).to_dict()

    def test_routes_cohesion_to_its_builder(self, sample_assignment_solution):
        metric = _cohesion_metric(sample_assignment_solution)
        assert display_metric_detail(metric).to_dict() == display_cohesion_detail(metric).to_dict()

    def test_routes_sparsity_to_its_builder(self, sample_assignment_solution):
        metric = _sparsity_metric(sample_assignment_solution)
        assert display_metric_detail(metric).to_dict() == display_sparsity_detail(metric).to_dict()

    def test_routes_age_spread_to_its_builder(self, sample_assignment_solution):
        metric = _age_spread_metric(sample_assignment_solution)
        assert display_metric_detail(metric).to_dict() == display_age_spread_detail(metric).to_dict()

    def test_raises_for_a_metric_with_no_detail_chart(self, sample_assignment_solution):
        unwired = dataclasses.replace(_preference_metric(sample_assignment_solution), name="Fair within")
        with pytest.raises(KeyError):
            display_metric_detail(unwired)


class TestNormalizeToBand:
    """The pure render-time band: raw metric value → 0–100, uniformly up-is-good."""

    def test_in_band_value_maps_within_the_band(self):
        """A single in-band observation normalizes linearly inside [low_anchor, high_anchor]."""
        # midpoint of [0.6, 0.95]
        result = normalize_to_band(
            0.775, low_anchor=0.6, high_anchor=0.95, higher_is_better=True, observed_min=0.775, observed_max=0.775
        )
        assert result == pytest.approx(50.0)

    def test_out_of_band_observation_expands_domain_to_itself(self):
        """An observation above high_anchor becomes the new top endpoint (maps to 100)."""
        result = normalize_to_band(
            1.2, low_anchor=0.6, high_anchor=0.95, higher_is_better=True, observed_min=1.2, observed_max=1.2
        )
        assert result == 100.0

    def test_band_never_contracts_below_the_anchors(self):
        """A narrow observed range inside the band still normalizes against the full band, not itself."""
        # observed range [0.7, 0.8] is narrower than [0.6, 0.95]; domain must stay the band.
        result = normalize_to_band(
            0.7, low_anchor=0.6, high_anchor=0.95, higher_is_better=True, observed_min=0.7, observed_max=0.8
        )
        assert result == pytest.approx(28.5714, abs=1e-3)  # (0.7-0.6)/0.35*100

    def test_down_is_bad_metric_is_flipped(self):
        """higher_is_better=False inverts the axis so a lower raw value scores higher."""
        low_value = normalize_to_band(
            2.0, low_anchor=1.0, high_anchor=5.0, higher_is_better=False, observed_min=2.0, observed_max=2.0
        )
        assert low_value == 75.0  # linear 25, flipped
        up_is_good = normalize_to_band(
            2.0, low_anchor=1.0, high_anchor=5.0, higher_is_better=True, observed_min=2.0, observed_max=2.0
        )
        assert up_is_good == 25.0


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
