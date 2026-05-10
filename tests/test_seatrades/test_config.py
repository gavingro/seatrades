"""Tests for config classes extracted to seatrades/config.py."""

import pandas as pd
import pytest
from pandera.errors import SchemaError

from seatrades.config import (
    CamperSeatradePreferences,
    CamperSimulationConfig,
    OptimizationConfig,
    SeatradesConfig,
    SeatradeSimulationConfig,
)


class TestOptimizationConfig:
    def test_defaults(self):
        config = OptimizationConfig()
        assert config.preference_weight == 3
        assert config.cabins_weight == 2
        assert config.sparsity_weight == 1
        assert config.max_seatrades_per_fleet is None

    def test_custom_values(self):
        config = OptimizationConfig(
            preference_weight=5,
            cabins_weight=1,
            sparsity_weight=0,
            max_seatrades_per_fleet=4,
        )
        assert config.preference_weight == 5
        assert config.cabins_weight == 1
        assert config.sparsity_weight == 0
        assert config.max_seatrades_per_fleet == 4


class TestCamperSimulationConfig:
    def test_defaults(self):
        config = CamperSimulationConfig()
        assert config.num_cabins == 8
        assert config.num_preferences == 4
        assert config.camper_per_cabin_min == 8
        assert config.camper_per_cabin_max == 12

    def test_custom_values(self):
        config = CamperSimulationConfig(
            num_cabins=12,
            num_preferences=3,
            camper_per_cabin_min=6,
            camper_per_cabin_max=10,
        )
        assert config.num_cabins == 12
        assert config.num_preferences == 3
        assert config.camper_per_cabin_min == 6
        assert config.camper_per_cabin_max == 10


class TestSeatradeSimulationConfig:
    def test_defaults(self):
        config = SeatradeSimulationConfig()
        assert config.num_seatrades == 16
        assert config.camper_capacity_min == 8
        assert config.camper_capacity_max == 15

    def test_custom_values(self):
        config = SeatradeSimulationConfig(
            num_seatrades=10,
            camper_capacity_min=5,
            camper_capacity_max=20,
        )
        assert config.num_seatrades == 10
        assert config.camper_capacity_min == 5
        assert config.camper_capacity_max == 20


class TestSeatradesConfig:
    def test_valid_data_passes_validation(self):
        df = pd.DataFrame(
            {
                "seatrade": ["Sailing", "Climbing"],
                "campers_min": [5, 3],
                "campers_max": [10, 8],
            }
        )
        validated = SeatradesConfig.validate(df)
        assert len(validated) == 2

    def test_min_greater_than_max_fails(self):
        df = pd.DataFrame(
            {
                "seatrade": ["Sailing"],
                "campers_min": [15],
                "campers_max": [5],
            }
        )
        with pytest.raises(SchemaError):
            SeatradesConfig.validate(df)


class TestCamperSeatradePreferences:
    def test_valid_data_passes_validation(self):
        df = pd.DataFrame(
            {
                "cabin": ["Puffin"],
                "camper": ["Alice"],
                "gender": ["female"],
                "seatrade_1": ["Sailing"],
                "seatrade_2": ["Climbing"],
                "seatrade_3": ["Archery"],
                "seatrade_4": ["Swimming"],
            }
        )
        validated = CamperSeatradePreferences.validate(df)
        assert len(validated) == 1

    def test_duplicate_choices_fail(self):
        df = pd.DataFrame(
            {
                "cabin": ["Puffin"],
                "camper": ["Alice"],
                "gender": ["female"],
                "seatrade_1": ["Sailing"],
                "seatrade_2": ["Sailing"],
                "seatrade_3": ["Climbing"],
                "seatrade_4": ["Swimming"],
            }
        )
        with pytest.raises(SchemaError):
            CamperSeatradePreferences.validate(df)


class TestReexports:
    def test_seatrades_config_importable_from_preferences(self):
        from seatrades.preferences import CamperSeatradePreferences, SeatradesConfig

        assert SeatradesConfig is not None
        assert CamperSeatradePreferences is not None
