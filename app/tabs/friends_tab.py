"""Friends tab — define camper relationships (friends / besties / frenemies).

Primary input is an editable grid: a captain types (cabin, camper, cabin, camper,
relationship) rows directly. A CSV upload is an optional bulk-entry convenience that
seeds the grid. Besties are enforced by the solver this slice; friends and frenemies
are saved and validated but not yet enforced.
"""

import pandas as pd
import streamlit as st

from app.components import clear_optimization_results, show_validation_error
from seatrades.config import RELATIONSHIP_TYPES, CamperRelationships
from seatrades.preferences import ValidationError, read_csv_for_schema, validate_relationships

_RELATIONSHIP_COLUMNS = ["cabin_1", "camper_1", "cabin_2", "camper_2", "relationship"]


def empty_relationships() -> pd.DataFrame:
    """An empty relationships grid with the right columns and dtypes."""
    return pd.DataFrame({col: pd.Series(dtype="object") for col in _RELATIONSHIP_COLUMNS})


class FriendsTab:
    """Tab content for defining camper relationships."""

    def generate(self) -> None:
        st.subheader("Friends")
        st.caption(
            "Pair up campers. **Besties** share an identical schedule (enforced now). "
            "**Friends** and **frenemies** are saved for later. Type rows directly, or "
            "upload a CSV to fill the grid."
        )

        uploaded = st.file_uploader(
            label="Upload relationships (cabin_1, camper_1, cabin_2, camper_2, relationship).",
            type="csv",
            help="Optional. Seeds the grid below — you can also type rows in directly.",
            key="relationships_uploader",
        )
        if uploaded:
            try:
                data = read_csv_for_schema(uploaded, CamperRelationships)
            except ValidationError as e:
                show_validation_error("Camper Relationships", e)
            else:
                _update_relationships(data)

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
                    help="One of friends, besties, frenemies.",
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
