# Service layer between UI and optimizer

The application splits into two packages: `seatrades/` (service layer — domain logic, optimization, simulation, results) and `app/` (presentation layer — Streamlit UI only). The UI calls service functions and never contains business logic, solver orchestration, or data generation.

**Status: accepted**

## Considered Options

1. **Service layer** — A thin service function (`solver.run(problem, config) -> AssignmentSolution`) sits between the UI and the optimizer. The UI calls one function; all orchestration happens in the service layer. `solver.run` calls `problem.build(config)` internally. `SolverStatus` is a field inside `AssignmentSolution`, not a separate return — the solution is self-contained and portable.

2. **Ad-hoc** — The UI constructs `SchedulingProblem`, calls `.solve()` on the problem object, passes raw output to a wrangler, gets back results. No service layer.

We chose option 1 because the solver orchestration (build → solve → wrangle) is a workflow, not a UI concern. A service function gives one place to test the full pipeline without Streamlit and one clean seam for the UI to call. Option 2 keeps solver logic tangled in `assignments_tab.py`, which already has 300 lines mixing thread management, log parsing, and progress display.

Config is passed at `build(config)` time, not at `SchedulingProblem.__init__` time. This allows rebuilding the MILP with different weights, limits, or solver settings against the same domain data without re-constructing the problem. The trade-off is that the problem object is not ready to solve until `build()` is called, but `solver.run()` handles this internally so callers don't need to think about it.

## Consequences

- Simulation data generation, validation, and config dataclasses move out of tab files into `seatrades/simulation.py`, `seatrades/preferences.py`, and `seatrades/config.py`.
- Cross-tab coupling (`_clear_optimization_results` imported across tabs) disappears — state management moves to session state keys via `app/state.py`.
- The `Seatrades` class (426 lines, monolith) splits into `SchedulingProblem` (stateful problem builder in `problem.py`), `solver.py` (orchestration), and `results.py` (`AssignmentSolution` dataclass + free wrangling/export functions). Wrangling functions take `AssignmentSolution`, not the problem object — keeps results portable.
- `seatrades_app/` renames to `app/` following Streamlit convention.