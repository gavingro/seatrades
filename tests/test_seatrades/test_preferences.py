"""Tests for seatrades/preferences.py — join_and_validate and cross-reference checks."""

import pandas as pd
import pytest

from seatrades.preferences import ValidationError, join_and_validate


class TestJoinAndValidateHappyPath:
    """join_and_validate returns joined DataFrames when all data is consistent."""

    def test_returns_joined_campers_with_all_columns(self):
        identity_df = pd.DataFrame(
            {
                "cabin": ["Puffin", "Puffin", "Tillikum"],
                "camper": ["Alice", "Bob", "Carlos"],
                "gender": ["female", "female", "male"],
            }
        )
        preferences_df = pd.DataFrame(
            {
                "camper": ["Alice", "Bob", "Carlos"],
                "seatrade_1": ["Sailing", "Climbing", "Archery"],
                "seatrade_2": ["Swimming", "Sailing", "Crafts"],
                "seatrade_3": ["Archery", "Swimming", "Sailing"],
                "seatrade_4": ["Crafts", "Archery", "Swimming"],
            }
        )
        seatrade_df = pd.DataFrame(
            {
                "seatrade": ["Sailing", "Climbing", "Archery", "Swimming", "Crafts"],
                "campers_min": [0, 0, 0, 0, 0],
                "campers_max": [10, 10, 10, 10, 10],
            }
        )

        joined_campers, seatrade_setup = join_and_validate(identity_df, preferences_df, seatrade_df)

        assert "cabin" in joined_campers.columns
        assert "camper" in joined_campers.columns
        assert "gender" in joined_campers.columns
        assert "seatrade_1" in joined_campers.columns
        assert len(joined_campers) == 3

    def test_seatrade_setup_passed_through(self):
        identity_df = pd.DataFrame(
            {
                "cabin": ["Puffin"],
                "camper": ["Alice"],
                "gender": ["female"],
            }
        )
        preferences_df = pd.DataFrame(
            {
                "camper": ["Alice"],
                "seatrade_1": ["Sailing"],
                "seatrade_2": ["Climbing"],
                "seatrade_3": ["Archery"],
                "seatrade_4": ["Swimming"],
            }
        )
        seatrade_df = pd.DataFrame(
            {
                "seatrade": ["Sailing", "Climbing", "Archery", "Swimming"],
                "campers_min": [0, 0, 0, 0],
                "campers_max": [10, 10, 10, 10],
            }
        )

        _, seatrade_setup = join_and_validate(identity_df, preferences_df, seatrade_df)

        assert len(seatrade_setup) == 4
        assert "seatrade" in seatrade_setup.columns


class TestJoinAndValidateCamperNameMismatch:
    """join_and_validate raises ValidationError listing all camper name mismatches."""

    def test_camper_in_identity_not_in_preferences(self):
        identity_df = pd.DataFrame(
            {
                "cabin": ["Puffin", "Puffin"],
                "camper": ["Alice", "Bob"],
                "gender": ["female", "female"],
            }
        )
        preferences_df = pd.DataFrame(
            {
                "camper": ["Alice"],
                "seatrade_1": ["Sailing"],
                "seatrade_2": ["Climbing"],
                "seatrade_3": ["Archery"],
                "seatrade_4": ["Swimming"],
            }
        )
        seatrade_df = pd.DataFrame(
            {
                "seatrade": ["Sailing", "Climbing", "Archery", "Swimming"],
                "campers_min": [0, 0, 0, 0],
                "campers_max": [10, 10, 10, 10],
            }
        )

        with pytest.raises(ValidationError) as exc_info:
            join_and_validate(identity_df, preferences_df, seatrade_df)

        assert any("Bob" in e for e in exc_info.value.errors)
        assert any("not in preferences" in e for e in exc_info.value.errors)

    def test_camper_in_preferences_not_in_identity(self):
        identity_df = pd.DataFrame(
            {
                "cabin": ["Puffin"],
                "camper": ["Alice"],
                "gender": ["female"],
            }
        )
        preferences_df = pd.DataFrame(
            {
                "camper": ["Alice", "Bob"],
                "seatrade_1": ["Sailing", "Climbing"],
                "seatrade_2": ["Climbing", "Sailing"],
                "seatrade_3": ["Archery", "Archery"],
                "seatrade_4": ["Swimming", "Swimming"],
            }
        )
        seatrade_df = pd.DataFrame(
            {
                "seatrade": ["Sailing", "Climbing", "Archery", "Swimming"],
                "campers_min": [0, 0, 0, 0],
                "campers_max": [10, 10, 10, 10],
            }
        )

        with pytest.raises(ValidationError) as exc_info:
            join_and_validate(identity_df, preferences_df, seatrade_df)

        assert any("Bob" in e for e in exc_info.value.errors)
        assert any("not in identity" in e for e in exc_info.value.errors)

    def test_mismatch_lists_all_names(self):
        identity_df = pd.DataFrame(
            {
                "cabin": ["Puffin"],
                "camper": ["Alice"],
                "gender": ["female"],
            }
        )
        preferences_df = pd.DataFrame(
            {
                "camper": ["Bob"],
                "seatrade_1": ["Sailing"],
                "seatrade_2": ["Climbing"],
                "seatrade_3": ["Archery"],
                "seatrade_4": ["Swimming"],
            }
        )
        seatrade_df = pd.DataFrame(
            {
                "seatrade": ["Sailing", "Climbing", "Archery", "Swimming"],
                "campers_min": [0, 0, 0, 0],
                "campers_max": [10, 10, 10, 10],
            }
        )

        with pytest.raises(ValidationError) as exc_info:
            join_and_validate(identity_df, preferences_df, seatrade_df)

        assert any("Alice" in e for e in exc_info.value.errors)
        assert any("Bob" in e for e in exc_info.value.errors)


class TestJoinAndValidateNonexistentSeatrade:
    """join_and_validate raises ValidationError listing invalid seatrade names."""

    def test_nonexistent_seatrade_in_preferences(self):
        identity_df = pd.DataFrame(
            {
                "cabin": ["Puffin"],
                "camper": ["Alice"],
                "gender": ["female"],
            }
        )
        preferences_df = pd.DataFrame(
            {
                "camper": ["Alice"],
                "seatrade_1": ["Sailing"],
                "seatrade_2": ["Climbing"],
                "seatrade_3": ["Archery"],
                "seatrade_4": ["Underwater Basket Weaving"],
            }
        )
        seatrade_df = pd.DataFrame(
            {
                "seatrade": ["Sailing", "Climbing", "Archery"],
                "campers_min": [0, 0, 0],
                "campers_max": [10, 10, 10],
            }
        )

        with pytest.raises(ValidationError) as exc_info:
            join_and_validate(identity_df, preferences_df, seatrade_df)

        assert any("Underwater Basket Weaving" in e for e in exc_info.value.errors)
        assert any("not in seatrade config" in e for e in exc_info.value.errors)

    def test_multiple_invalid_seatrades(self):
        identity_df = pd.DataFrame(
            {
                "cabin": ["Puffin", "Puffin"],
                "camper": ["Alice", "Bob"],
                "gender": ["female", "female"],
            }
        )
        preferences_df = pd.DataFrame(
            {
                "camper": ["Alice", "Bob"],
                "seatrade_1": ["Sailing", "Fake1"],
                "seatrade_2": ["Climbing", "Sailing"],
                "seatrade_3": ["Archery", "Fake2"],
                "seatrade_4": ["Swimming", "Climbing"],
            }
        )
        seatrade_df = pd.DataFrame(
            {
                "seatrade": ["Sailing", "Climbing", "Archery", "Swimming"],
                "campers_min": [0, 0, 0, 0],
                "campers_max": [10, 10, 10, 10],
            }
        )

        with pytest.raises(ValidationError) as exc_info:
            join_and_validate(identity_df, preferences_df, seatrade_df)

        error_text = " ".join(exc_info.value.errors)
        assert "Fake1" in error_text
        assert "Fake2" in error_text


class TestJoinAndValidateCombinedErrors:
    """All validation errors are collected and reported together, not fail-on-first."""

    def test_both_camper_mismatch_and_invalid_seatrades(self):
        identity_df = pd.DataFrame(
            {
                "cabin": ["Puffin"],
                "camper": ["Alice"],
                "gender": ["female"],
            }
        )
        preferences_df = pd.DataFrame(
            {
                "camper": ["Bob"],
                "seatrade_1": ["Fake1"],
                "seatrade_2": ["Fake2"],
                "seatrade_3": ["Fake3"],
                "seatrade_4": ["Fake4"],
            }
        )
        seatrade_df = pd.DataFrame(
            {
                "seatrade": ["Sailing", "Climbing"],
                "campers_min": [0, 0],
                "campers_max": [10, 10],
            }
        )

        with pytest.raises(ValidationError) as exc_info:
            join_and_validate(identity_df, preferences_df, seatrade_df)

        errors = exc_info.value.errors
        assert len(errors) >= 2
        assert any("Alice" in e or "Bob" in e for e in errors)
        assert any("Fake1" in e for e in errors)
