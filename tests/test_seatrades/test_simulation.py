"""Tests for seatrades/simulation.py — pure data generators, no Streamlit."""

import pandas as pd

from seatrades.config import CamperRelationships, CamperSimulationConfig, SeatradeSimulationConfig
from seatrades.preferences import validate_relationships
from seatrades.simulation import (
    ALL_CABIN_DICT,
    BOY_CABIN_EXAMPLES,
    GIRL_CABIN_EXAMPLES,
    SEATRADE_EXAMPLES,
    simulate_camper_identity,
    simulate_camper_preferences,
    simulate_camper_relationships,
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


class TestSimulateCamperIdentity:
    """simulate_camper_identity produces a valid CamperIdentity DataFrame."""

    def test_returns_dataframe_with_expected_columns(self):
        config = CamperSimulationConfig()
        result = simulate_camper_identity(config)
        assert isinstance(result, pd.DataFrame)
        for col in ["cabin", "camper", "gender", "age"]:
            assert col in result.columns

    def test_ages_are_positive_integers(self):
        config = CamperSimulationConfig(num_cabins=8)
        result = simulate_camper_identity(config)
        assert result["age"].dtype.kind == "i"
        assert (result["age"] >= 1).all()

    def test_ages_cluster_within_each_cabin(self):
        """Each cabin stays within a few years of its base, never the camp range."""
        config = CamperSimulationConfig(num_cabins=8, base_age_min=13, base_age_max=16, age_spread=0.7)
        result = simulate_camper_identity(config)
        for cabin in result["cabin"].unique():
            ages = result.loc[result["cabin"] == cabin, "age"]
            # Jitter is a ±1–2 minority around one base, so the spread stays tight.
            assert ages.max() - ages.min() <= 5

    def test_most_campers_sit_on_their_cabin_base_age(self):
        """Camp-wide, most campers land on their cabin's modal (base) age — a clear plurality."""
        # A tight spread makes "most" unambiguous; the mechanism (base + jitter) is the same.
        config = CamperSimulationConfig(num_cabins=8, base_age_min=13, base_age_max=16, age_spread=0.5)
        result = simulate_camper_identity(config)
        cabin_base = result.groupby("cabin")["age"].transform(lambda a: a.mode().iloc[0])
        assert (result["age"] == cabin_base).mean() >= 0.5

    def test_base_ages_vary_across_camp(self):
        """Independent per-cabin base draws give the camp a spread of younger/older cabins."""
        config = CamperSimulationConfig(num_cabins=8, base_age_min=13, base_age_max=16, age_spread=0.7)
        result = simulate_camper_identity(config)
        cabin_modal_ages = result.groupby("cabin")["age"].agg(lambda a: a.mode().iloc[0])
        assert cabin_modal_ages.nunique() >= 2

    def test_cabin_count_matches_config(self):
        config = CamperSimulationConfig(num_cabins=4)
        result = simulate_camper_identity(config)
        assert result["cabin"].nunique() <= config.num_cabins

    def test_genders_match_cabin_assignments(self):
        config = CamperSimulationConfig(num_cabins=4)
        result = simulate_camper_identity(config)
        for cabin in result["cabin"].unique():
            gender = result.loc[result["cabin"] == cabin, "gender"].iloc[0]
            assert gender == ALL_CABIN_DICT[cabin]

    def test_pandera_validation_passes(self):
        config = CamperSimulationConfig()
        result = simulate_camper_identity(config)
        from seatrades.config import CamperIdentity

        CamperIdentity.validate(result)


class TestSimulateCamperPreferences:
    """simulate_camper_preferences produces a valid CamperPreferences DataFrame."""

    def test_returns_dataframe_with_expected_columns(self):
        seatrade_prefs = simulate_seatrade_preferences(SeatradeSimulationConfig())
        config = CamperSimulationConfig()
        identity_df = simulate_camper_identity(config)
        result = simulate_camper_preferences(identity_df, seatrade_prefs)
        assert isinstance(result, pd.DataFrame)
        for col in ["camper", "seatrade_1", "seatrade_2", "seatrade_3", "seatrade_4"]:
            assert col in result.columns

    def test_preferences_are_from_available_seatrades(self):
        seatrade_prefs = simulate_seatrade_preferences(SeatradeSimulationConfig())
        config = CamperSimulationConfig(num_cabins=4)
        identity_df = simulate_camper_identity(config)
        result = simulate_camper_preferences(identity_df, seatrade_prefs)
        available = set(seatrade_prefs["seatrade"].tolist())
        for col in ["seatrade_1", "seatrade_2", "seatrade_3", "seatrade_4"]:
            for val in result[col]:
                assert val in available

    def test_camper_names_match_identity(self):
        seatrade_prefs = simulate_seatrade_preferences(SeatradeSimulationConfig())
        config = CamperSimulationConfig(num_cabins=4)
        identity_df = simulate_camper_identity(config)
        result = simulate_camper_preferences(identity_df, seatrade_prefs)
        assert set(result["camper"]) == set(identity_df["camper"])

    def test_pandera_validation_passes(self):
        seatrade_prefs = simulate_seatrade_preferences(SeatradeSimulationConfig())
        config = CamperSimulationConfig(num_cabins=4)
        identity_df = simulate_camper_identity(config)
        result = simulate_camper_preferences(identity_df, seatrade_prefs)
        from seatrades.config import CamperPreferences

        CamperPreferences.validate(result)


class TestSimulateCamperRelationships:
    """simulate_camper_relationships produces a feasible mock besties pair."""

    def _identity(self):
        return pd.DataFrame(
            {
                "cabin": ["Puffin", "Puffin", "Tillikum"],
                "camper": ["Alice", "Bob", "Carlos"],
                "gender": ["female", "female", "male"],
            }
        )

    def _preferences(self):
        # Alice and Bob (same cabin) share Sailing + Climbing (≥2). Carlos shares <2 with each.
        return pd.DataFrame(
            {
                "camper": ["Alice", "Bob", "Carlos"],
                "seatrade_1": ["Sailing", "Climbing", "Archery"],
                "seatrade_2": ["Climbing", "Sailing", "Kayaking"],
                "seatrade_3": ["Archery", "Archery", "Tubing"],
                "seatrade_4": ["Crafts", "Swimming", "Wibit"],
            }
        )

    def _roster_identity(self):
        return pd.DataFrame(
            {
                "cabin": ["Puffin", "Puffin", "Tillikum", "Tillikum", "Orca", "Narwhal"],
                "camper": ["Alice", "Bob", "Carlos", "Dana", "Eve", "Frank"],
                "gender": ["female", "female", "male", "male", "female", "male"],
            }
        )

    def _roster_preferences(self):
        # Alice&Bob (same cabin) share ≥2 → besties. Other pairs share ≥1 → friends/frenemies.
        return pd.DataFrame(
            {
                "camper": ["Alice", "Bob", "Carlos", "Dana", "Eve", "Frank"],
                "seatrade_1": ["Sailing", "Climbing", "Archery", "Sailing", "Climbing", "Kayaking"],
                "seatrade_2": ["Climbing", "Sailing", "Sailing", "Archery", "Kayaking", "Tubing"],
                "seatrade_3": ["Archery", "Archery", "Kayaking", "Crafts", "Tubing", "Wibit"],
                "seatrade_4": ["Crafts", "Swimming", "Tubing", "Wibit", "Wibit", "Swimming"],
            }
        )

    def test_seeds_friends_and_frenemies_rows(self):
        result = simulate_camper_relationships(self._roster_identity(), self._roster_preferences())

        seeded = set(result["relationship"])
        assert "friends" in seeded
        assert "frenemies" in seeded

    def test_seeded_pairs_use_distinct_campers(self):
        result = simulate_camper_relationships(self._roster_identity(), self._roster_preferences())

        campers = [(r.cabin_1, r.camper_1) for r in result.itertuples()] + [
            (r.cabin_2, r.camper_2) for r in result.itertuples()
        ]
        # Disjoint camper sets across pairs preclude contradictory friend/frenemy chains.
        assert len(campers) == len(set(campers))

    def test_seeded_roster_passes_validation(self):
        identity, prefs = self._roster_identity(), self._roster_preferences()
        joined = identity.merge(prefs, on="camper")

        result = simulate_camper_relationships(identity, prefs)

        validate_relationships(result, joined, "Camper Relationships")

    def test_returns_single_same_cabin_besties_row(self):
        result = simulate_camper_relationships(self._identity(), self._preferences())

        assert len(result) == 1
        row = result.iloc[0]
        assert row["relationship"] == "besties"
        assert row["cabin_1"] == row["cabin_2"]

    def test_generated_pair_passes_validation(self):
        identity, prefs = self._identity(), self._preferences()
        joined = identity.merge(prefs, on="camper")

        result = simulate_camper_relationships(identity, prefs)

        # The seeded pair must survive validate_relationships (known + feasible).
        validate_relationships(result, joined, "Camper Relationships")

    def test_empty_when_no_feasible_pair(self):
        identity = pd.DataFrame(
            {"cabin": ["Puffin", "Puffin"], "camper": ["Solo", "Lone"], "gender": ["female", "female"]}
        )
        prefs = pd.DataFrame(
            {
                "camper": ["Solo", "Lone"],
                "seatrade_1": ["Archery", "Sailing"],
                "seatrade_2": ["Climbing", "Crafts"],
                "seatrade_3": ["Kayaking", "Tubing"],
                "seatrade_4": ["Wibit", "Swimming"],
            }
        )

        result = simulate_camper_relationships(identity, prefs)

        assert len(result) == 0
        CamperRelationships.validate(result)
