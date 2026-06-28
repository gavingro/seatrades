"""Tests for seatrades/preferences.py — join_and_validate and cross-reference checks."""

from io import StringIO

import pandas as pd
import pytest

from seatrades.config import CamperIdentity, CamperPreferences, SeatradesConfig
from seatrades.preferences import (
    ValidationError,
    join_and_validate,
    read_csv_for_schema,
    validate_schema,
)


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


class TestJoinAndValidateSchemaErrors:
    """join_and_validate catches and translates schema errors via validate_schema."""

    def test_schema_error_in_identity(self):
        """Null values in identity produce user-friendly ValidationError."""
        identity_df = pd.DataFrame(
            {
                "cabin": [None],
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

        with pytest.raises(ValidationError) as exc_info:
            join_and_validate(identity_df, preferences_df, seatrade_df)

        assert any("Camper Identity" in e for e in exc_info.value.errors)
        assert any("cabin" in e for e in exc_info.value.errors)

    def test_schema_error_in_preferences(self):
        """Duplicate seatrade choices produce user-friendly ValidationError."""
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
                "seatrade_2": ["Sailing"],
                "seatrade_3": ["Climbing"],
                "seatrade_4": ["Swimming"],
            }
        )
        seatrade_df = pd.DataFrame(
            {
                "seatrade": ["Sailing", "Climbing", "Swimming"],
                "campers_min": [0, 0, 0],
                "campers_max": [10, 10, 10],
            }
        )

        with pytest.raises(ValidationError) as exc_info:
            join_and_validate(identity_df, preferences_df, seatrade_df)

        assert any("Camper Preferences" in e for e in exc_info.value.errors)

    def test_schema_errors_skip_cross_reference(self):
        """When schema validation fails, cross-reference checks are skipped."""
        identity_df = pd.DataFrame(
            {
                "cabin": [None],
                "camper": ["Alice"],
                "gender": ["female"],
            }
        )
        preferences_df = pd.DataFrame(
            {
                "camper": ["Bob"],  # Mismatched name — but schema errors come first
                "seatrade_1": ["FakeTrade"],
                "seatrade_2": ["Sailing"],
                "seatrade_3": ["Climbing"],
                "seatrade_4": ["Swimming"],
            }
        )
        seatrade_df = pd.DataFrame(
            {
                "seatrade": ["Sailing", "Climbing", "Swimming"],
                "campers_min": [0, 0, 0],
                "campers_max": [10, 10, 10],
            }
        )

        with pytest.raises(ValidationError) as exc_info:
            join_and_validate(identity_df, preferences_df, seatrade_df)

        # Should only have schema errors, not cross-reference errors
        for error in exc_info.value.errors:
            assert "not in preferences" not in error
            assert "not in identity" not in error
            assert "not in seatrade config" not in error


class TestValidateSchema:
    """validate_schema translates pandera errors into user-friendly ValidationError."""

    def test_valid_data_passes_through(self):
        identity_df = pd.DataFrame(
            {
                "cabin": ["Puffin"],
                "camper": ["Alice"],
                "gender": ["female"],
            }
        )
        result = validate_schema(CamperIdentity, identity_df, "Camper Identity")
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1

    def test_nullability_error_message(self):
        df = pd.DataFrame(
            {
                "cabin": ["Puffin", None],
                "camper": ["Alice", "Bob"],
                "gender": ["female", "male"],
            }
        )
        with pytest.raises(ValidationError) as exc_info:
            validate_schema(CamperIdentity, df, "Camper Identity")
        assert any("Camper Identity" in e for e in exc_info.value.errors)
        assert any("cabin" in e for e in exc_info.value.errors)

    def test_missing_column_error_message(self):
        df = pd.DataFrame(
            {
                "camper": ["Alice"],
                "gender": ["female"],
            }
        )
        with pytest.raises(ValidationError) as exc_info:
            validate_schema(CamperIdentity, df, "Camper Identity")
        assert any("Camper Identity" in e for e in exc_info.value.errors)
        assert any("cabin" in e for e in exc_info.value.errors)

    def test_uniqueness_check_error_message(self):
        df = pd.DataFrame(
            {
                "camper": ["Alice"],
                "seatrade_1": ["Sailing"],
                "seatrade_2": ["Sailing"],
                "seatrade_3": ["Climbing"],
                "seatrade_4": ["Swimming"],
            }
        )
        with pytest.raises(ValidationError) as exc_info:
            validate_schema(CamperPreferences, df, "Camper Preferences")
        assert any("Camper Preferences" in e for e in exc_info.value.errors)

    def test_multiple_errors_collected(self):
        """Multiple schema errors are all collected, not fail-on-first."""
        df = pd.DataFrame(
            {
                "cabin": [None],
                "camper": [None],
                "gender": ["female"],
            }
        )
        with pytest.raises(ValidationError) as exc_info:
            validate_schema(CamperIdentity, df, "Camper Identity")
        assert len(exc_info.value.errors) >= 2


class TestReadCsvForSchema:
    """read_csv_for_schema reads CSV with usecols from schema, stripping rogue index columns."""

    def test_reads_clean_csv(self):
        csv = StringIO("cabin,camper,gender\nPuffin,Alice,F\nTillikum,Bob,M")
        result = read_csv_for_schema(csv, CamperIdentity)
        assert set(result.columns) == {"cabin", "camper", "gender"}
        assert len(result) == 2

    def test_strips_unnamed_index_column(self):
        csv = StringIO(",cabin,camper,gender\n0,Puffin,Alice,F\n1,Tillikum,Bob,M")
        result = read_csv_for_schema(csv, CamperIdentity)
        assert "Unnamed: 0" not in result.columns
        assert list(result.columns) == ["cabin", "camper", "gender"]

    def test_same_output_with_or_without_rogue_index(self):
        csv_clean = StringIO("cabin,camper,gender\nPuffin,Alice,F\nTillikum,Bob,M")
        csv_with_index = StringIO(",cabin,camper,gender\n0,Puffin,Alice,F\n1,Tillikum,Bob,M")

        result_clean = read_csv_for_schema(csv_clean, CamperIdentity)
        result_with_index = read_csv_for_schema(csv_with_index, CamperIdentity)

        pd.testing.assert_frame_equal(
            result_clean.reset_index(drop=True),
            result_with_index.reset_index(drop=True),
        )

    def test_raises_validation_error_on_missing_schema_columns(self):
        csv = StringIO("cabin,camper\nPuffin,Alice\nTillikum,Bob")  # missing 'gender'
        with pytest.raises(ValidationError) as exc_info:
            read_csv_for_schema(csv, CamperIdentity)
        assert any("gender" in e for e in exc_info.value.errors)
        assert any("missing required column" in e for e in exc_info.value.errors)

    def test_works_with_seatrades_config(self):
        csv = StringIO("seatrade,campers_min,campers_max\nSailing,0,10\nClimbing,2,12")
        result = read_csv_for_schema(csv, SeatradesConfig)
        assert list(result.columns) == ["seatrade", "campers_min", "campers_max"]
        assert len(result) == 2

    def test_works_with_camper_preferences(self):
        csv = StringIO("camper,seatrade_1,seatrade_2,seatrade_3,seatrade_4\nAlice,Sailing,Climbing,Archery,Swimming")
        result = read_csv_for_schema(csv, CamperPreferences)
        assert list(result.columns) == ["camper", "seatrade_1", "seatrade_2", "seatrade_3", "seatrade_4"]

    def test_column_order_matches_schema(self):
        csv = StringIO("gender,camper,cabin\nF,Alice,Puffin\nM,Bob,Tillikum")
        result = read_csv_for_schema(csv, CamperIdentity)
        assert list(result.columns) == ["cabin", "camper", "gender"]
