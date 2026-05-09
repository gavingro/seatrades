# PRD: Service Layer Refactor

## Problem Statement

The seatrades optimizer and its UI are tangled together. The `Seatrades` class is a 470-line monolith that holds domain data, builds the MILP, solves it, and wrangles results. Config dataclasses, simulation generators, and validation logic live in Streamlit tab files. The `AssignmentsTab` manages threading, log parsing, and result rendering inline. This coupling makes the optimizer untestable in isolation, impossible to reuse outside Streamlit, and hard to reason about.

## Solution

Extract the `seatrades/` package into a clean service layer with proper module boundaries. Each module has a single responsibility and a simple, testable interface. The UI becomes a thin presentation layer that calls service functions and displays results. The refactor splits the monolith, relocates misplaced code, and defines clear data contracts — without adding new features.

## User Stories

### Service Layer Interface
1. As a developer, I want `solver.run(problem, config)` to return a single `AssignmentSolution` so that the UI calls one function and gets everything it needs.
2. As a developer, I want `SchedulingProblem` to hold domain data separate from optimization config so that I can rebuild the MILP with different weights against the same campers and seatrades.
3. As a developer, I want `SolverStatus` to live inside `AssignmentSolution` so that I can pass around one object that contains both the result and the outcome state.
4. As a developer, I want `SolverStatus.state` to be a `SolverState` enum (optimal/infeasible/error) so that consumers handle outcomes explicitly.
5. As a developer, I want `SolverStatus.gap` to report the optimality gap so that I know how close the solution is to optimal.
6. As a developer, I want `SchedulingProblem.build(config)` to be a separate step from construction so that I can inspect the problem before solving and rebuild with different configs.

### Data Pipeline
7. As a camp administrator uploading data, I want to provide camper identity, camper preferences, and seatrade setup as three separate DataFrames so that I don't have to join them myself.
8. As a developer, I want `preferences.py` to validate and join the three DataFrames into two so that `SchedulingProblem` receives clean, validated data.
9. As a developer, I want cross-reference validation to check that camper names match between identity and preference sources and that seatrade names in preferences exist in the seatrade setup.
10. As a developer, I want simulation data generation to produce the same three DataFrames as real uploads so that simulated data goes through the same validation pipeline.

### Module Extraction
11. As a developer, I want config dataclasses in `seatrades/config.py` so that they're reusable without importing Streamlit tab files.
12. As a developer, I want simulation generators in `seatrades/simulation.py` so that domain logic is separate from the presentation layer.
13. As a developer, I want visualization in `seatrades/visualization.py` so that chart specs are reusable in notebooks, APIs, or other frontends without Streamlit.
14. As a developer, I want wrangling functions to be free functions taking `AssignmentSolution` so that results processing doesn't require the problem builder.
15. As a developer, I want `results.py` to contain only the `AssignmentSolution` dataclass, wrangling functions, and export views — no chart logic.

### Testing
16. As a developer, I want to test `SchedulingProblem` construction and building independently from solving so that I can verify constraint setup without running the optimizer.
17. As a developer, I want to test `solver.run()` as an integration point that takes a built problem and returns an `AssignmentSolution` so that I can verify the full pipeline.
18. As a developer, I want to test `AssignmentSolution` wrangling and export separately from the optimizer so that I can verify data transformations with fixture data.

## Implementation Decisions

### Module Structure
- `seatrades/problem.py` — `SchedulingProblem` class. Holds parsed domain state. `.build(config)` creates the PuLP model with variables, constraints, and objective. Does NOT solve. Config passed at build time allows rebuilding with different weights/limits against same domain data.
- `seatrades/solver.py` — `solver.run(problem, config) -> AssignmentSolution`. Calls `problem.build(config)` internally, solves, wrangles results, returns self-contained `AssignmentSolution`. Manages solver thread and CBC log reading for progress monitoring.
- `seatrades/results.py` — `AssignmentSolution` dataclass (holds assignments DataFrame, SolverStatus with SolverState enum and optimality gap, plus domain data needed for wrangling). Free functions: `wrangle_assignments_to_longform`, `wrangle_assignments_to_wideform`, `prepare_seatrade_leaders`, and export view methods. All functions take `AssignmentSolution`, not the problem.
- `seatrades/visualization.py` — Build `alt.Chart` specs from `AssignmentSolution`. No Streamlit dependency. The UI renders via `st.altair_chart()`.
- `seatrades/preferences.py` — Pandera schemas, cross-reference validation, and the 3→2 DataFrame join (camper identity + preferences → joined campers). Dynamic Pandera subclass generation takes `available_seatrades` as a parameter.
- `seatrades/simulation.py` — Generate mock data as three separate DataFrames: camper identity, camper preferences, and seatrade setup. Goes through same validation pipeline as real uploads.
- `seatrades/config.py` — `OptimizationConfig`, `CamperSimulationConfig`, `SeatradeSimulationConfig`. Has PuLP dependency for solver configuration.

### Data Contracts
- `SchedulingProblem.__init__` receives two DataFrames: joined campers (identity + preferences merged) and seatrade setup (name, min, max). Fleets are hardcoded domain knowledge (`["1a", "1b", "2a", "2b"]`), not a parameter. Block availability is always all blocks.
- `SchedulingProblem.build(config)` receives `OptimizationConfig`. Returns nothing — builds the internal PuLP model.
- `solver.run(problem, config)` returns a single `AssignmentSolution`. Internally calls `problem.build(config)` if not already built.
- `AssignmentSolution` is self-contained and portable. It holds the assignments DataFrame, `SolverStatus`, and domain data (campers list, seatrades list, preferences) needed by wrangling and visualization functions. No reference to the PuLP model or `SchedulingProblem`.

### SolverStatus
- `SolverState` enum: `OPTIMAL`, `INFEASIBLE`, `ERROR`.
- `SolverStatus` dataclass: `state: SolverState`, `gap: float` (optimality gap), `message: str` (human-readable detail, e.g. infeasibility info).
- `SolverStatus` is a field inside `AssignmentSolution`, not a separate return.
- Progress monitoring (percent-complete during a running solve) stays in the UI layer via `@st.fragment` log polling. Not in `SolverStatus`.

### Solver Monitoring
- Service layer owns the solver thread and CBC log reading.
- UI polls `AssignmentSolution.status` via `@st.fragment(run_every=...)`.
- PuLP/CBC doesn't support mid-solve callbacks — log file is the only progress signal.

### Infeasibility
- Report only: `SolverStatus` with `state=INFEASIBLE` and a descriptive message.
- Structured constraint-conflict diagnostics are future work.

## Testing Decisions

### What Makes a Good Test
Tests verify external behavior, not implementation details. A good test for `SchedulingProblem` checks that the right constraints are generated for given input. A good test for `solver.run()` checks that a solvable problem produces an `AssignmentSolution` with `state=OPTIMAL`. A good test for wrangling functions checks that `AssignmentSolution` data transforms correctly.

### Test Structure (per ADR 0002)
- One test file per Python module: `test_problem.py`, `test_solver.py`, `test_results.py`, `test_visualization.py`, `test_preferences.py`, `test_simulation.py`, `test_config.py`.
- Tests mirror code directory structure within `tests/test_seatrades/`.
- Fixtures start in the same test file. Extract to `conftest.py` when 3+ files share the same fixtures.
- Fixtures start as raw DataFrames, refactored to factories if they grow unwieldy.

### Modules to Test
- `problem.py` — Test that `SchedulingProblem.__init__` parses domain data correctly. Test that `.build(config)` generates expected constraints and variables for different configs.
- `solver.py` — Integration test: `solver.run(problem, config)` returns `AssignmentSolution` with expected state. Test infeasible case returns `INFEASIBLE` status.
- `results.py` — Test wrangling functions with fixture `AssignmentSolution` data. Test export views produce correct DataFrames.
- `visualization.py` — Test that chart specs are produced from `AssignmentSolution` without Streamlit dependency.
- `preferences.py` — Test validation catches name mismatches and cross-reference errors. Test 3→2 join produces correct output.
- `simulation.py` — Test that simulation produces three DataFrames with expected columns and valid data.
- `config.py` — Test default config values. Test PuLP solver configuration.

### Prior Art
- `tests/test_seatrades/test_seatrades.py` — existing monolith tests will be replaced by module-specific tests.
- `tests/test_seatrades/test_results.py` — existing results tests will be extended for new wrangling interface.
- `tests/test_seatrades/test_preferences.py` — existing preferences tests will be extended for 3→2 join and cross-reference validation.

## Out of Scope

- Rename `seatrades_app/` to `app/` — separate PR following Streamlit convention.
- Session state key centralization in `app/state.py` — low priority, later work.
- Per-seatrade block availability — always all blocks for Keats Camp, not a parameter.
- Structured infeasibility diagnostics — report infeasibility as message only; constraint-conflict analysis is future work.
- UI tab rework (separate camper identity from camper preferences form) — future enhancement.
- `@st.fragment` solver monitoring UI rewrite — depends on this refactor but is a separate concern.
- Any new features, optimizations, or algorithm changes to the MILP solver.

## Further Notes

### Implementation Order
The refactor should be done in vertical slices that keep the app working at each step, rather than big-bang module creation:
1. Extract config dataclasses to `seatrades/config.py` (mechanical, no logic changes).
2. Extract simulation to `seatrades/simulation.py` (mechanical, move functions).
3. Add 3→2 join and cross-reference validation to `seatrades/preferences.py`.
4. Create `AssignmentSolution` and `SolverStatus` dataclasses in `results.py`.
5. Create `SchedulingProblem` in `problem.py` — extract domain state from `Seatrades.__init__` and constraint building from `Seatrades.assign()`.
6. Create `solver.run()` in `solver.py` — wire up build, solve, and result creation.
7. Extract wrangling functions from `Seatrades` class to free functions in `results.py`.
8. Extract visualization from `results.py` to `visualization.py`.
9. Update `AssignmentsTab` to call service layer instead of `Seatrades` directly.
10. Remove `Seatrades` class.

### Preserved Decisions
This PRD respects decisions documented in:
- ADR 0001: MILP optimization approach (unchanged)
- ADR 0002: Test structure conventions (applied to new modules)
- ADR 0003: Service layer architecture (implemented by this PRD)
- ADR 0004: Solver monitoring strategy (unchanged, service layer enables it)
- ADR 0005: Git branching strategy (follow for implementation branches)

### Key Design Principle
`AssignmentSolution` is self-contained and portable. It holds everything needed for wrangling, visualization, and export — no reference back to the `SchedulingProblem` or the PuLP model. This makes it usable in notebooks, APIs, and other frontends without dragging the solver along.
