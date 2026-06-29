"""
Cross-reference validation and 3→2 DataFrame join for camper data.

Pandera mypy suppressions:
- type: ignore[attr-defined] on DataFrameModel subclasses' .loc and .index:
  pandera DataFrameModel subclasses are DataFrames at runtime but mypy can't
  verify DataFrame attribute access on them.

Revisit if pandera mypy plugin improves or pandas-stubs adds DataFrameModel support.
"""

from __future__ import annotations

import re

import pandas as pd
from pandera import DataFrameModel
from pandera.errors import SchemaError, SchemaErrors

from seatrades.config import (
    BESTIES_MIN_SHARED_SEATRADES,
    FRIENDS_MIN_SHARED_SEATRADES,
    PREF_COLS,
    CamperIdentity,
    CamperPreferences,
    CamperRelationships,
    SeatradesConfig,
)


def empty_relationships() -> pd.DataFrame:
    """An empty, schema-valid CamperRelationships frame (columns derived from the schema)."""
    columns = CamperRelationships.to_schema().columns.keys()
    empty = pd.DataFrame({col: pd.Series(dtype="object") for col in columns})
    return CamperRelationships.validate(empty)  # type: ignore[return-value]


class ValidationError(Exception):
    """Raised when validation finds errors.

    Collects all errors before raising — never fails on the first problem.
    """

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


# Pandera check names → user-friendly message templates.
# Keys are substrings matched against the `check` column in failure_cases.
_CHECK_MESSAGES = {
    "not_nullable": 'has missing or empty values in column "{column}"',
    "coerce": 'has invalid values in column "{column}"',
    "column_in_dataframe": 'is missing required column "{failure_case}"',
}


def validate_schema(
    schema: type[DataFrameModel],
    df: pd.DataFrame,
    label: str,
) -> pd.DataFrame:
    """Validate a DataFrame against a Pandera schema, translating errors to user-friendly messages.

    Uses lazy validation to collect all errors before raising.
    Raises ValidationError with one message per distinct error type.
    """
    try:
        return schema.validate(df, lazy=True)  # type: ignore[union-attr]
    except SchemaErrors as e:
        errors: list[str] = []
        fc = e.failure_cases
        for check_name in fc["check"].unique():
            check_rows = fc[fc["check"] == check_name]
            columns = check_rows["column"].unique()
            for col in columns:
                col_rows = check_rows[check_rows["column"] == col]
                indices = col_rows["index"].dropna().unique().tolist()
                failure_cases = col_rows["failure_case"].dropna().unique().tolist()
                msg_template = _CHECK_MESSAGES.get(check_name, 'failed check "{check}" in column "{column}"')
                msg = msg_template.format(
                    column=col,
                    check=check_name,
                    label=label,
                    failure_case=", ".join(str(f) for f in failure_cases),
                )
                if indices:
                    msg += f" (rows {_format_indices(indices)})"
                errors.append(f'"{label}" {msg}')
        raise ValidationError(errors) from e
    except SchemaError as e:
        # Single error (non-lazy path shouldn't reach here, but handle defensively)
        raise ValidationError([f'"{label}" {e}']) from e


def _format_indices(indices: list) -> str:
    """Format row indices for display, capping at 5."""
    if len(indices) > 5:
        return ", ".join(str(i) for i in indices[:5]) + f", ... ({len(indices)} total)"
    return ", ".join(str(i) for i in indices)


def read_csv_for_schema(file_like, schema_class: type[DataFrameModel], **kwargs) -> pd.DataFrame:
    """Read a CSV selecting only the columns defined by a Pandera schema.

    Uses schema column names as usecols to filter out rogue index columns
    (e.g. 'Unnamed: 0' from re-uploaded Streamlit exports). Reorders columns
    to match schema definition order. Raises ValidationError if required
    columns are missing from the CSV.
    """
    columns = list(schema_class.to_schema().columns.keys())
    try:
        df = pd.read_csv(file_like, usecols=columns, **kwargs)
    except ValueError as e:
        # Translate pandas usecols error into a user-friendly message.
        # Pandas format: "Usecols do not match columns, columns expected but not found: ['col1', 'col2']"
        match = re.search(r"columns expected but not found: \[(.+?)]", str(e))
        if match:
            missing = match.group(1).replace("'", "").replace('"', "")
            msg = f"CSV is missing required column(s): {missing}"
        else:
            msg = str(e)
        raise ValidationError([msg]) from e
    return df[columns]


def validate_relationships(
    relationships_df: pd.DataFrame,
    joined_campers: pd.DataFrame,
    label: str = "Camper Relationships",
) -> pd.DataFrame:
    """Validate camper relationship pairs against the joined campers.

    Checks (collect-all-errors-then-raise, like join_and_validate):
    schema, self-pairs, order-insensitive duplicate pairs, that both campers
    exist in joined_campers, that besties pairs share enough preferences to have
    a feasible identical schedule, and that friends pairs share at least one
    preferred seatrade so a shared session is possible. joined_campers carries
    seatrade_1..4 so these feasibility checks can run before solver time.

    Returns the validated relationships DataFrame.
    """
    errors: list[str] = []

    validated: pd.DataFrame | None = None
    try:
        validated = validate_schema(CamperRelationships, relationships_df, label)
    except ValidationError as e:
        errors.extend(e.errors)

    # Row-level checks only once the schema (columns, types, non-null) is sound.
    if not errors:
        assert validated is not None
        prefs_by_camper = {
            (row.cabin, row.camper): {getattr(row, col) for col in PREF_COLS}
            for row in joined_campers.itertuples(index=False)
        }
        known_campers = set(prefs_by_camper)
        seen_pairs: set[frozenset[tuple[str, str]]] = set()
        for row in validated.itertuples(index=True):
            camper_1 = (str(row.cabin_1), str(row.camper_1))
            camper_2 = (str(row.cabin_2), str(row.camper_2))
            if camper_1 == camper_2:
                errors.append(f"Row {row.Index}: camper {camper_1} cannot have a relationship with itself.")
                continue
            pair = frozenset({camper_1, camper_2})
            if pair in seen_pairs:
                errors.append(f"Row {row.Index}: duplicate pair {camper_1} & {camper_2} (order does not matter).")
                continue
            seen_pairs.add(pair)

            unknown = [c for c in (camper_1, camper_2) if c not in known_campers]
            if unknown:
                named = " and ".join(str(c) for c in unknown)
                errors.append(f"Row {row.Index}: {named} is not a known camper.")
                continue

            if row.relationship == "besties":
                shared = prefs_by_camper[camper_1] & prefs_by_camper[camper_2]
                if len(shared) < BESTIES_MIN_SHARED_SEATRADES:
                    errors.append(
                        f"Row {row.Index}: besties pair {camper_1} & {camper_2} share fewer than "
                        f"{BESTIES_MIN_SHARED_SEATRADES} preferred seatrades — no identical schedule is possible."
                    )
            elif row.relationship == "friends":
                shared = prefs_by_camper[camper_1] & prefs_by_camper[camper_2]
                if len(shared) < FRIENDS_MIN_SHARED_SEATRADES:
                    errors.append(
                        f"Row {row.Index}: friends pair {camper_1} & {camper_2} share fewer than "
                        f"{FRIENDS_MIN_SHARED_SEATRADES} preferred seatrades — no shared session is possible."
                    )

    if errors:
        raise ValidationError(errors)

    return validated  # type: ignore[return-value]


def join_and_validate(
    identity_df: pd.DataFrame,
    preferences_df: pd.DataFrame,
    seatrade_df: pd.DataFrame,
    relationships_df: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame | None]:
    """Validate cross-references and join 3 DataFrames into 2 (+ optional relationships).

    Takes camper identity, camper preferences, seatrade config, and optionally
    camper relationships DataFrames. Validates that camper names match between
    identity and preferences, that all seatrade names in preferences exist in the
    seatrade config, and (when provided) that relationships reference known campers
    and are feasible.

    Returns (joined_campers, seatrade_setup, validated_relationships) where
    joined_campers has columns cabin, camper, gender, seatrade_1..4 and
    validated_relationships is None when no relationships are given (absent or empty).
    """
    errors: list[str] = []

    identity_validated: pd.DataFrame | None = None
    preferences_validated: pd.DataFrame | None = None
    seatrade_validated: pd.DataFrame | None = None

    try:
        identity_validated = validate_schema(CamperIdentity, identity_df, "Camper Identity")
    except ValidationError as e:
        errors.extend(e.errors)

    try:
        preferences_validated = validate_schema(CamperPreferences, preferences_df, "Camper Preferences")
    except ValidationError as e:
        errors.extend(e.errors)

    try:
        seatrade_validated = validate_schema(SeatradesConfig, seatrade_df, "Seatrade Setup")
    except ValidationError as e:
        errors.extend(e.errors)

    # Cross-reference checks only if all schemas passed
    if not errors:
        assert identity_validated is not None
        assert preferences_validated is not None
        assert seatrade_validated is not None

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
        all_pref_seatrades: set[str] = set()
        for col in PREF_COLS:
            all_pref_seatrades.update(preferences_validated[col])
        invalid_seatrades = all_pref_seatrades - available_seatrades
        if invalid_seatrades:
            invalid = ", ".join(sorted(invalid_seatrades))
            errors.append(f"Seatrades in preferences but not in seatrade config: {invalid}")

    # Relationships are validated against the joined campers, but only once the
    # identity/preferences data is internally consistent (the join is meaningful).
    joined: pd.DataFrame | None = None
    validated_relationships: pd.DataFrame | None = None
    if not errors:
        joined = identity_validated.merge(preferences_validated, on="camper")  # type: ignore[union-attr, arg-type]
        if relationships_df is not None and not relationships_df.empty:
            try:
                validated_relationships = validate_relationships(relationships_df, joined, "Camper Relationships")
            except ValidationError as e:
                errors.extend(e.errors)

    if errors:
        raise ValidationError(errors)

    return joined, seatrade_validated, validated_relationships  # type: ignore[return-value]
