"""Tests for seatrades/visualization.py."""

import dataclasses
import json

import pandas as pd
import pytest

from seatrades.results import SolverState, SolverStatus
from seatrades.scoring import score
from seatrades.visualization import (
    _DETAIL_BUILDERS,
    FLEET_STATE_RANGE,
    SATISFACTION_RANGE,
    STAFFING_STATE_RANGE,
    display_age_spread_detail,
    display_assignments,
    display_cohesion_detail,
    display_fairness_between_detail,
    display_fairness_within_detail,
    display_fleet_assignments,
    display_metric_detail,
    display_optimality_donut,
    display_preference_detail,
    display_quality_summary,
    display_seatrade_staffing,
    display_sparsity_detail,
    metric_label,
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


def _rule_layer_average(spec):
    """The numeric value baked into a chart's reference-line (``mark_rule``) layer."""
    for layer in spec.get("layer", []):
        if layer.get("mark", {}).get("type") == "rule":
            data = layer.get("data", {})
            rows = data.get("values") or spec.get("datasets", {}).get(data.get("name"), [])
            return rows[0]["average"]
    raise AssertionError("No rule layer found in spec")


class TestDisplayQualitySummary:
    """The six-metric overview: normalized 0–100 on an ordinal x, measured value (plain units) in the tooltip."""

    def test_x_is_sorted_in_scorecard_order_with_display_labels(self, sample_assignment_solution):
        """The x-axis order is derived from scorecard.metrics (single source, no parallel
        constant) and shows the user-facing labels, not the internal metric names."""
        card = score(sample_assignment_solution)
        spec = display_quality_summary(card).to_dict()
        x_sorts = [enc["x"].get("sort") for enc in _flatten(spec) if "x" in enc]
        expected = [metric_label(metric.name) for metric in card.metrics]
        assert expected in x_sorts
        assert "Within-cabin fairness" in expected  # a de-jargoned label made it to the axis

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
        # The plain-units raw display is in the tooltip; the 0–100 position is not.
        assert "raw_display" in tooltip_fields
        assert "normalized" not in tooltip_fields

    def test_rendered_as_area_for_v1(self, sample_assignment_solution):
        spec = display_quality_summary(score(sample_assignment_solution)).to_dict()
        marks = [spec["mark"]] if "mark" in spec else [layer.get("mark") for layer in spec.get("layer", [])]
        mark_types = [mark.get("type") if isinstance(mark, dict) else mark for mark in marks]
        assert "area" in mark_types

    def test_every_built_metric_has_a_detail_builder(self, sample_assignment_solution):
        """Every metric score() builds must have a registered detail chart, so a metric can
        never reach the selectbox (options are derived from the scorecard) without a drill-down
        — the KeyError dispatch would otherwise only bite at render time (design review #4).
        """
        names = [metric.name for metric in score(sample_assignment_solution).metrics]
        assert set(names) <= set(_DETAIL_BUILDERS)

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

    def test_fair_within_is_plotted_on_the_summary(self, sample_assignment_solution):
        """Fair within shows on the Overview summary plot (issue #96 acceptance criterion)."""
        spec = display_quality_summary(score(sample_assignment_solution)).to_dict()
        assert "Fair within" in _summary_metric_names(spec)

    def test_fair_between_is_plotted_on_the_summary(self, sample_assignment_solution):
        """Fair between shows on the Overview summary plot (issue #96 acceptance criterion)."""
        spec = display_quality_summary(score(sample_assignment_solution)).to_dict()
        assert "Fair between" in _summary_metric_names(spec)

    def test_summary_axis_uses_de_jargoned_fairness_labels(self, sample_assignment_solution):
        """The plotted x labels de-jargon the two fairness metrics (owner comment #5)."""
        spec = display_quality_summary(score(sample_assignment_solution)).to_dict()
        data = spec.get("data", {})
        rows: list[dict] = data.get("values") or next(iter(spec.get("datasets", {}).values()), [])
        labels = {row["label"] for row in rows if "label" in row}
        assert {"Within-cabin fairness", "Between-cabin fairness"} <= labels
        assert "Fair within" not in labels and "Fair between" not in labels


def _preference_metric(solution):
    return score(solution).metric("Preference")


def _cohesion_metric(solution):
    return score(solution).metric("Cohesion")


def _sparsity_metric(solution):
    return score(solution).metric("Sparsity")


def _age_spread_metric(solution):
    return score(solution).metric("Age spread")


def _fair_within_metric(solution):
    return score(solution).metric("Fair within")


def _fair_between_metric(solution):
    return score(solution).metric("Fair between")


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
    """The Cohesion drill-down: camper-session counts per cabin-group size (1 = alone), by block."""

    def test_x_encodes_cohort_size(self, sample_assignment_solution):
        spec = display_cohesion_detail(_cohesion_metric(sample_assignment_solution)).to_dict()
        assert spec["encoding"]["x"]["field"] == "cohort_size"

    def test_y_is_a_camper_session_count(self, sample_assignment_solution):
        spec = display_cohesion_detail(_cohesion_metric(sample_assignment_solution)).to_dict()
        assert spec["encoding"]["y"]["aggregate"] == "count"

    def test_coloured_red_green_by_alone_not_by_block(self, sample_assignment_solution):
        """Colour reads the *quality* (alone = red, with a cabinmate = green), NOT the block — a
        block colour falsely reads as 'good' vs 'bad' blocks. Blocks still ride detail + tooltip."""
        spec = display_cohesion_detail(_cohesion_metric(sample_assignment_solution)).to_dict()
        assert spec["encoding"]["color"]["field"] == "togetherness"
        alone_index = spec["encoding"]["color"]["scale"]["domain"].index("Alone")
        assert spec["encoding"]["color"]["scale"]["range"][alone_index] == "#d73027"
        detail_fields = [entry.get("field") for entry in spec["encoding"]["detail"]]
        assert "block" in detail_fields
        tooltip_fields = [entry.get("field") for entry in spec["encoding"]["tooltip"]]
        assert "block" in tooltip_fields


class TestDisplaySparsityDetail:
    """The Sparsity drill-down: running-seatrade count per block."""

    def test_x_encodes_block(self, sample_assignment_solution):
        spec = display_sparsity_detail(_sparsity_metric(sample_assignment_solution)).to_dict()
        assert spec["encoding"]["x"]["field"] == "block"

    def test_y_is_a_running_seatrade_count(self, sample_assignment_solution):
        spec = display_sparsity_detail(_sparsity_metric(sample_assignment_solution)).to_dict()
        assert spec["encoding"]["y"]["aggregate"] == "count"


@pytest.fixture
def fleet_assignments_df():
    """A Cabin × Block presence grid as ``wrangle_fleet_assignments`` emits it."""
    return pd.DataFrame(
        {
            "cabin": ["Cabin1", "Cabin1", "Cabin2", "Cabin2"],
            "block": ["1a", "1b", "1a", "1b"],
            "state": ["Seatrade", "Fleet Time", "Fleet Time", "Seatrade"],
        }
    )


class TestDisplayFleetAssignments:
    """The Fleet Assignments overview: Cabin × Block presence heatmap."""

    def test_y_encodes_cabin(self, fleet_assignments_df):
        spec = display_fleet_assignments(fleet_assignments_df).to_dict()
        assert spec["encoding"]["y"]["field"] == "cabin"

    def test_x_encodes_block(self, fleet_assignments_df):
        spec = display_fleet_assignments(fleet_assignments_df).to_dict()
        assert spec["encoding"]["x"]["field"] == "block"

    def test_color_encodes_state(self, fleet_assignments_df):
        spec = display_fleet_assignments(fleet_assignments_df).to_dict()
        assert spec["encoding"]["color"]["field"] == "state"

    def test_color_domain_is_the_two_states(self, fleet_assignments_df):
        spec = display_fleet_assignments(fleet_assignments_df).to_dict()
        assert spec["encoding"]["color"]["scale"]["domain"] == ["Seatrade", "Fleet Time"]

    def test_palette_is_neutral_not_satisfaction(self, fleet_assignments_df):
        # Presence, not goodness — must not borrow the green→red satisfaction scale.
        spec = display_fleet_assignments(fleet_assignments_df).to_dict()
        color_range = spec["encoding"]["color"]["scale"]["range"]
        assert color_range == FLEET_STATE_RANGE
        assert color_range != SATISFACTION_RANGE

    def test_block_axis_uses_decoded_labels(self, fleet_assignments_df):
        spec = display_fleet_assignments(fleet_assignments_df).to_dict()
        rows = spec["data"].get("values") or spec["datasets"][spec["data"]["name"]]
        block_values = {row["block"] for row in rows}
        assert block_values == {"1st·AM", "1st·PM"}

    def test_tooltip_carries_cabin_block_state(self, fleet_assignments_df):
        spec = display_fleet_assignments(fleet_assignments_df).to_dict()
        tooltip_fields = [entry.get("field") for entry in spec["encoding"]["tooltip"]]
        assert {"cabin", "block", "state"} <= set(tooltip_fields)

    def test_no_chart_title_so_the_app_subheader_owns_the_heading(self, fleet_assignments_df):
        # The app renders st.subheader("Fleet Assignments") directly above this chart. A
        # chart-level title of the same text would double the heading (unlike the master grid,
        # which self-titles because it has no subheader). The subheader owns the heading.
        spec = display_fleet_assignments(fleet_assignments_df).to_dict()
        assert "title" not in spec


@pytest.fixture
def seatrade_staffing_df():
    """A Seatrade × Block staffing grid as ``wrangle_seatrade_staffing`` emits it."""
    return pd.DataFrame(
        {
            "seatrade": ["Archery", "Archery", "Sailing", "Sailing"],
            "block": ["1a", "1b", "1a", "1b"],
            "state": ["Running", "Not offered", "Not offered", "Running"],
        }
    )


class TestDisplaySeatradeStaffing:
    """The Seatrade Staffing Schedule overview: Seatrade × Block presence heatmap."""

    def test_y_encodes_seatrade(self, seatrade_staffing_df):
        spec = display_seatrade_staffing(seatrade_staffing_df).to_dict()
        assert spec["encoding"]["y"]["field"] == "seatrade"

    def test_x_encodes_block(self, seatrade_staffing_df):
        spec = display_seatrade_staffing(seatrade_staffing_df).to_dict()
        assert spec["encoding"]["x"]["field"] == "block"

    def test_color_encodes_state(self, seatrade_staffing_df):
        spec = display_seatrade_staffing(seatrade_staffing_df).to_dict()
        assert spec["encoding"]["color"]["field"] == "state"

    def test_color_domain_is_the_two_states(self, seatrade_staffing_df):
        spec = display_seatrade_staffing(seatrade_staffing_df).to_dict()
        assert spec["encoding"]["color"]["scale"]["domain"] == ["Running", "Not offered"]

    def test_palette_is_neutral_not_satisfaction(self, seatrade_staffing_df):
        # Presence, not goodness — must not borrow the green→red satisfaction scale.
        spec = display_seatrade_staffing(seatrade_staffing_df).to_dict()
        color_range = spec["encoding"]["color"]["scale"]["range"]
        assert color_range == STAFFING_STATE_RANGE
        assert color_range != SATISFACTION_RANGE

    def test_block_axis_uses_decoded_labels(self, seatrade_staffing_df):
        spec = display_seatrade_staffing(seatrade_staffing_df).to_dict()
        rows = spec["data"].get("values") or spec["datasets"][spec["data"]["name"]]
        block_values = {row["block"] for row in rows}
        assert block_values == {"1st·AM", "1st·PM"}

    def test_tooltip_carries_seatrade_block_state(self, seatrade_staffing_df):
        spec = display_seatrade_staffing(seatrade_staffing_df).to_dict()
        tooltip_fields = [entry.get("field") for entry in spec["encoding"]["tooltip"]]
        assert {"seatrade", "block", "state"} <= set(tooltip_fields)

    def test_no_chart_title_so_the_app_subheader_owns_the_heading(self, seatrade_staffing_df):
        # The app renders st.subheader("Seatrade Staffing Schedule") directly above this chart;
        # a same-text chart title would double the heading. The subheader owns the heading.
        spec = display_seatrade_staffing(seatrade_staffing_df).to_dict()
        assert "title" not in spec

    def test_y_sort_follows_row_order_not_alphabetical(self):
        # The wrangler emits rows in seatrades_full order; the chart must preserve it rather
        # than let Altair re-sort the y axis alphabetically (Sailing before Archery here).
        grid = pd.DataFrame(
            {
                "seatrade": ["Sailing", "Archery"],
                "block": ["1a", "1a"],
                "state": ["Running", "Running"],
            }
        )
        spec = display_seatrade_staffing(grid).to_dict()
        assert spec["encoding"]["y"]["sort"] == ["Sailing", "Archery"]


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

    def test_coloured_red_green_by_range_band(self, sample_assignment_solution):
        """Colour is a red↔green band on the range: 0–1 yr green, 2 yr yellow, 3+ yr red."""
        spec = display_age_spread_detail(_age_spread_metric(sample_assignment_solution)).to_dict()
        assert spec["encoding"]["color"]["field"] == "band"
        scale = spec["encoding"]["color"]["scale"]
        by_band = dict(zip(scale["domain"], scale["range"], strict=True))
        assert by_band == {"0–1 yr": "#1a9850", "2 yr": "#fee08b", "3+ yr": "#d73027"}

    def test_per_session_marks_stack_into_the_count(self, sample_assignment_solution):
        """The per-session grouping (seatrade x block) must ride a stacking channel (detail),
        not tooltip alone. detail is one row per running session, so count() groups by
        (spread, seatrade, block) = 1 each; tooltip is not a stacking channel, so putting the
        fields there alone overplots every session at height 1 and the bars never reach the
        real per-range count. detail stacks the unit marks so each bar's height is the seatrade
        count for that range."""
        spec = display_age_spread_detail(_age_spread_metric(sample_assignment_solution)).to_dict()
        detail_fields = [entry.get("field") for entry in spec["encoding"]["detail"]]
        assert "seatrade" in detail_fields
        assert "block" in detail_fields


class TestDisplayFairnessWithinDetail:
    """The Fairness Within drill-down: cabin counts per within-cabin CPR spread."""

    def test_x_encodes_spread(self, sample_assignment_solution):
        spec = display_fairness_within_detail(_fair_within_metric(sample_assignment_solution)).to_dict()
        x_fields = [enc["x"].get("field") for enc in _flatten(spec) if "x" in enc]
        assert "spread" in x_fields

    def test_y_is_a_cabin_count(self, sample_assignment_solution):
        spec = display_fairness_within_detail(_fair_within_metric(sample_assignment_solution)).to_dict()
        y_aggregates = [enc["y"].get("aggregate") for enc in _flatten(spec) if "y" in enc]
        assert "count" in y_aggregates

    def test_has_a_reference_line_at_the_average(self, sample_assignment_solution):
        """A rule mark layer draws the average as a reference line."""
        spec = display_fairness_within_detail(_fair_within_metric(sample_assignment_solution)).to_dict()
        marks = [layer.get("mark", {}).get("type") for layer in spec.get("layer", [])]
        assert "rule" in marks

    def test_reference_line_sits_at_the_mean_of_the_plotted_spreads(self, sample_assignment_solution):
        """The rule's x-position is the mean of the *plotted* per-cabin spreads (the same
        quantity ``metric.raw_value`` already is here), so it lands inside the bars' range."""
        metric = _fair_within_metric(sample_assignment_solution)
        spec = display_fairness_within_detail(metric).to_dict()
        assert _rule_layer_average(spec) == pytest.approx(metric.detail["spread"].mean())

    def test_cabin_rides_the_stacking_channel(self, sample_assignment_solution):
        """Cabin name must ride detail (not tooltip alone) so bars reach their true count —
        the same stacking gotcha as Age Spread."""
        spec = display_fairness_within_detail(_fair_within_metric(sample_assignment_solution)).to_dict()
        detail_fields = [entry.get("field") for enc in _flatten(spec) for entry in enc.get("detail", [])]
        assert "cabin" in detail_fields

    def test_tooltip_identifies_the_cabin(self, sample_assignment_solution):
        spec = display_fairness_within_detail(_fair_within_metric(sample_assignment_solution)).to_dict()
        tooltip_fields = [entry.get("field") for enc in _flatten(spec) for entry in enc.get("tooltip", [])]
        assert "cabin" in tooltip_fields


class TestDisplayFairnessBetweenDetail:
    """The Fairness Between drill-down: cabin counts per cabin mean-CPR."""

    def test_x_encodes_mean_cpr(self, sample_assignment_solution):
        spec = display_fairness_between_detail(_fair_between_metric(sample_assignment_solution)).to_dict()
        x_fields = [enc["x"].get("field") for enc in _flatten(spec) if "x" in enc]
        assert "mean_cpr" in x_fields

    def test_y_is_a_cabin_count(self, sample_assignment_solution):
        spec = display_fairness_between_detail(_fair_between_metric(sample_assignment_solution)).to_dict()
        y_aggregates = [enc["y"].get("aggregate") for enc in _flatten(spec) if "y" in enc]
        assert "count" in y_aggregates

    def test_has_a_reference_line_at_the_average(self, sample_assignment_solution):
        spec = display_fairness_between_detail(_fair_between_metric(sample_assignment_solution)).to_dict()
        marks = [layer.get("mark", {}).get("type") for layer in spec.get("layer", [])]
        assert "rule" in marks

    def test_reference_line_sits_at_the_mean_of_plotted_means_not_the_metric_std(self, sample_assignment_solution):
        """The rule's x-position is the mean of the *plotted* cabin mean-CPRs -- NOT
        metric.raw_value, which is the std of those means (the Fairness Between score
        itself, a different quantity/units from what the x-axis plots). Regression: using
        raw_value here drew the line miles from the bars (std ~0.2 vs mean-CPR ~3.5-5.5)."""
        metric = _fair_between_metric(sample_assignment_solution)
        spec = display_fairness_between_detail(metric).to_dict()
        assert _rule_layer_average(spec) == pytest.approx(metric.detail["mean_cpr"].mean())
        assert _rule_layer_average(spec) != pytest.approx(metric.raw_value)

    def test_cabin_rides_the_stacking_channel(self, sample_assignment_solution):
        spec = display_fairness_between_detail(_fair_between_metric(sample_assignment_solution)).to_dict()
        detail_fields = [entry.get("field") for enc in _flatten(spec) for entry in enc.get("detail", [])]
        assert "cabin" in detail_fields

    def test_tooltip_identifies_the_cabin(self, sample_assignment_solution):
        spec = display_fairness_between_detail(_fair_between_metric(sample_assignment_solution)).to_dict()
        tooltip_fields = [entry.get("field") for enc in _flatten(spec) for entry in enc.get("tooltip", [])]
        assert "cabin" in tooltip_fields


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

    def test_routes_fair_within_to_its_builder(self, sample_assignment_solution):
        metric = _fair_within_metric(sample_assignment_solution)
        assert display_metric_detail(metric).to_dict() == display_fairness_within_detail(metric).to_dict()

    def test_routes_fair_between_to_its_builder(self, sample_assignment_solution):
        metric = _fair_between_metric(sample_assignment_solution)
        assert display_metric_detail(metric).to_dict() == display_fairness_between_detail(metric).to_dict()

    def test_raises_for_a_metric_with_no_detail_chart(self, sample_assignment_solution):
        unwired = dataclasses.replace(_preference_metric(sample_assignment_solution), name="Nonexistent")
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
