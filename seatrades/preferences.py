"""
This file contains logic and data objects capturing the preferences of campers
and camp staff towards seatrades.

Pandera mypy suppressions:
- type: ignore[attr-defined] on CamperSeatradePreferences.loc and .index (line ~54):
  pandera DataFrameModel subclasses are DataFrames at runtime but mypy can't
  verify DataFrame attribute access on them.

Revisit if pandera mypy plugin improves or pandas-stubs adds DataFrameModel support.
"""

from seatrades.config import CamperSeatradePreferences, SeatradesConfig  # noqa: F401 re-export


def add_index_to_campername(
    camper_prefs: CamperSeatradePreferences,
) -> CamperSeatradePreferences:
    """Add index to Camper Names within the prefrence object to avoid name collisions."""
    camper_prefs.loc[:, "camper"] += "." + camper_prefs.index.astype(str)  # type: ignore[attr-defined]
    return camper_prefs
