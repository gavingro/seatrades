"""Reusable Streamlit UI components for the Seatrades app."""

import streamlit as st

from seatrades.preferences import ValidationError, join_and_validate


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


def try_join_and_validate():
    """If both identity and preferences are present, run cross-reference validation."""
    identity = st.session_state.get("camper_identity")
    preferences = st.session_state.get("camper_preferences")
    seatrades = st.session_state.get("seatrade_preferences")

    if identity is None or preferences is None or seatrades is None:
        return

    try:
        joined_campers, seatrade_setup = join_and_validate(identity, preferences, seatrades)
        st.session_state["cabin_camper_prefs"] = joined_campers
    except ValidationError as e:
        show_validation_error("Cross-reference Validation", e)
