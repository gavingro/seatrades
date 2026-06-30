"""Tests for config classes extracted to seatrades/config.py."""

import pandas as pd
import pytest
from pandera.errors import SchemaError

from seatrades.config import (
    CamperIdentity,
    CamperPreferences,
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
        assert config.force_same_fleet_all_week is False

    def test_force_same_fleet_all_week_opt_in(self):
        assert OptimizationConfig(force_same_fleet_all_week=True).force_same_fleet_all_week is True

    def test_solver_default_is_not_shared(self):
        config_a = OptimizationConfig()
        config_b = OptimizationConfig()
        assert config_a.solver is not config_b.solver

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


class TestCamperIdentity:
    def test_valid_data_passes_validation(self):
        df = pd.DataFrame(
            {
                "cabin": ["Puffin", "Tillikum"],
                "camper": ["Alice", "Bob"],
                "gender": ["female", "male"],
            }
        )
        validated = CamperIdentity.validate(df)
        assert len(validated) == 2

    def test_missing_column_fails(self):
        df = pd.DataFrame(
            {
                "cabin": ["Puffin"],
                "camper": ["Alice"],
            }
        )
        with pytest.raises(SchemaError):
            CamperIdentity.validate(df)


class TestCamperPreferences:
    def test_valid_data_passes_validation(self):
        df = pd.DataFrame(
            {
                "camper": ["Alice"],
                "seatrade_1": ["Sailing"],
                "seatrade_2": ["Climbing"],
                "seatrade_3": ["Archery"],
                "seatrade_4": ["Swimming"],
            }
        )
        validated = CamperPreferences.validate(df)
        assert len(validated) == 1

    def test_duplicate_choices_fail(self):
        df = pd.DataFrame(
            {
                "camper": ["Alice"],
                "seatrade_1": ["Sailing"],
                "seatrade_2": ["Sailing"],
                "seatrade_3": ["Climbing"],
                "seatrade_4": ["Swimming"],
            }
        )
        with pytest.raises(SchemaError):
            CamperPreferences.validate(df)


class TestReexports:
    def test_models_importable_from_preferences(self):
        from seatrades.preferences import (
            SeatradesConfig,
            ValidationError,
            join_and_validate,
        )

        assert SeatradesConfig is not None
        assert ValidationError is not None
        assert join_and_validate is not None
