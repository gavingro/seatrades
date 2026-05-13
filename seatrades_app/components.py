"""Reusable Streamlit UI components for the Seatrades app."""

import streamlit as st

from seatrades.preferences import ValidationError


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
