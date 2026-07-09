# Decompose the conflated `preference` column into orthogonal facts

The longform assignments frame (`wrangle_assignments_to_longform`) once carried a single
`preference` column that conflated three unrelated things. Issue #85 decomposes it into
orthogonal `assignment` + `preference_rank` facts, plus a derived `assigned_to_block` schedule fact.

**Status: accepted**

## Context

The old `preference` column overloaded one integer with three meanings:

- `0` — the camper was **not assigned** this cell (regardless of what they ranked).
- `1–4` — the camper was **assigned** this cell **and** had ranked it at that position.
- `999` (`UNMATCHED_PREFERENCE`) — the camper was **assigned** this cell but never ranked it.

Because unassigned was forced to `0`, the rank a camper *gave* a seatrade they *didn't get* was
unrecoverable. That hid near-misses — most visibly, a group who submitted the same preferences so
they could be together but got split by the solver: nothing on the master grid showed the group was
*nearly* kept whole (issue #85).

## Decision

Replace the conflated column with orthogonal facts:

- **`assignment`** (0/1) — did this camper get *this* seatrade cell? Unchanged.
- **`preference_rank`** — the rank the camper gave this seatrade (`1–4`), else `999`
  (`UNMATCHED_PREFERENCE`) for unranked. Populated on **every** cell regardless of assignment or
  block — a pure camper↔seatrade fact. Stays a plain `int` reusing the existing `999` sentinel (no
  `pd.NA`).
- **`assigned_to_block`** (bool) — does this camper have *any* real seatrade in this block (vs Fleet
  Time)? Derived by grouping `assignment` over `(camper_id, block)`. A schedule fact about the whole
  block, deliberately distinct from `assignment`, which is about one cell.

The old `preference` column is **removed entirely** — keeping it alongside the new columns would
reintroduce the very conflation this decision removes.

"Where to paint faint ink" (the ghost-number display rule) is **not** a data-layer concern. The
data layer carries only domain facts; the chart layer (`enrich_assignments_for_display` in
`visualization.py`) derives the display columns (`satisfaction`, `rank_text`, `ghost_text`) from
those facts as a pure, unit-testable helper.

## Consequences

- The master camper grid can draw a camper's rank for seatrades they were *not* assigned, faintly,
  in the blocks they attend — surfacing split same-preference groups. The ghost rule is
  `preference_rank ∈ 1..4 AND assignment == 0 AND assigned_to_block`.
- The assigned layer's Altair filter flips from `preference > 0` to `assignment == 1`. Required:
  now that unassigned cells carry real ranks, `preference > 0` would mis-colour a ghost cell as a
  real placement. Assigned cells render identically.
- Callers that read the old column moved to `preference_rank` (e.g. `scoring._camper_cprs`, which
  only ever looks at assigned rows, where `preference_rank` equals the old `preference`).
- **Future refactors must not re-collapse these columns "for simplicity."** The orthogonality is
  the point — the split is what makes the "didn't get" rank recoverable and the Fleet-Time-vs-
  seatrade distinction testable at a clear seam.
