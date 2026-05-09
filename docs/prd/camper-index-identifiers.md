# PRD: Replace Camper-Name Identifiers with Integer Indices in MILP Solver

## Problem Statement

Campers are currently identified by name inside the MILP solver. When two campers share a name, the `add_index_to_campername` function appends a `.{index}` suffix to disambiguate. This hack causes two bugs:

1. **Compounding suffix bug** — Re-solving the same data mutates the name column in-place, appending the suffix repeatedly. A camper named "Gavin" becomes "Gavin.3", then "Gavin.3.3", then "Gavin.3.3.3" across successive solves.
2. **Leaking mangled names** — The suffixed names appear in charts, exports, and all user-facing output, making them unreadable.

Even without name collisions, using names as internal identifiers is fragile. Names are display data, not identity data.

## Solution

Switch the MILP solver to use zero-indexed integer IDs (`camper_id`) as internal identifiers instead of camper names. Names are preserved for input and output, but never used as solver variable keys.

The composite key `(cabin, camper_name)` uniquely identifies a camper in all user-facing output. Sort order preserves the original upload position, not alphabetical order.

### Why integer indices, not names

Names are unstable identifiers — they can collide, and they carry no ordering information. Row indices are deterministic, collision-free, and preserve the user's intended order. The solver should operate on stable internal identifiers; names belong at the boundary.

### Why not merge this into the service layer refactor

The ADR-0003 refactor (#40) preserves current behavior. Switching to index-based identifiers changes the solver's variable scheme, which is an algorithm change. Mixing behavior changes into a structural refactor makes both harder to review and harder to roll back. This change must land after the refactor.

## User Stories

### Solver Identity

1. As the solver, I want to identify each camper by a stable zero-indexed integer, so that variable keys are deterministic and collision-free regardless of name duplicates.

2. As the solver, I want camper IDs generated automatically from the validated DataFrame row position during `SchedulingProblem.__init__`, so that no caller needs to provide or manage IDs.

### Output Correctness

3. As a camp director, I want all exports and charts to show clean camper names (no numeric suffixes), so that the output is readable and presentable.

4. As a camp director, I want assignments sorted in the same order as my uploaded roster, so that I can find campers where I expect them.

5. As a camp director, I want two campers with the same name to appear correctly in output (disambiguated by cabin), so that I can tell them apart without confusing IDs.

### Data Integrity

6. As the system, I want re-solving the same data to produce identical output, so that iterative workflow doesn't corrupt camper names.

7. As the system, I want the `add_index_to_campername` function removed, so that the name-mutation hack no longer exists in the codebase.

## Implementation Decisions

### ID Lifecycle

- `SchedulingProblem.__init__` — Ingests camper names from the validated DataFrame. Assigns `camper_id` as the zero-indexed row position. Builds an internal `camper_id → camper_name` mapping.
- `SchedulingProblem.build()` — All PuLP variable dicts keyed by `camper_id` (integer). Constraint names use `camper_id`. No string names in the MILP model.
- `solver.run()` — After solving, translates all `camper_id` references back to `camper_name` when constructing `AssignmentSolution`.
- `AssignmentSolution` — Holds `camper_id` internally as an implementation detail. No public method, property, or export exposes it. All user-facing wrangling and export methods use `(cabin, camper_name)` as the composite key.

### Composite Key

- The unique identifier for a camper in user-facing output is `(cabin, camper_name)`. This handles name collisions naturally — two "Gavins" in different cabins are distinct.
- Sort order preserves original upload position (row index), not alphabetical order.

### Deleted Code

- `add_index_to_campername` in `preferences.py` is deleted. It was the source of both the compounding suffix bug and the name-mutation hack.
- The `Seatrades.__init__` call to `add_index_to_campername` is removed. In the post-refactor `SchedulingProblem.__init__`, names are never mutated.

### Affected Modules

- `SchedulingProblem` (`problem.py`) — ID assignment, variable/constraint construction, objective function.
- `solver.py` — Result construction: translate `camper_id → camper_name` when building `AssignmentSolution`.
- `AssignmentSolution` (`results.py`) — Internal `camper_id` column; all public methods emit `camper_name`.
- Wrangling functions (`results.py`) — Use `(cabin, camper_name)` composite key; sort by upload order.
- Visualization (`visualization.py`) — No change to display (uses `camper_name`).
- Preferences (`preferences.py`) — Delete `add_index_to_campername`.
- Simulation (`simulation.py`) — No change; simulation generates names, IDs assigned during problem construction.

## Testing Decisions

### What Makes a Good Test

Tests verify external behavior, not implementation details. The camper ID scheme is an implementation detail — tests should verify that names come out clean, not that IDs are integers. However, one test may verify that the solver uses IDs internally by checking that name collisions don't produce errors or mangled output.

### Test Cases

- Re-solving the same data produces clean camper names with no compounding suffixes.
- Two campers with the same name (different cabins) are handled correctly via the `(cabin, camper_name)` composite key.
- Wrangling and export output contains `camper_name`, never `camper_id`.
- Wideform output preserves original upload sort order.
- `SchedulingProblem` builds and solves successfully with duplicate camper names in different cabins.

### Modules to Test

- `problem.py` — Test that `SchedulingProblem.__init__` assigns IDs correctly; test that `.build()` produces valid constraints for duplicate-name campers.
- `results.py` — Test that wrangling functions output `camper_name` and sort by upload order.
- Integration — Test that `solver.run()` produces clean names end-to-end, including after re-solving.

## Out of Scope

- Changing the MILP algorithm or adding new constraints — this is purely an identifier scheme change.
- Adding structured infeasibility diagnostics — future work per ADR-0003.
- UI tab rework (separating camper identity from preferences form) — separate enhancement.
- Making `camper_id` user-visible or configurable — IDs are internal-only.
- Changing how cabin or seatrade identifiers work — only camper identification changes.

## Further Notes

### Prerequisite

This change must land **after** the ADR-0003 service layer refactor (#40). The refactor preserves current behavior; this change introduces new behavior.

### Compounding Suffix Bug

The compounding suffix bug (`Gavin.3.3.3`) is not a separate deliverable — it is automatically fixed by removing `add_index_to_campername` and switching to integer IDs. A regression test ensures it stays fixed.

### Preserved Decisions

- ADR-0003 service layer architecture remains unchanged.
- `AssignmentSolution` remains self-contained and portable per ADR-0003.
- Config is still passed at `.build(config)` time per ADR-0003.