"""Tests for seatrades/simulation.py — pure data generators, no Streamlit."""

import pandas as pd

from seatrades.config import CamperSimulationConfig, SeatradeSimulationConfig
from seatrades.simulation import (
    ALL_CABIN_DICT,
    BOY_CABIN_EXAMPLES,
    GIRL_CABIN_EXAMPLES,
    SEATRADE_EXAMPLES,
    simulate_cabin_camper_preferences,
    simulate_seatrade_preferences,
)


class TestSimulateSeatradePreferences:
    """simulate_seatrade_preferences produces a valid SeatradesConfig DataFrame."""

    def test_returns_dataframe_validating_against_seatrades_config(self):
        config = SeatradeSimulationConfig()
        result = simulate_seatrade_preferences(config)
        assert isinstance(result, pd.DataFrame)
        assert "seatrade" in result.columns
        assert "campers_min" in result.columns
        assert "campers_max" in result.columns
        assert len(result) == config.num_seatrades

    def test_seatrade_names_are_from_examples(self):
        config = SeatradeSimulationConfig(num_seatrades=5)
        result = simulate_seatrade_preferences(config)
        for name in result["seatrade"]:
            assert name in SEATRADE_EXAMPLES

    def test_campers_min_less_than_or_equal_to_campers_max(self):
        config = SeatradeSimulationConfig(
            camper_capacity_min=8,
            camper_capacity_max=15,
        )
        result = simulate_seatrade_preferences(config)
        assert (result["campers_min"] <= result["campers_max"]).all()

    def test_pandera_validation_passes(self):
        """The returned DataFrame passes strict SeatradesConfig validation."""
        config = SeatradeSimulationConfig()
        result = simulate_seatrade_preferences(config)
        # If this doesn't raise, validation passed
        from seatrades.preferences import SeatradesConfig as SeatradesConfigSchema

        SeatradesConfigSchema.validate(result)


class TestSimulateCabinCamperPreferences:
    """simulate_cabin_camper_preferences produces a valid CamperSeatradePreferences DataFrame."""

    def test_returns_dataframe_with_expected_columns(self):
        seatrade_prefs = simulate_seatrade_preferences(SeatradeSimulationConfig())
        camper_config = CamperSimulationConfig()
        result = simulate_cabin_camper_preferences(camper_config, seatrade_prefs)
        assert isinstance(result, pd.DataFrame)
        for col in ["cabin", "camper", "gender", "seatrade_1", "seatrade_2", "seatrade_3", "seatrade_4"]:
            assert col in result.columns

    def test_cabin_count_matches_config(self):
        seatrade_prefs = simulate_seatrade_preferences(SeatradeSimulationConfig())
        config = CamperSimulationConfig(num_cabins=4)
        result = simulate_cabin_camper_preferences(config, seatrade_prefs)
        assert result["cabin"].nunique() <= config.num_cabins

    def test_genders_match_cabin_assignments(self):
        seatrade_prefs = simulate_seatrade_preferences(SeatradeSimulationConfig())
        config = CamperSimulationConfig(num_cabins=4)
        result = simulate_cabin_camper_preferences(config, seatrade_prefs)
        for cabin in result["cabin"].unique():
            gender = result.loc[result["cabin"] == cabin, "gender"].iloc[0]
            assert gender == ALL_CABIN_DICT[cabin]

    def test_preferences_are_from_available_seatrades(self):
        seatrade_prefs = simulate_seatrade_preferences(SeatradeSimulationConfig())
        config = CamperSimulationConfig(num_cabins=4)
        result = simulate_cabin_camper_preferences(config, seatrade_prefs)
        available = set(seatrade_prefs["seatrade"].tolist())
        for col in ["seatrade_1", "seatrade_2", "seatrade_3", "seatrade_4"]:
            for val in result[col]:
                assert val in available

    def test_pandera_validation_passes(self):
        seatrade_prefs = simulate_seatrade_preferences(SeatradeSimulationConfig())
        config = CamperSimulationConfig(num_cabins=4)
        result = simulate_cabin_camper_preferences(config, seatrade_prefs)
        from seatrades.preferences import CamperSeatradePreferences

        CamperSeatradePreferences.validate(result)


class TestDataConstants:
    """Simulation data constants are accessible and well-formed."""

    def test_seatrade_examples_non_empty(self):
        assert len(SEATRADE_EXAMPLES) > 0
        assert all(isinstance(s, str) for s in SEATRADE_EXAMPLES)

    def test_cabin_examples_cover_girls_and_boys(self):
        assert len(GIRL_CABIN_EXAMPLES) > 0
        assert len(BOY_CABIN_EXAMPLES) > 0
        assert len(ALL_CABIN_DICT) == len(GIRL_CABIN_EXAMPLES) + len(BOY_CABIN_EXAMPLES)

    def test_all_cabin_dict_maps_to_gender(self):
        for _cabin, gender in ALL_CABIN_DICT.items():
            assert gender in ("female", "male")
