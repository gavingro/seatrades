# PRD: Camper Relationships (Friends/Besties/Frenemies)

## Problem

Campers at Keats Camp have social relationships that should influence seatrade assignments. Currently the solver has no mechanism to enforce social constraints — campers are assigned based on preferences, capacity, and cabin/fleet balance alone. Staff need a way to express:

- **Friends**: campers who should share at least one session together
- **Besties**: campers who should have identical schedules
- **Frenemies**: campers who should never be in the same session

These are hard constraints — the solver must satisfy them or report infeasibility.

## Definitions

A **session** is a specific seatrade within a specific fleet and block (e.g., "Sailing in 1a"). Since fleets and blocks are solver-assigned, session identity is a derived concept — the constraint formulations operate on the solver's assignment variables.

| Relationship | Constraint |
|-------------|-----------|
| Friends | Pair shares ≥1 session (same seatrade, same fleet+block) |
| Besties | Pair shares both sessions (identical schedule) |
| Frenemies | Pair shares zero sessions (no seatrade overlap in any block) |

All relationships are symmetric — the order of campers in a pair does not matter.

## Data Model

**Input DataFrame**: `CamperRelationships`

| Column | Type | Description |
|--------|------|-------------|
| `cabin_1` | `str` | Cabin of first camper |
| `camper_1` | `str` | Name of first camper |
| `cabin_2` | `str` | Cabin of second camper |
| `camper_2` | `str` | Name of second camper |
| `relationship` | `str` | One of: `friends`, `besties`, `frenemies` |

Uses `(cabin, camper)` composite keys to match the existing domain model. Column names align with existing `CamperIdentity` and `CamperPreferences` schemas.

The DataFrame is **optional** — when absent or empty, no relationship constraints are applied. Only explicitly listed pairs have constraints; all other pairs default to unconstrained.

## Validation

Schema validation via Pandera (`CamperRelationships` model) plus cross-reference checks:

### Schema checks

- All columns present and non-null
- `relationship` values are exactly `friends`, `besties`, or `frenemies`
- No self-pairs (`camper_1 == camper_2 AND cabin_1 == cabin_2`)

### Uniqueness checks

- No duplicate pairs regardless of order — `(Puffin, Alice, Puffin, Bob)` is the same as `(Puffin, Bob, Puffin, Alice)`. Both orderings in the same DataFrame is a validation error.

### Cross-reference checks (only if schema + uniqueness pass)

- Both `camper_1` in `(cabin_1, camper_1)` and `camper_2` in `(cabin_2, camper_2)` must exist in the camper identity data
- Checked after the existing `join_and_validate` identity/preferences join, so the reference set is the validated joined campers

Validation follows the same pattern as `preferences.py`: collect all errors, then raise `ValidationError` with the full list.

## Solver Integration

Relationships are passed to the solver as hard MILP constraints alongside existing preference, capacity, and balance constraints.

### Friends constraint

For each friends pair (c1, c2), at least one session must be shared:

```
sum_{session s} y[c1, c2, s] >= 1
```

Where `y[c1, c2, s]` is an auxiliary binary variable indicating both c1 and c2 are assigned to session s. Linearized via standard big-M or AND constraints.

### Besties constraint

For each besties pair (c1, c2), both assignments must match:

```
x[c1, s, b] = x[c2, s, b]  for each session (s, b) where both could be assigned
```

In practice: both campers get the same seatrade in the same fleet+block for both block 1 and block 2. Since fleet assignment is itself a solver variable, this implicitly forces both campers into the same fleet.

### Frenemies constraint

For each frenemies pair (c1, c2), no session is shared:

```
sum_{session s} y[c1, c2, s] = 0
```

Same auxiliary variable formulation as Friends, but equality to zero instead of ≥1.

## Proposed Changes

### 1. Add `CamperRelationships` Pandera model to `config.py`

Schema definition with columns: `cabin_1`, `camper_1`, `cabin_2`, `camper_2`, `relationship`.

### 2. Add relationship validation to `preferences.py`

- `validate_relationships(relationships_df, identity_df, label)` — schema validation + self-pair check + duplicate-pair check + cross-reference (both campers exist in identity)
- Extend `join_and_validate` to accept an optional `relationships_df` parameter and validate it alongside existing checks
- Return relationships as a third element: `(joined_campers, seatrade_setup, validated_relationships)`

### 3. Add MILP constraints for relationships to the solver

- In `seatrades.py` (current) or `problem.py` (post-refactor), accept relationship data and add Friends/Besties/Frenemies constraints
- Relationships are optional — when `None` or empty, no constraints are added and solver behavior is unchanged

### 4. Add "Friends" tab to Streamlit UI

- New tab between camper info and optimization config
- CSV upload for relationships DataFrame
- Uses `validate_schema` for error display (same pattern as other tabs)
- Passes validated relationships through to the solver pipeline

### 5. Files Changed

| File | Change |
|------|--------|
| `seatrades/config.py` | Add `CamperRelationships` Pandera model |
| `seatrades/preferences.py` | Add `validate_relationships`, extend `join_and_validate` signature |
| `seatrades/seatrades.py` | Accept relationships parameter, add MILP constraints |
| `seatrades/simulation.py` | Generate mock relationship data |
| `seatrades_app/tabs/friends_tab.py` | New tab: CSV upload + validation |
| `seatrades_app/app.py` | Register Friends tab |
| `tests/test_seatrades/test_preferences.py` | Tests for relationship validation |
| `tests/test_seatrades/test_seatrades.py` | Tests for relationship constraints |

## Out of Scope

- Diagnosing or reporting *why* a solver is infeasible (e.g., contradictory friend/frenemy chains). Out of scope for this PRD — will be addressed in future solver diagnostics work.
- Extensible relationship types. Only `friends`, `besties`, `frenemies` — adding new types requires solver changes and is not designed for extension.
- Soft/weighted relationships. All relationships are hard constraints.
- Editing relationships in the UI (beyond re-uploading CSV).
