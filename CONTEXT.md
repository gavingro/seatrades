# SeaTrades Domain

Keats Camp seatrade scheduling optimization.

## Core Entities

### Camper

A child attending camp. Has:

- **Name** - Display name (not a unique identifier — two campers can share a name)
- **Cabin** - Group of ~12 campers staying together
- **Age** - The camper's age in whole years (required). Cabins cluster campers of similar age, but a cabin is *not* uniform — ages within one cabin typically span 1–3 years. Used as a soft optimization preference to keep similar-aged campers together within sessions and within blocks.
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

The 4 blocks group two different ways. By **half of the week**: 1st half `{1a, 1b}`, 2nd half `{2a, 2b}`. By **fleet**: AM/Fleet 1 `{1a, 2a}`, PM/Fleet 2 `{1b, 2b}`. A block code's digit picks the half; its letter picks the fleet.

A cabin's fleet is chosen **per half, independently** — a cabin can be morning in the first half and afternoon in the second (and vice versa).

**Same fleet all week (optional, issue #22).** A Scheduling Captain working by hand keeps each cabin in one fleet all week purely for simplicity. The solver doesn't need that crutch, so per-half independence is the default. A user can switch ON an *optional hard constraint* that forces a cabin's fleet to match across both halves (AM 1st half ⇒ AM 2nd half, and PM ⇒ PM), reproducing the legacy hand-scheduled behavior. Default OFF. Implemented by `OptimizationConfig.force_same_fleet_all_week` → `_add_same_fleet_constraints` in `problem.py`, exposed as a checkbox in the optimization config form's Advanced settings. Do not write user-facing copy that asserts a cabin is in one fleet for the whole week.

### Fleet Time

The non-seatrade activity. Each half-week has two time slots (AM and PM). A cabin attends a seatrade during its assigned slot; during the *other* slot of that half it is on Fleet Time — a single large group activity (a hike, a wide game) that every not-on-a-seatrade camper does together.

Fleet Time is the **perfect complement** of seatrade assignment: in any time slot, a camper is either in a seatrade or on Fleet Time, never both and never neither. It is therefore **not modeled in the solver** — it is implied by the absence of a seatrade. The output layer fills the empty seatrade cells with the label `"Fleet Time"` (`results.py`); it has no capacity, preference, or block parameters.

Because the Fleet Time group in one slot is exactly the set of cabins *not* on seatrades that slot — which is the seatrade population of the opposite-fleet block in the same half — any measurement over each block's seatrade population also describes the Fleet Time gatherings, with no need to model Fleet Time directly.

### Fleet Assignments (view)

A results **view**, not a separate domain concept: the compact Cabin × Block overview grid at the top of "The Schedule", above the master camper grid. Each cell is a labeled binary — **Seatrade** (the cabin is on a seatrade that block) or **Fleet Time** (its complementary slot) — coloured on a neutral presence scale (deliberately *not* the green→red satisfaction scale, since it encodes presence, not goodness). Because a cabin is on a seatrade only in the blocks matching its **Fleet assignment** (§Cabin — which fleet the cabin attends each half), the Seatrade/Fleet-Time pattern read off the AM/PM-decoded block columns *is* that fleet placement. So "Fleet Assignments" (the view) is a visualization of the existing **Fleet assignment** concept, not a new idea. Derived post-solve by `wrangle_fleet_assignments` (`results.py`) and drawn by `display_fleet_assignments` (`visualization.py`); adds no solver, config, or session state.

### Seatrade Staffing Schedule (view)

A results **view**, not a separate domain concept: the compact Seatrade × Block overview grid in "The Schedule", below **Fleet Assignments** and above the master camper grid. Each cell is a labeled binary — **Running** (that seatrade runs as a session that block, i.e. has ≥ 1 camper) or **Not offered** — coloured on the same neutral presence scale as Fleet Assignments (deliberately *not* the green→red satisfaction scale, since it encodes presence, not goodness). *Every* seatrade in the setup is a row, so a fully **Not offered** row surfaces a seatrade that got zero uptake this week — nobody to staff. This answers "*which* am I staffing" (a named-identity map), distinct from the **Sparsity** quality metric's detail chart, which answers "*how much of the catalog*" (a fraction rollup — running ÷ catalog×blocks — in Schedule Quality) and ties to the "staffing load" framing (§Optimization weights). Derived post-solve by `wrangle_seatrade_staffing` (`results.py`) and drawn by `display_seatrade_staffing` (`visualization.py`); adds no solver, config, or session state.

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

**Implementation status (slice #66).** All three types are now enforced by the solver. Besties (slice #65) equates assignment variables; friends and frenemies (slice #66) use an auxiliary binary `y[c1, c2, s]` = AND(both campers in session `s`), linearized with standard AND constraints. Friends require `sum_s y >= 1` (share at least one session); frenemies require `sum_s y == 0` (share none). See `_session_overlap_vars`, `_add_friends_constraints`, `_add_frenemies_constraints` in `problem.py`.

**Feasibility is checked at validation, not solve time.** A besties pair needs two identical sessions, so its members must share at least 2 preferred seatrades; a friends pair needs one shared session, so its members must share at least 1. `validate_relationships` rejects either pair that shares too few (naming both campers) before the solver runs. Frenemies has no such precondition — forcing overlap depends on global capacity/assignment, which is the out-of-scope solver-diagnostics case. The mock generator (`simulate_camper_relationships`) seeds one pair of each type on distinct campers — same-cabin for besties/friends, cross-cabin for frenemies — so the default demo always solves.

### Assignment

A mapping of a camper to a seatrade in a specific block. Each camper gets exactly 2 assignments per week (one per block).

### AssignmentSolution

Self-contained and portable — no reference to the MILP model. Fields: assignments DataFrame, SolverStatus, plus domain data (campers, seatrades_full, preferences) needed by wrangling and visualization. Wrangling functions operate on this, not on the SchedulingProblem.

### SolverStatus

A field inside `AssignmentSolution` (not a separate return). Tracks the outcome of a solve. Fields: state (SolverState enum), gap (optimality gap as a float), message (human-readable, e.g. error detail), and `timed_out` (the stop reason carried onto the *final* status — True when the solve stopped at the time limit rather than proving optimality). Progress monitoring (percent-complete during a running solve) lives in the service layer's `SolveRun.progress()` (a `SolveProgress` snapshot computed from the CBC log + elapsed time) — not in SolverStatus. The UI only polls it and renders.

A solve ends in one of **three failure-or-success outcomes**, diagnosed differently (`SolverState.from_pulp`: PuLP code `1`→optimal, `-1`→infeasible, `0`→timeout, else error):

- **Infeasible** — a hard constraint provably cannot be met; no schedule exists. (Diagnosing *which* constraint is future work — see Decisions-Log, and PRD `docs/prd/infeasibility-diagnosis.md`.)
- **Timeout** — the problem is *feasible* but the solver ran out of time (CBC's "Not Solved" / PuLP code `0`). A distinct state, **not** an error: the UI advises more time or a smaller problem, never "an unexpected error". Likely the dominant real-world failure at production roster scale.
- **Error** — a genuine crash (CBC binary missing, pty failure, unbounded/undefined status); the technical message is surfaced unchanged.

A **success** is itself two things, split by `timed_out`: **proven** — CBC closed the optimality gap, so "proven X% optimal" is meaningful and final — vs. **stopped-on-time** — CBC hit the time limit holding the best incumbent so far, which is usable but not proven near-optimal ("a longer solve may improve it"). Overstating the second as the first would mislead; the success banner branches on the flag.

### Assignment Export

The app exports assignments in 2 formats for different audiences:

| Format | Sort Order | Use Case |
|--------|------------|----------|
| Captain's Book | Camper (Cabin upload order) | Internal logistics and bookkeeping, Distribute to cabin leaders for their campers |
| Seatrade Leaders | Block → Seatrade → Cabin → Camper | Day-of attendance at each seatrade session |

Each row carries: camper, seatrade, `assignment` (0/1), `preference_rank`, `assigned_to_block`, cabin, block.

The longform (`wrangle_assignments_to_longform`) decomposes what was once a single conflated `preference` column into orthogonal facts (issue #85, [ADR 0010](docs/adr/0010-decompose-preference-into-orthogonal-facts.md)):

- **`assignment`** (0/1) — did this camper get *this* seatrade cell?
- **`preference_rank`** — the rank the camper *gave* this seatrade (1–4), else `999` (`UNMATCHED_PREFERENCE`) for unranked. A pure camper↔seatrade fact populated on **every** cell, so the rank a camper gave a seatrade they *didn't* get stays recoverable.
- **`assigned_to_block`** (bool) — does this camper have *any* seatrade this block, vs being on Fleet Time? A schedule fact about the whole block, distinct from `assignment` (one cell).

## Data Flow

```mermaid
flowchart LR
    subgraph UI [app/ — Presentation Layer]
        Upload[File Upload / Simulation Forms]
        Poll["@st.fragment polling SolveRun.progress() / result()"]
        Display[Render AssignmentSolution + Charts]
    end

    subgraph Service [seatrades/ — Service Layer]
        Sim[simulation.py: Generate Mock Data]
        Val[preferences.py: Validate + Join 3→2 + Relationships]
        Prob[SchedulingProblem: Build MILP]
        Run[solve_run.py: SolveRun thread + log progress]
        Solve[solver.py: Solve + SolverStatus]
        Result[results.py: AssignmentSolution]
    end

    Upload --> Sim
    Sim -->|3 DataFrames + optional relationships [#58]| Val
    Val -->|2 DataFrames + validated relationships [#58]| Prob
    Prob --> Run
    Run -->|solver.run| Solve
    Run -->|SolveProgress / AssignmentSolution| Poll
    Result --> Display
```

### Pipeline (happy path)

```
1. User uploads CSVs or uses simulation → app/ calls seatrades.simulation (produces 3 DataFrames: camper identity, camper preferences, seatrade setup + optional relationships [#58])
2. preferences.py validates (names match, seatrades exist in setup, relationship pairs valid [#58]) and joins 3 DataFrames → 2 (joined campers, seatrade setup) + validated relationships [#58]
3. SchedulingProblem(joined_campers, seatrade_setup, relationships) → holds parsed domain state; maps besties/friends/frenemies pairs to internal camper_ids [#65, #66]
4. solver.run(problem, config) → calls problem.build(config) internally, returns AssignmentSolution (with SolverStatus inside)
5. UI reads AssignmentSolution.status via @st.fragment, displays assignments
6. `wrangle_assignments_to_longform(solution)` / `wrangle_assignments_to_wideform(longform_df)` → formatted DataFrames
```

## Scoring

**Scoring** is the post-hoc measurement of a schedule's *goodness*, computed from an `AssignmentSolution` **after** the solve. It is deliberately separate from three neighbouring ideas that must not be conflated:

- **Objective** — what CBC optimizes *during* the solve (the soft weights). Some Quality Metrics echo an objective goal; others (fairness) have no objective counterpart. Overlap is coincidental, not a rule.
- **Optimality** — the solver's gap (`SolverStatus.optimality`, `1 − gap`): how close CBC *proved* it got to the mathematical optimum. A headline single number, **not** a goodness measure. On small rosters it's ~100% almost always.
- **Scoring** — human-interpretable schedule goodness, measured after the fact.

### Quality Metric

One axis of schedule goodness (there are 7). A Quality Metric is an *area* of goodness (e.g. "camper preference satisfaction", "age spread"), not a single number.

### Rollup Score

The single number that represents a Quality Metric's area. The metric's detailed view decomposes this rollup. Every rollup is framed **up-is-good** (higher = better schedule), regardless of whether the underlying raw quantity is naturally better-when-lower (e.g. age spread, variance).

### Anchor / Reference Band

A **Reference Band** is a curated per-metric *expected range*, bounded by two **Anchors**: the `low_anchor` (maps to the bottom of the axis) and `high_anchor` (maps to the top). Anchors are hand-tuned domain knowledge — the "normal" range we expect scores to fall in — not theoretical best/worst.

For a shared-scale comparison view, rollup scores are normalized behind the scenes against the band. The band is the **default axis domain** and a **floor on axis width**, so a single scenario never renders on a flat/meaningless scale. When an observed value falls **outside** the band (a genuinely great or poor scenario), the band **expands** to make that outlier the new endpoint and everything renormalizes; the band only ever grows, never contracts inside the anchors. Tooltips always show the **raw** metric value, never the normalized position.

Scoring is measured over **seatrade sessions**, generally ignoring Fleet Time unless a metric evaluates it directly (see age spread, which measures both a per-session and a per-block/Fleet-Time level).

### Design principle: MECE, no composite

The 7 Quality Metrics are meant to be **orthogonal** — mutually exclusive, collectively exhaustive areas of goodness. Level and equity are deliberately separate: a uniformly-miserable cabin scores *perfectly fair* (σ = 0) on the fairness metrics, and that is **correct** — the preference metric is what exposes the low level. The suite is **not** rolled up into one overall goodness number. The scheduler weighs the trade-offs themselves; Scoring hands them the instruments rather than deciding for them. (This is separate from the *solver optimality* headline, which is a single number but measures the gap, not goodness.)

### Cohesion

**Cohesion** measures how often a camper has company: the fraction of **camper×session slots**
that are *shared* — the camper's same-cabin cohort in that (block, seatrade) session is ≥2 (self +
a cabinmate). Counted per session, so a camper alone in one of their two blocks loses only that one
session, not their whole self. The rollup sits at the **same camper×session grain as the detail**
histogram (one row per camper per session), so the summary number and the drill-down count the same
thing: each *stranding* by cabin-group size and block. This per-session grain superseded an earlier
per-camper "every session" rollup (too harsh, and mismatched its own detail chart), which had itself
tightened the original "shares ≥1 session" framing (issue #99 review).

### Fairness Within / Between Cabins

Both fairness metrics are built from the same per-camper CPR (Combined Preference Rank) atom, grouped by cabin, using **population** standard deviation (`ddof=0`) — not pandas' default sample std (`ddof=1`). Population std is deliberate: it makes a 1-camper cabin (Fairness Within) or a 1-cabin roster (Fairness Between) correctly evaluate to `0`, not `NaN`. Std (not variance) is chosen for correct units and outlier sensitivity — one camper with a much worse schedule than their bunkmates should show up.

- **Fairness Within** — for each cabin, the std of its campers' CPR, averaged across cabins.
- **Fairness Between** — each cabin's *mean* CPR (mean, not sum, so a bigger cabin isn't penalized), then the std of those cabin means across cabins.

Both detail views are true histograms (binned quantitative x), not countplots (discrete x) like Age Spread/Sparsity — the reference line at the average requires a shared quantitative scale with the bars, which an ordinal x-axis cannot provide. The reference line's value is the mean of the *plotted* per-cabin quantity (the same statistic the histogram bins), which for Fairness Within happens to equal `raw_value` (it's already an average-of-per-cabin-spreads) but for Fairness Between is *not* `raw_value` (the std of means) — it is a separately computed mean of cabin means.

### Cabin Variety

**Cabin Variety** measures whether one cabin *dominates* a seatrade: the rollup is the mean over
running sessions of each session's **max cabin share** = the largest cabin's camper count ÷ the
session's **realized** size. A session with only one cabin present is fully dominated (share `1.0`,
worst); a session split evenly across `n` cabins scores `1/n`. Lower is better → down-is-bad, flipped
up-is-good at render time. It is the measurement counterpart of the `cabin_variety_weight` objective
penalty (constraint #6), but uses **realized** session size where the solver penalty keys off
**capacity** — a deliberate, acceptable mismatch (the two still move together; the metric is the
honest post-hoc measure). Orthogonal to **Cohesion**: Cohesion asks "do I have a cabinmate here?"
(per-camper, anti-loneliness); Cabin Variety asks "does one cabin dominate this session?" (per-session,
anti-domination) — a session can score well on both. The detail view is a true histogram (binned max
share on x, seatrade-session count on y) with a mean reference line equal to `raw_value`; each session
rides the `detail` stacking channel so the bars reach their true count (the vega countplot stacking
trap). Issue #109.

## Optimization Problem

The scheduler balances two user-facing categories of settings:

- **Hard constraint** - A rule the schedule *must* satisfy, or the solver reports infeasibility (e.g. capacity limits, top-2 guarantee, the opt-in cabin-share cap). Non-negotiable.
- **Soft weight** - A scored *preference* the solver trades off against others to find the best overall schedule (e.g. the three Objective Goals above). Higher weight = stronger pull, but never absolute.

The scheduler solves a mixed-integer linear programming problem with these constraints:

1. **One seatrade per block** - Each camper assigned to exactly 1 seatrade in each block
2. **No duplicates** - Camper cannot take same seatrade in both blocks
3. **Capacity limits** - Conditional per session: a session either runs (camper count within `[campers_min, campers_max]`) or doesn't run (0 campers). The minimum is a viability threshold — enforced only when the session runs — not a forced quota. See Decisions-Log #14.
4. **Preference only** - Campers only assigned seatrades they ranked
5. **Top-2 guarantee** - Campers guaranteed one of their top 2 choices
6. **Cabin variety** (issue #108) - Discourages one cabin from *dominating* a seatrade. A **soft penalty** (default on, `cabin_variety_weight`) charges each camper a cabin places in a seatrade beyond a per-seatrade free threshold of `round(0.25 × campers_max)`; the threshold keys off capacity (a pre-solve constant) so the term stays linear. An **optional hard cap** (`max_cabin_share_per_seatrade`, default `1.0` = off) caps a cabin at `round(share × campers_max)` per seatrade when slid below 100%. Replaces the old hardcoded "max 4 campers from one cabin per seatrade" (removed). See Decisions-Log #17.
7. **Fleet balance** - Cabins split evenly between fleets
8. **Gender balance** - Boys/girls cabins split evenly between fleets
9. **Camper relationships** - Friends (share ≥1 session), besties (identical schedule), frenemies (share zero sessions). Hard constraints, optional input. **All three are enforced (besties slice #65, friends/frenemies slice #66).** Besties (`_add_besties_constraints`) equates the two campers' assignment variables across every block_seatrade — no auxiliary variables. Friends and frenemies share an auxiliary binary `y[c1, c2, s]` = AND(both in session `s`); friends require `sum_s y >= 1`, frenemies `sum_s y == 0`.
10. **Same fleet all week** (optional, off by default — issue #22) - Forces each cabin's fleet (AM/PM) to match across both halves of the week. Opt-in hard constraint reproducing legacy hand-scheduled behavior; default OFF leaves fleet choice independent per half. Reuses the per-cabin block-selection variable (`_add_same_fleet_constraints`) — no new variables.

### Objective Goals (user-facing)

The objective weights are competing goals the Scheduling Captain balances. Each has a plain-language name and a real-world meaning the UI must convey:

| Weight (`config`) | User-facing goal | What raising it does | Real-world meaning |
|---|---|---|---|
| `preference_weight` | **Camper top choices** | More campers get their #1–2 ranked seatrades | Camper happiness |
| `cabins_weight` | **Cabin togetherness** | Cabinmates share more of their seatrades | Cabin cohesion / supervision |
| `sparsity_weight` | **Fewer seatrades to staff** | Run fewer distinct seatrades | Staffing load — fewer seatrades = fewer staff needed to operate |
| `age_weight` | **Keep similar ages together** | Tighter age spread within each session and each block | Age-appropriate peers in an activity and on Fleet Time |
| `cabin_variety_weight` | **Cabin Variety** | More cabins share each seatrade (one cabin dominates less) | Fairer access to popular activities; more social sessions to run. Direct counterweight to Cabin togetherness. |

These are presented as "importance" sliders with a one-line tradeoff description each, not as raw weights. `sparsity_weight`'s real driver is **staffing**, not session fullness — frame it that way.

**Age grouping** penalizes each group's age *range* (`maxAge − minAge`), summed over two levels and each normalized by its group count (mean range, not sum, so the levels are comparable): the *session* level (one `(block, seatrade)`) and the *fleet* level (one `block`, which by complementarity also covers Fleet Time). An advanced `age_balance` (0–1, default 0.5) splits `age_weight`'s pull between them — 0 favors fleet-wide, 1 favors per-seatrade. Range is outlier-sensitive by design: one odd-aged camper is cheap for the solver to move out. The penalty is soft and can never cause infeasibility.

Note the tension: `cabins_weight` (pull cabinmates together) pushes opposite to `cabin_variety_weight` (spread each cabin across seatrades), which in turn competes with `sparsity_weight` (concentrate into fewer seatrades) — three competing soft goals the Captain balances. The UI must not present cabin togetherness and cabin variety as the same idea. The old *hard* cabin cap is gone; a real ceiling is now the opt-in `max_cabin_share_per_seatrade` (Advanced, default off).

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
| `solver.py` | `solver.run(problem, config) -> AssignmentSolution` — pure synchronous orchestration of build + solve + wrangle. Calls `problem.build(config)` internally. Does NOT own the *solve* thread or read the log for progress — that lives in `solve_run.py`. It does wrap the `solve()` call in `live_cbc_log` (a pty tee whose one relay thread is joined before `run` returns) so cbc's log streams line-by-line instead of block-buffering (#100). |
| `solve_run.py` | `SolveRun` — runs `solver.run` in a background thread, reads the CBC log, and exposes `progress()` (a `SolveProgress` snapshot) / `result()`. The service-layer seam ADR-0004 mandates; the UI polls it and never imports `threading`/`queue` or opens the log file. |
| `results.py` | `AssignmentSolution` dataclass + free functions for wrangling (`wrangle_assignments_to_longform`, `wrangle_assignments_to_wideform`, `prepare_seatrade_leaders`) and export views. Functions take `AssignmentSolution`, not the problem. |
| `scoring.py` | Post-hoc Scoring (#31) — `score(solution) -> Scorecard` measures schedule *goodness* after the solve. Pure service layer, no Streamlit, **no normalization** (that is render-time, in `visualization.py`). `QualityMetric` (name, raw_value, anchors, `higher_is_better`, detail DataFrame) + `Scorecard` (metrics + pass-through `optimality`). Reuses `wrangle_assignments_to_longform`. Ships all seven Quality Metrics (Preference, Cohesion, Sparsity, Cabin variety, Age spread, Fair within, Fair between) with reference-band anchors calibrated against real mock-scenario solves (#97, #109). |
| `visualization.py` | Build `alt.Chart` specs from `AssignmentSolution`/`Scorecard`. No Streamlit dependency — renders in any Altair-capable frontend. Colors assignment cells by a camper-satisfaction scale (top choice → low/unranked), labels block facets via `blocks.py`, and owns the Scoring render layer: the pure `normalize_to_band` (raw → 0–100, band expands never contracts, down-is-bad flipped), the `display_quality_summary` overview plot, and a per-metric detail chart for each of the seven Quality Metrics. |
| `blocks.py` | Pure decoder from block codes to Captain-friendly labels (`1a` → `1st·AM`) plus `BLOCK_DECODER_CAPTION`. No Streamlit, no side effects. |
| `preferences.py` | Pandera schemas + cross-reference validation (camper names match between sources, seatrade names in prefs exist in setup) + 3→2 DataFrame join (camper identity + camper preferences → joined campers) + relationship validation (self-pairs, duplicate pairs, camper existence) [#58 planned] |
| `simulation.py` | Generate mock data as 3 separate DataFrames (camper identity, camper preferences, seatrade setup) + optional relationships DataFrame [#58 planned] — goes through same validation pipeline as real uploads |
| `config.py` | `OptimizationConfig`, `CamperSimulationConfig`, `SeatradeSimulationConfig`. Has PuLP dependency — `OptimizationConfig` owns its solver object directly. |

## Architecture Grilling — Decisions Log

Resolved during grilling session 2026-05-05. Open questions marked with [OPEN].

1. **`Seatrades` class → split into SchedulingProblem + solver + results.** Problem builder owns variables/constraints/objective. Solving is separate. Wrangling is separate. `SchedulingProblem` is stateful (holds parsed domain state) because the wrangler needs the same state — avoids re-parsing or building a second context object. Module is `problem.py` (not `scheduling_problem.py`). Config passed at `.build(config)` time, not init — allows rebuilding with different configs against same domain data.

2. **Solver produces `AssignmentSolution`, not raw pulp object.** Clean boundary: problem goes in, solution comes out. No leaking PuLP internals. `AssignmentSolution` is self-contained and portable — holds assignments DataFrame, SolverStatus, and domain data needed by wrangling/visualization. `SolverStatus` is a field inside `AssignmentSolution` (not a separate return): state is a `SolverState` enum (optimal/infeasible/timeout/error — see the SolverStatus glossary entry for the three outcomes and the proven-vs-stopped-on-time success split), `gap` is the optimality gap, `message` for human-readable detail, `timed_out` the final-status stop reason. Progress monitoring lives in the `SolveRun` seam (service layer), surfaced as `SolveProgress`; the UI only polls and renders.

3. **Service function `solver.run(problem, config) -> AssignmentSolution`.** UI calls one function. `solver.run` calls `problem.build(config)` internally. No solver orchestration in the presentation layer.

4. **Solver monitoring splits: the `SolveRun` seam (service layer, `solve_run.py`) runs the solve in a thread + reads the CBC log and exposes `progress()`/`result()`; the UI polls those and renders.** PuLP/CBC doesn't support mid-solve callbacks — the log file is the only progress signal. Progress percent is computed in `SolveRun.progress()` (a `SolveProgress` snapshot), not in SolverStatus. The migration is complete (#61): the active `SolveRun` lives in `session_state` (one run at a time, no queue), the UI polls it via `@st.fragment(run_every=2)` instead of a blocking loop, the run's presence both drives the fragment and disables the Assign button (single-run guard — no concurrent CBC solves), and the fragment finalizes the result then triggers a full-script rerun to stop polling. The non-functional "Stop" button was removed; true cancellation is deferred (ADR-0008 / #74).

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

15. **Friends and frenemies are enforced via a shared session-overlap auxiliary variable (slice #66).** Both reuse one binary `y[c1, c2, s]` = AND(camper c1 in session `s`, camper c2 in session `s`), linearized with the standard AND constraints (`y <= x1`, `y <= x2`, `y >= x1 + x2 - 1`) in `_session_overlap_vars`. Friends then require `sum_s y >= 1` (share at least one session); frenemies require `sum_s y == 0` (share none). Besties keeps its simpler variable-equality formulation (no aux var). Friends gain a pre-solve feasibility check mirroring besties: a friends pair sharing 0 preferred seatrades is rejected at validation (`FRIENDS_MIN_SHARED_SEATRADES = 1`), since they could never co-occupy a session. Frenemies has no cheap provable precondition (forcing overlap depends on global capacity/assignment), so it is left to solve-time infeasibility — the out-of-scope diagnostics case from item 13.

16. **Same fleet all week + block/fleet rename (issue #22).** Added opt-in `OptimizationConfig.force_same_fleet_all_week` (default `False`) — `_add_same_fleet_constraints` ties each cabin's AM/PM choice across both halves, reusing the per-cabin block-selection variable (no new variables). Bundled an internal-only vocabulary fix: the solver had named the four *blocks* "fleets". Renamed `SchedulingProblem.fleets` → `blocks`, `fleet_assignment` → `block_assignment` (PuLP label `Cabin_Block_Assignment`), `_add_fleet_assignment_constraints` → `_add_block_assignment_constraints`, `_add_fleet_balance_constraints` → `_add_block_balance_constraints`, and block-iterating loop vars `fleet` → `block`, so *block* and *fleet* now match the glossary. Kept as-is (separate migration): the public `max_seatrades_per_fleet` config field, `_add_max_seatrades_per_fleet_constraints`, and the "Max seatrades per fleet" UI label — so the Advanced expander briefly carries "fleet" in two senses. **Correction to the issue's stated rationale:** the toggle *cannot* make a feasible week infeasible via fleet/gender balance — those constraints are lower-bound-only and symmetric across the two halves, so same-fleet just copies the first-half solution to the second. The toggle is instead verified by a *binding* test: on a sparsity-tuned roster the unconstrained optimum rotates a cabin between halves, and turning the toggle on forces a same-fleet schedule with a strictly worse objective.

17. **Cabin variety replaces the hardcoded max-4-per-cabin (issue #108, PRD #101).** Deleted the `_CABIN_MAX_PER_SEATRADE = 4` hard constraint — a hard rule doing a soft job, wrong at both capacity ends, and a source of spurious infeasibility (a besties chain of 5+ in one cabin). Replaced by two config-driven levers. **Soft penalty** (`cabin_variety_weight`, default 3): `_cabin_variety_penalty_term` adds one non-negative `excess` aux var per (cabin, session), `excess ≥ cabin_count − round(0.25 × campers_max)`, and adds `cabin_variety_weight × Σ excess` to the minimized objective. The 0.25 free-fraction is a fixed internal constant (`_CABIN_VARIETY_FREE_FRACTION`), not user-exposed; keying the threshold off `campers_max` (constant pre-solve) keeps the term **linear** — no nonlinear realized-share term. **Optional hard cap** (`max_cabin_share_per_seatrade`, float `[0.25, 1.0]`, default `1.0` = off): `_add_cabin_share_cap_constraints` adds nothing at 1.0; below it, caps each cabin at `round(share × campers_max)` per seatrade (renamed from `_add_cabin_max_constraints`). Verified by a *binding* test (high weight spreads a cohesion-packed cabin at a strictly worse preference cost, not infeasible), a hard-cap feasibility test (default no-op solves; 25% cap makes a 3-bestie trio infeasible), and a regression (5-bestie chain now solves by default). Turning `cabin_variety_weight=3` on by default nudged the Cohesion and Age-Spread reference-band low anchors down (`COHESION_LOW_ANCHOR` 0.65→0.60, `AGE_SPREAD_LOW_ANCHOR` 1.5→1.4, recalibrated 2026-07-09) — the variety pressure runs cohesion a touch lower and widens age ranges slightly; caught and re-bracketed by the slow band-drift guard. The **Cabin Variety Quality Metric + drill-down chart** is built separately in #109 (Decisions-Log #18).

18. **Cabin Variety Quality Metric + drill-down chart (issue #109, PRD #101).** Added the 7th Quality Metric `Cabin variety` to `scoring.py` (`_cabin_variety_metric`): rollup `raw_value` = mean over running sessions of each session's max cabin share (largest cabin's camper count ÷ **realized** session size), `higher_is_better=False`. Uses realized size where the #108 solver penalty keys off capacity — a deliberate, acceptable mismatch (honest post-hoc measure; the two still move together). Single-cabin session → `1.0` (worst); evenly split across `n` cabins → `1/n`. Detail is one row per running `(block, seatrade)` session with `max_share`. Reference band `[0.4, 0.7]` calibrated 2026-07-09 against seeded 8-cabin mock solves (~0.57–0.59, seed 0 = 0.57), same approach as #97; the slow band-drift guard now covers it automatically. `visualization.py` adds `display_cabin_variety_detail` — a true histogram (binned `max_share` on x, seatrade-session count on y) with a mean reference line equal to `raw_value`, reusing the generalized `_histogram_with_average` (now parameterized by `id_fields`/`count_title`, shared with the two Fairness detail charts). The per-session id (`seatrade` × `block`) rides the `detail` stacking channel, not tooltip alone — the vega countplot stacking trap (bars flatten to height 1, invisible to unit tests); guarded by a chart-spec test and verified in a browser (ADR-0007). The metric auto-appears in the summary plot and the drill-down selectbox (both derive from the scorecard / `_DETAIL_BUILDERS`). Orthogonal to Cohesion (per-camper anti-loneliness vs per-session anti-domination). Updated every "6 Quality Metrics" reference to "7".

## Tech Stack

- **UI:** Streamlit
- **Optimizer:** PuLP (mixed-integer linear programming)
- **Validation:** Pandera (DataFrame schemas)
- **Deployment:** Streamlit Community Cloud
- **App URL:** <https://keats-seatrades.streamlit.app/>
- **Entry point:** app.py

## Git Workflow

Three branch prefixes: `feature/` (PRD-level work, sub-issues are commits on the feature branch), `dev/` (standalone small work off `main` only), `fix/` (bug fix off `main`). All merges are squash-merge via PR. `feature/` branches are created when the PRD issue opens. Any merge targeting `main` requires approval. See [ADR 0005](docs/adr/0005-git-branching-strategy.md).
