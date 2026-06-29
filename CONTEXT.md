# SeaTrades Domain

Keats Camp seatrade scheduling optimization.

## Core Entities

### Camper

A child attending camp. Has:

- **Name** - Display name (not a unique identifier — two campers can share a name)
- **Cabin** - Group of ~12 campers staying together
- **Age** - Camp year (determines cabin assignment)
- **Gender** - Used for fleet balance constraints
- **Preferences** - Ranked list of 4 seatrades (required)
- **Composite key** - `(cabin, name)` uniquely identifies a camper

Internally, the solver identifies campers by a zero-indexed row ID (`camper_id`), never by name. The composite key `(cabin, name)` is used in all user-facing output. Names stay clean — no suffixes or mangling.

Camper identity (name, cabin, gender) and camper preferences (name, seatrade rankings) come from different sources in the real world — registration data vs. preference forms. The service layer joins them.

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

**Canonical user-facing term.** UI copy always says "seatrade", never "activity". "Activity" is only the glossary definition for newcomers; it never appears as a label.

### Block

A time slot within a fleet. There are 4 blocks per week:

- `1a` - Fleet 1, first half of the week
- `1b` - Fleet 2, first half of the week
- `2a` - Fleet 1, second half of the week
- `2b` - Fleet 2, second half of the week

Blocks and fleets are hardcoded domain knowledge — not parameters to `SchedulingProblem`.

### Session

A specific seatrade within a specific fleet and block. E.g., "Sailing in 1a". Sessions are the unit of assignment in the solver — a camper is assigned to a seatrade in a fleet+block, and that combination is a session.

### Fleet

A time-of-day grouping within a half of the week:

- **Fleet 1** - Morning Session
- **Fleet 2** - Afternoon Session

A cabin's fleet is chosen **per half, independently** — a cabin can be morning in the first half and afternoon in the second (and vice versa).

**Operating reality vs. intended model.** Today, schedules in practice keep a cabin in one fleet all week (a simplification to reduce assignment complexity). The model is moving toward independent per-half fleets, with "same fleet all week" becoming an *optional* hard constraint a user can switch on to keep the legacy behavior. Do not write user-facing copy that asserts a cabin is in one fleet for the whole week.

### Camper Relationship

A social constraint between a pair of campers. Each relationship has:

- **Pair** - Two campers identified by `(cabin, name)` composite keys
- **Type** - One of: `friends`, `besties`, `frenemies`
- **Symmetric** - Order doesn't matter; (Alice, Bob) is the same as (Bob, Alice)

| Type | Constraint |
|------|-----------|
| Friends | Pair shares ≥1 session (same seatrade, same fleet+block) |
| Besties | Pair shares both sessions (identical schedule) |
| Frenemies | Pair shares zero sessions (no seatrade overlap in any block) |

All relationship types are hard constraints — the solver must satisfy them or report infeasibility. Relationships are optional input; when absent, no relationship constraints are applied.

### Assignment

A mapping of a camper to a seatrade in a specific block. Each camper gets exactly 2 assignments per week (one per block).

### AssignmentSolution

Self-contained and portable — no reference to the MILP model. Fields: assignments DataFrame, SolverStatus, plus domain data (campers, seatrades_full, preferences) needed by wrangling and visualization. Wrangling functions operate on this, not on the SchedulingProblem.

### SolverStatus

A field inside `AssignmentSolution` (not a separate return). Tracks the outcome of a solve. Fields: state (SolverState enum: optimal/infeasible/error), gap (optimality gap as a float), message (human-readable, e.g. infeasibility detail). Progress monitoring (percent-complete during a running solve) stays in the UI layer via `@st.fragment` log polling — not in SolverStatus.

### Assignment Export

The app exports assignments in 2 formats for different audiences:

| Format | Sort Order | Use Case |
|--------|------------|----------|
| Captain's Book | Camper (Cabin upload order) | Internal logistics and bookkeeping, Distribute to cabin leaders for their campers |
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
        Val[preferences.py: Validate + Join 3→2 + Relationships]
        Prob[SchedulingProblem: Build MILP]
        Solve[solver.py: Solve + SolverStatus]
        Result[results.py: AssignmentSolution]
    end

    Upload --> Sim
    Sim -->|3 DataFrames + optional relationships [#58]| Val
    Val -->|2 DataFrames + validated relationships [#58]| Prob
    Solve -->|AssignmentSolution| Fragment
    Result --> Display
```

### Pipeline (happy path)

```
1. User uploads CSVs or uses simulation → app/ calls seatrades.simulation (produces 3 DataFrames: camper identity, camper preferences, seatrade setup + optional relationships [#58])
2. preferences.py validates (names match, seatrades exist in setup, relationship pairs valid [#58]) and joins 3 DataFrames → 2 (joined campers, seatrade setup) + validated relationships [#58]
3. SchedulingProblem(joined_campers, seatrade_setup) → holds parsed domain state (relationships parameter [#58 planned])
4. solver.run(problem, config) → calls problem.build(config) internally, returns AssignmentSolution (with SolverStatus inside)
5. UI reads AssignmentSolution.status via @st.fragment, displays assignments
6. `wrangle_assignments_to_longform(solution)` / `wrangle_assignments_to_wideform(longform_df)` → formatted DataFrames
```

## Optimization Problem

The scheduler balances two user-facing categories of settings:

- **Hard constraint** - A rule the schedule *must* satisfy, or the solver reports infeasibility (e.g. capacity limits, cabin cap, top-2 guarantee). Non-negotiable.
- **Soft weight** - A scored *preference* the solver trades off against others to find the best overall schedule (e.g. the three Objective Goals above). Higher weight = stronger pull, but never absolute.

The scheduler solves a mixed-integer linear programming problem with these constraints:

1. **One seatrade per block** - Each camper assigned to exactly 1 seatrade in each block
2. **No duplicates** - Camper cannot take same seatrade in both blocks
3. **Capacity limits** - Conditional per session: a session either runs (camper count within `[campers_min, campers_max]`) or doesn't run (0 campers). The minimum is a viability threshold — enforced only when the session runs — not a forced quota. See Decisions-Log #14.
4. **Preference only** - Campers only assigned seatrades they ranked
5. **Top-2 guarantee** - Campers guaranteed one of their top 2 choices
6. **Cabin max per seatrade** - Max k campers from same cabin in one seatrade (by default k=4)
7. **Fleet balance** - Cabins split evenly between fleets
8. **Gender balance** - Boys/girls cabins split evenly between fleets
9. **Camper relationships** - Friends (share ≥1 session), besties (identical schedule), frenemies (share zero sessions). Hard constraints, optional input.

### Objective Goals (user-facing)

The three objective weights are competing goals the Scheduling Captain balances. Each has a plain-language name and a real-world meaning the UI must convey:

| Weight (`config`) | User-facing goal | What raising it does | Real-world meaning |
|---|---|---|---|
| `preference_weight` | **Camper top choices** | More campers get their #1–2 ranked seatrades | Camper happiness |
| `cabins_weight` | **Cabin togetherness** | Cabinmates share more of their seatrades | Cabin cohesion / supervision |
| `sparsity_weight` | **Fewer seatrades to staff** | Run fewer distinct seatrades | Staffing load — fewer seatrades = fewer staff needed to operate |

These are presented as "importance" sliders with a one-line tradeoff description each, not as raw weights. `sparsity_weight`'s real driver is **staffing**, not session fullness — frame it that way.

Note the tension: `cabins_weight` (soft, encourages cabinmates together) pushes opposite to the hard cabin cap (max k campers from one cabin per seatrade). The UI must not present these as the same idea.

## Module Boundaries

| Package | Responsibility |
|---------|---------------|
| `seatrades/` | Service layer — domain logic, optimization, simulation, results |
| `app/` | Presentation layer — Streamlit UI only, no business logic |

### app/ modules

| Module | Owns |
|--------|------|
| `app.py` | Entry point, tab layout |
| `state.py` | Constants for all session state keys (low priority, replace scattered strings) |
| `tabs/` | Thin Streamlit presentation — widgets, forms, file uploads. Call service functions, display results. Includes Friends tab for optional relationship CSV upload [#58 planned]. |

### seatrades/ modules

| Module | Owns |
|--------|------|
| `problem.py` | `SchedulingProblem` — holds parsed domain state, builds MILP (variables, constraints, objective) when `.build(config)` is called. Does NOT solve. Config (weights, limits, solver settings) is passed at build time, not init — allows rebuilding with different configs against the same domain data. |
| `solver.py` | `solver.run(problem, config) -> AssignmentSolution` — orchestrates build + solve + wrangle. Calls `problem.build(config)` internally. Manages solver thread and CBC log reading. |
| `results.py` | `AssignmentSolution` dataclass + free functions for wrangling (`wrangle_assignments_to_longform`, `wrangle_assignments_to_wideform`, `prepare_seatrade_leaders`) and export views. Functions take `AssignmentSolution`, not the problem. |
| `visualization.py` | Build `alt.Chart` specs from `AssignmentSolution`. No Streamlit dependency — renders in any Altair-capable frontend. Colors cells by a camper-satisfaction scale (top choice → low/unranked) and labels block facets via `blocks.py`. |
| `blocks.py` | Pure decoder from block codes to Captain-friendly labels (`1a` → `1st·AM`) plus `BLOCK_DECODER_CAPTION`. No Streamlit, no side effects. |
| `preferences.py` | Pandera schemas + cross-reference validation (camper names match between sources, seatrade names in prefs exist in setup) + 3→2 DataFrame join (camper identity + camper preferences → joined campers) + relationship validation (self-pairs, duplicate pairs, camper existence) [#58 planned] |
| `simulation.py` | Generate mock data as 3 separate DataFrames (camper identity, camper preferences, seatrade setup) + optional relationships DataFrame [#58 planned] — goes through same validation pipeline as real uploads |
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

10. **Altair chart → separate `seatrades/visualization.py` module.** Chart is neither presentation layer nor data model — it's a visualization spec that consumes `AssignmentSolution`. Stays in service layer (no Streamlit dep) so it's reusable outside the app (API, notebooks, other frontends). `results.py` stays clean: data model + export only. `app/` renders via `st.altair_chart()`.

11. **Fleets and blocks are hardcoded domain knowledge.** Keats Camp always has 2 fleets with 2 blocks each (1a, 1b, 2a, 2b). Not parameters to `SchedulingProblem` — derived from the domain. Block availability for seatrades is always "all blocks."

12. **SchedulingProblem receives 2 DataFrames, not 6 params.** After `preferences.py` joins the 3 source DataFrames, the problem builder gets `joined_campers` (identity + preferences merged) and `seatrade_setup` (name, min, max).

13. **Camper relationships are hard MILP constraints with a dedicated input DataFrame.** Schema: `(cabin_1, camper_1, cabin_2, camper_2, relationship)` with values `friends`, `besties`, `frenemies`. Uses composite keys matching existing domain model. Session = seatrade + fleet + block; all relationship constraints operate on sessions. Validation rejects self-pairs and duplicate pairs (regardless of order). Relationships are optional — no constraints by default. Diagnosing contradictory constraint chains causing infeasibility is future work. PRD: `docs/prd/camper-relationships.md`.

14. **`campers_min` is a conditional minimum per session (issue #48).** A session may have either 0 campers (it doesn't run) or a count within `[campers_min, campers_max]` (it runs) — nothing in between. This reframes `campers_min` as a *viability threshold* ("worth running only with N campers") rather than a forced quota, and removes a class of spurious infeasibility where an unranked seatrade's floor was force-filled. Constraints-only — no objective term or penalty; whether a session empties is still driven by the existing objective (notably `sparsity_weight`). Reuses the existing per-session `seatrade_assignment` indicator (the "session runs" binary) — no new variable. Both bounds are gated on that indicator in `_add_capacity_constraints`. Default-on via `OptimizationConfig.allow_empty_sessions` (not exposed in the UI); setting it `False` restores the legacy hard floor. Only *widens* the feasible region — never makes a feasible problem infeasible; with `campers_min = 0` it is a no-op.

## Tech Stack

- **UI:** Streamlit
- **Optimizer:** PuLP (mixed-integer linear programming)
- **Validation:** Pandera (DataFrame schemas)
- **Deployment:** Streamlit Community Cloud
- **App URL:** <https://keats-seatrades.streamlit.app/>
- **Entry point:** app.py

## Git Workflow

Three branch prefixes: `feature/` (PRD-level work, sub-issues are commits on the feature branch), `dev/` (standalone small work off `main` only), `fix/` (bug fix off `main`). All merges are squash-merge via PR. `feature/` branches are created when the PRD issue opens. Any merge targeting `main` requires approval. See [ADR 0005](docs/adr/0005-git-branching-strategy.md).
