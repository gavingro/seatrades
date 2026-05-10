"""
Cross-reference validation and 3→2 DataFrame join for camper data.

Pandera mypy suppressions:
- type: ignore[attr-defined] on DataFrameModel subclasses' .loc and .index:
  pandera DataFrameModel subclasses are DataFrames at runtime but mypy can't
  verify DataFrame attribute access on them.

Revisit if pandera mypy plugin improves or pandas-stubs adds DataFrameModel support.
"""

import pandas as pd

from seatrades.config import CamperIdentity, CamperPreferences, SeatradesConfig


class ValidationError(Exception):
    """Raised when cross-reference validation finds errors.

    Collects all errors before raising — never fails on the first problem.
    """

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


def join_and_validate(
    identity_df: pd.DataFrame,
    preferences_df: pd.DataFrame,
    seatrade_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate cross-references and join 3 DataFrames into 2.

    Takes camper identity, camper preferences, and seatrade config DataFrames.
    Validates that camper names match between identity and preferences, and
    that all seatrade names in preferences exist in the seatrade config.

    Returns (joined_campers, seatrade_setup) where joined_campers has columns:
    cabin, camper, gender, seatrade_1..4.
    """
    identity_validated = CamperIdentity.validate(identity_df)
    preferences_validated = CamperPreferences.validate(preferences_df)
    seatrade_validated = SeatradesConfig.validate(seatrade_df)

    errors: list[str] = []

    identity_names = set(identity_validated["camper"])
    preference_names = set(preferences_validated["camper"])

    in_identity_not_prefs = identity_names - preference_names
    if in_identity_not_prefs:
        names = ", ".join(sorted(in_identity_not_prefs))
        errors.append(f"Campers in identity but not in preferences: {names}")

    in_prefs_not_identity = preference_names - identity_names
    if in_prefs_not_identity:
        names = ", ".join(sorted(in_prefs_not_identity))
        errors.append(f"Campers in preferences but not in identity: {names}")

    available_seatrades = set(seatrade_validated["seatrade"])
    pref_cols = ["seatrade_1", "seatrade_2", "seatrade_3", "seatrade_4"]
    all_pref_seatrades: set[str] = set()
    for col in pref_cols:
        all_pref_seatrades.update(preferences_validated[col])
    invalid_seatrades = all_pref_seatrades - available_seatrades
    if invalid_seatrades:
        names = ", ".join(sorted(invalid_seatrades))
        errors.append(f"Seatrades in preferences but not in seatrade config: {names}")

    if errors:
        raise ValidationError(errors)

    joined = identity_validated.merge(preferences_validated, on="camper")
    return joined, seatrade_validated


# Kept for backward compatibility during migration — will be removed.
from seatrades.config import CamperSeatradePreferences  # noqa: F401, E402


def add_index_to_campername(
    camper_prefs: CamperSeatradePreferences,
) -> CamperSeatradePreferences:
    """Add index to Camper Names within the prefrence object to avoid name collisions."""
    camper_prefs.loc[:, "camper"] += "." + camper_prefs.index.astype(str)  # type: ignore[attr-defined]
    return camper_prefs
