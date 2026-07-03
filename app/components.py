"""Reusable Streamlit UI components for the Seatrades app."""

from typing import Any, MutableMapping

import streamlit as st

from seatrades.preferences import ValidationError, join_and_validate

# The camper roster is simulated as a unit: identity, the preferences derived from
# it, and the relationships that reference specific campers. Regenerating any input
# must drop all three together — leaving a stale key fails cross-reference validation
# against the fresh roster on the next re-seed.
CAMPER_ROSTER_KEYS = ("camper_identity", "camper_preferences", "camper_relationships")


def clear_camper_roster(session_state: MutableMapping[Any, Any]) -> None:
    """Drop every camper-roster key so they re-seed together on the next run."""
    for key in CAMPER_ROSTER_KEYS:
        if key in session_state:
            del session_state[key]


def show_validation_error(label: str, error: ValidationError):
    """Display a ValidationError in a popover with details and a toast notification."""
    with st.popover(
        f"Continuing without updating {label}. Click for details.",
        icon="🚨",
    ):
        for msg in error.errors:
            st.write(msg)
        st.toast(
            f"Continuing without updating {label}.",
            icon="🚨",
        )


def clear_optimization_results():
    """Reset optimization results in session state."""
    if st.session_state.get("assigned_solution") is not None:
        st.toast("Clearing Previous Optimization Results.")
    st.session_state["optimization_success"] = None
    st.session_state["assigned_solution"] = None
    st.session_state["solver_log"] = None


def try_join_and_validate():
    """If both identity and preferences are present, run cross-reference validation."""
    identity = st.session_state.get("camper_identity")
    preferences = st.session_state.get("camper_preferences")
    seatrades = st.session_state.get("seatrade_preferences")
    relationships = st.session_state.get("camper_relationships")

    if identity is None or preferences is None or seatrades is None:
        return

    try:
        joined_campers, _seatrade_setup, _relationships = join_and_validate(
            identity, preferences, seatrades, relationships
        )
        st.session_state["cabin_camper_prefs"] = joined_campers
    except ValidationError as e:
        show_validation_error("Cross-reference Validation", e)
