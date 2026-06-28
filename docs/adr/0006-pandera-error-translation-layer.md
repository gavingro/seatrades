# ADR 0006: Pandera error translation lives in the service layer

## Status: proposed

## Context

When users upload malformed CSVs, pandera raises `SchemaError` with technical messages like "non-nullable series 'camper' contains null values" or check names like `campers_must_choose_4_unique_seatrades`. These messages are meaningless to non-technical scheduling captains.

We need to translate pandera errors into human-readable messages. The question is where the translation logic lives.

## Considered Options

1. **Service layer** (`seatrades/preferences.py`) — A `validate_schema` function wraps pandera validation with `lazy=True`, inspects the `SchemaErrors.failure_cases` DataFrame, and translates each check type into a plain-language message. Raises the existing `ValidationError`. Both UI tabs and `join_and_validate()` call this function.

2. **UI layer** (`app/tabs/`) — Each tab catches `SchemaError`/`SchemaErrors` and translates inline. `join_and_validate()` stays unchanged.

3. **Separate module** (`seatrades/errors.py`) — Error translation in a dedicated module, imported by both `preferences.py` and the tabs.

## Decision

**Option 1: Service layer.**

Rationale:

- Error translation understands schema semantics (what `not_nullable` means, what `campers_must_choose_4_unique_seatrades` checks). That's domain knowledge, not presentation logic.
- `join_and_validate()` already owns validation — it validates 3 schemas, then runs cross-reference checks. Translating schema errors into the same `ValidationError` format lets it collect all errors (schema + cross-reference) and raise once.
- UI tabs already handle `ValidationError` uniformly. Adding a second error type or duplicating translation logic across tabs would be inconsistent.
- A separate module (`errors.py`) would be one function — not enough surface area to justify its own file. If it grows later, we extract then.

## Consequences

- Pandera becomes an implementation detail of validation. Callers (UI, simulation, future API) see `ValidationError` with human-readable messages, never raw `SchemaError`.
- `join_and_validate()` collects schema errors and cross-reference errors together, but skips cross-reference checks when schemas fail (can't safely join DataFrames with missing columns or null keys).
- The UI tabs become thinner — they call `validate_schema` and handle `ValidationError`, no pandera imports needed.
- `lazy=True` validation is used so all schema errors are collected at once, not short-circuited on the first failure.
