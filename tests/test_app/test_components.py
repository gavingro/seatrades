"""Unit tests for reusable app.components helpers."""

from app.components import CAMPER_ROSTER_KEYS, clear_camper_roster


def test_clear_camper_roster_drops_every_roster_key():
    state = {key: object() for key in CAMPER_ROSTER_KEYS}
    state["seatrade_preferences"] = object()  # not part of the roster

    clear_camper_roster(state)

    assert not any(key in state for key in CAMPER_ROSTER_KEYS)
    assert "seatrade_preferences" in state  # unrelated key untouched


def test_clear_camper_roster_tolerates_missing_keys():
    clear_camper_roster({})  # no roster present -> no KeyError
