"""Friends tab — define camper relationships (friends / besties / frenemies).

Primary input is an editable grid: a captain types (cabin, camper, cabin, camper,
relationship) rows directly. A CSV upload is an optional bulk-entry convenience that
seeds the grid. All three relationship types are enforced by the solver as hard
constraints.
"""

import pandas as pd
import streamlit as st

from app.components import clear_optimization_results, show_validation_error
from seatrades.config import RELATIONSHIP_TYPES, CamperRelationships
from seatrades.preferences import (
    ValidationError,
    empty_relationships,
    read_csv_for_schema,
    validate_relationships,
)


class FriendsTab:
    """Tab content for defining camper relationships."""

    def generate(self) -> None:
        st.subheader("Friends")
        st.markdown(
            "Pair up campers if you want to honor sepcific friendships beyond the 'cabin togetherness' scores"
            "in the scheduling setup. Each row links two "
            "campers plus a relationship type. Type rows directly in the grid below, or upload a CSV to fill it. Every "
            "relationship is a **hard rule**: the optimizer must satisfy all of them, or it "
            "reports that no schedule is possible."
        )
        with st.expander("What relationships are available? (Friends, Besties, Frenemies)"):
            st.markdown(
                "- **Friends** — the pair shares **at least one seatrade session**: the same seatrade, in "
                "the same fleet and block (so they're together at least once during the week). "
                "_Needs at least one preferred seatrade in common, or it can't be honoured._\n"
                "- **Besties** — the pair gets an **identical seatrade schedule**: the same seatrades in "
                "the same blocks for the whole week (this also puts them in the same fleet). "
                "_Needs at least two preferred seatrades in common._\n"
                "- **Frenemies** — the pair shares **no session**: they are never placed in the "
                "same seatrade at the same time.\n\n"
                "Order within a pair doesn't matter, and each pair may appear only once. Besties "
                "or friends that don't share enough preferred seatrades are flagged here, before "
                "you optimize, so you can fix typos instead of waiting on a failed solve."
            )

        uploaded = st.file_uploader(
            label="Upload relationships (cabin_1, camper_1, cabin_2, camper_2, relationship).",
            type="csv",
            help="Optional. Seeds the grid below — you can also type rows in directly.",
            key="relationships_uploader",
        )
        if uploaded:
            try:
                uploaded_relationships = read_csv_for_schema(uploaded, CamperRelationships)
            except ValidationError as e:
                show_validation_error("Camper Relationships", e)
            else:
                _update_relationships(uploaded_relationships)

        current = st.session_state.get("camper_relationships")
        if current is None or current.empty:
            current = empty_relationships()

        edited = st.data_editor(
            current,
            num_rows="dynamic",
            key="relationships_editor",
            use_container_width=True,
            column_config={
                "relationship": st.column_config.SelectboxColumn(
                    "relationship",
                    options=RELATIONSHIP_TYPES,
                    required=True,
                    help=(
                        "friends = share ≥1 session · besties = identical schedule · frenemies = never share a session."
                    ),
                ),
            },
        )
        if not edited.reset_index(drop=True).equals(current.reset_index(drop=True)):
            _update_relationships(edited)


def _update_relationships(relationships: pd.DataFrame) -> None:
    """Persist the edited grid and surface validation feedback against current campers."""
    st.session_state["camper_relationships"] = relationships.reset_index(drop=True)
    clear_optimization_results()

    joined = st.session_state.get("cabin_camper_prefs")
    if joined is None or relationships.empty:
        return
    try:
        validate_relationships(relationships, joined, "Camper Relationships")
        st.toast("Updating Camper Relationships.")
    except ValidationError as e:
        show_validation_error("Camper Relationships", e)
