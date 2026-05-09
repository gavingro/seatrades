# SeaTrades Domain

Keats Camp seatrade scheduling optimization.

## Core Entities

### Camper

A child attending camp. Has:

- **Name** - Unique identifier
- **Cabin** - Group of ~12 campers staying together
- **Age** - Camp year (determines cabin assignment)
- **Gender** - Used for fleet balance constraints
- **Preferences** - Ranked list of 4 seatrades (required)

Camper identity (name, cabin, gender) and camper preferences (name, seatrade rankings) come from different sources in the real world — registration data vs. preference forms. The service layer joins them.

### Cabin

A group of campers staying together. Properties:

- **Name** - e.g., "Spindrift", "Tillikum"
- **Gender** - All-boys, all-girls, or mixed (rare)
- **Fleet assignment** - Which fleet (1 or 2) the cabin attends together

### Seatrade

An activity offered at camp. Properties:

- **Name** - e.g., "Sailing", "Kayaking", "Rowing"
- **Capacity** - Min/max campers per session
- **Blocks available** - All 4 blocks always (hardcoded domain knowledge, not a parameter).

### Block

A time slot within a fleet. There are 4 blocks per day:

- `1a` - Fleet 1, first session
- `1b` - Fleet 1, second session
- `2a` - Fleet 2, first session
- `2b` - Fleet 2, second session

Blocks and fleets are hardcoded domain knowledge — not parameters to `SchedulingProblem`.

### Fleet

A group of 2 blocks (morning or afternoon):

- **Fleet 1** - Blocks 1a + 1b
- **Fleet 2** - Blocks 2a + 2b

Each cabin is assigned to one fleet for the week.

### Assignment

A mapping of a camper to a seatrade in a specific block. Each camper gets exactly 2 assignments per week (one per block).

### AssignmentSolution

Self-contained and portable — no reference to the MILP model. Fields: assignments DataFrame, SolverStatus, plus domain data (campers, seatrades, preferences) needed by wrangling and visualization. Wrangling functions operate on this, not on the SchedulingProblem.

### SolverStatus

A field inside `AssignmentSolution` (not a separate return). Tracks the outcome of a solve. Fields: state (SolverState enum: optimal/infeasible/error), gap (optimality gap as a float), message (human-readable, e.g. infeasibility detail). Progress monitoring (percent-complete during a running solve) stays in the UI layer via `@st.fragment` log polling — not in SolverStatus.

### Assignment Export

The app exports assignments in 3 formats for different audiences:

| Format | Sort Order | Use Case |
|--------|------------|----------|
| Captain's Book | Camper (upload order) | Internal logistics and bookkeeping |
| Cabin Leaders | Cabin → Block → Camper | Distribute to cabin leaders for their campers |
| Seatrade Leaders | Block → Seatrade → Cabin → Camper | Day-of attendance at each seatrade session |

Each export includes columns: camper, seatrade, assignment (0/1), preference (1-4), cabin, block.

## Data Flow

```mermaid
flowchart LR
    subgraph UI [app/ — Presentation Layer]
        Upload[File Upload / Simulation Forms]
        Fragment["@st.fragment polling SolverStatus"]
        Display[Render AssignmentSolution + Charts]
    end

    subgraph Service [seatrades/ — Service Layer]
        Sim[simulation.py: Generate Mock Data]
        Val[preferences.py: Validate + Join 3→2]
        Prob[SchedulingProblem: Build MILP]
        Solve[solver.py: Solve + SolverStatus]
        Result[results.py: AssignmentSolution]
    end

    Upload --> Sim
    Sim -->|3 DataFrames| Val
    Val -->|2 DataFrames| Prob
    Solve -->|AssignmentSolution| Fragment
    Result --> Display
```

### Pipeline (happy path)

```
1. User uploads CSVs or uses simulation → app/ calls seatrades.simulation (produces 3 DataFrames: camper identity, camper preferences, seatrade setup)
2. preferences.py validates (names match, seatrades exist in setup) and joins 3 DataFrames → 2 (joined campers, seatrade setup)
3. SchedulingProblem(joined_campers, seatrade_setup) → holds parsed domain state
4. solver.run(problem, config) → calls problem.build(config) internally, returns AssignmentSolution (with SolverStatus inside)
5. UI reads AssignmentSolution.status via @st.fragment, displays assignments
6. AssignmentSolution.export(view="camper"|"cabin"|"seatrade") → formatted DataFrame
```

## Optimization Problem

The scheduler solves a mixed-integer linear programming problem with these constraints:

1. **One seatrade per block** - Each camper assigned to exactly 1 seatrade in each block
2. **No duplicates** - Camper cannot take same seatrade in both blocks
3. **Capacity limits** - Seatrade capacity enforced (min/max per session)
4. **Preference only** - Campers only assigned seatrades they ranked
5. **Top-2 guarantee** - Campers guaranteed one of their top 2 choices
6. **Cabin max per seatrade** - Max k campers from same cabin in one seatrade (by default k=4)
7. **Fleet balance** - Cabins split evenly between fleets
8. **Gender balance** - Boys/girls cabins split evenly between fleets

## Module Boundaries

| Package | Responsibility |
|---------|---------------|
| `seatrades/` | Service layer — domain logic, optimization, simulation, results |
| `app/` | Presentation layer — Streamlit UI only, no business logic (rename from `seatrades_app/`) |

### app/ modules

| Module | Owns |
|--------|------|
| `app.py` | Entry point, tab layout |
| `state.py` | Constants for all session state keys (low priority, replace scattered strings) |
| `tabs/` | Thin Streamlit presentation — widgets, forms, file uploads. Call service functions, display results. |

### seatrades/ modules

| Module | Owns |
|--------|------|
| `problem.py` | `SchedulingProblem` — holds parsed domain state, builds MILP (variables, constraints, objective) when `.build(config)` is called. Does NOT solve. Config (weights, limits, solver settings) is passed at build time, not init — allows rebuilding with different configs against the same domain data. |
| `solver.py` | `solver.run(problem, config) -> AssignmentSolution` — orchestrates build + solve + wrangle. Calls `problem.build(config)` internally. Manages solver thread and CBC log reading. |
| `results.py` | `AssignmentSolution` dataclass + free functions for wrangling (`wrangle_assignments_to_longform`, `wrangle_assignments_to_wideform`, `prepare_seatrade_leaders`) and export views. Functions take `AssignmentSolution`, not the problem. |
| `visualization.py` | Build `alt.Chart` specs from `AssignmentSolution`. No Streamlit dependency — renders in any Altair-capable frontend. |
| `preferences.py` | Pandera schemas + cross-reference validation (camper names match between sources, seatrade names in prefs exist in setup) + 3→2 DataFrame join (camper identity + camper preferences → joined campers) |
| `simulation.py` | Generate mock data as 3 separate DataFrames (camper identity, camper preferences, seatrade setup) — goes through same validation pipeline as real uploads |
| `config.py` | `OptimizationConfig`, `CamperSimulationConfig`, `SeatradeSimulationConfig`. Has PuLP dependency — `OptimizationConfig` owns its solver object directly. |

## Architecture Grilling — Decisions Log

Resolved during grilling session 2026-05-05. Open questions marked with [OPEN].

1. **`Seatrades` class → split into SchedulingProblem + solver + results.** Problem builder owns variables/constraints/objective. Solving is separate. Wrangling is separate. `SchedulingProblem` is stateful (holds parsed domain state) because the wrangler needs the same state — avoids re-parsing or building a second context object. Module is `problem.py` (not `scheduling_problem.py`). Config passed at `.build(config)` time, not init — allows rebuilding with different configs against same domain data.

2. **Solver produces `AssignmentSolution`, not raw pulp object.** Clean boundary: problem goes in, solution comes out. No leaking PuLP internals. `AssignmentSolution` is self-contained and portable — holds assignments DataFrame, SolverStatus, and domain data needed by wrangling/visualization. `SolverStatus` is a field inside `AssignmentSolution` (not a separate return): state is a `SolverState` enum (optimal/infeasible/error), `gap` is the optimality gap, `message` for human-readable detail. Progress monitoring stays in UI layer only.

3. **Service function `solver.run(problem, config) -> AssignmentSolution`.** UI calls one function. `solver.run` calls `problem.build(config)` internally. No solver orchestration in the presentation layer.

4. **Solver monitoring splits: service layer runs solver + reads CBC log, UI polls `AssignmentSolution.status` via `@st.fragment`.** PuLP/CBC doesn't support mid-solve callbacks — log file is the only progress signal. `@st.fragment(run_every=...)` replaces manual `while`+`sleep` polling. Progress percent stays in UI polling layer, not in SolverStatus.

5. **Simulation data generation moves to service layer** (`seatrades/simulation.py`). It's domain logic, not UI. Simulation produces 3 separate DataFrames (camper identity, camper preferences, seatrade setup) — goes through same validation pipeline as real uploads.

6. **Cross-reference validation and 3→2 join moves to service layer** (`seatrades/preferences.py`). Camper identity and preferences come from different sources (registration data vs. preference forms) — the user shouldn't have to join them. `preferences.py` validates (names match, seatrades exist in setup) and joins 3 DataFrames into 2 (joined campers, seatrade setup) before passing to `SchedulingProblem`. Dynamic Pandera subclass generation for checking camper prefs against available seatrades becomes a function that takes `available_seatrades` as a parameter.

7. **Config dataclasses move to service layer** (`seatrades/config.py`). `OptimizationConfig`, `CamperSimulationConfig`, `SeatradeSimulationConfig` don't belong in UI files. `OptimizationConfig` has PuLP dependency — it owns its solver object directly, since PuLP requires solver params at instantiation time and the config IS for the solver.

8. **Infeasibility: report only for now (A), diagnose later (B).** `SolverStatus` reports error state + message. Structured constraint-conflict diagnostics are future work.

9. **Session state keys: centralize in `app/state.py`** (low priority). Replaces scattered string literals for IDE support and typo protection.

10. **Rename `seatrades_app/` → `app/`**. Follows Streamlit convention, avoids naming confusion with `seatrades/` service package.

11. **Altair chart → separate `seatrades/visualization.py` module.** Chart is neither presentation layer nor data model — it's a visualization spec that consumes `AssignmentSolution`. Stays in service layer (no Streamlit dep) so it's reusable outside the app (API, notebooks, other frontends). `results.py` stays clean: data model + export only. `app/` renders via `st.altair_chart()`.

12. **Fleets and blocks are hardcoded domain knowledge.** Keats Camp always has 2 fleets with 2 blocks each (1a, 1b, 2a, 2b). Not parameters to `SchedulingProblem` — derived from the domain. Block availability for seatrades is always "all blocks."

13. **SchedulingProblem receives 2 DataFrames, not 6 params.** After `preferences.py` joins the 3 source DataFrames, the problem builder gets `joined_campers` (identity + preferences merged) and `seatrade_setup` (name, min, max).

## Tech Stack

- **UI:** Streamlit
- **Optimizer:** PuLP (mixed-integer linear programming)
- **Validation:** Pandera (DataFrame schemas)
- **Deployment:** Streamlit Cloud

## Git Workflow

Three branch prefixes: `feature/` (PRD-level work), `dev/` (small-scope work — sources from parent `feature/` when supporting a PRD, or `main` when standalone), `fix/` (bug fix off main). All merges are squash-merge via PR. `feature/` branches are created when the PRD issue opens, as landing zones. Any merge targeting `main` requires approval. See [ADR 0005](docs/adr/0005-git-branching-strategy.md).