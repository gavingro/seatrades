# PRD: Infeasibility Diagnosis — explain *why* a solve fails

Source issue: [#78](https://github.com/gavingro/seatrades/issues/78). This PRD is the
deliverable of the research spike posted there. It is grounded in an empirical harness
(`scratchpad/infeasibility_spike.py`, `probe_gaps.py`, `probe_missing.py`,
`probe_friends_hub.py`, `probe_collision.py`) that builds a minimal input set per
candidate failure mode, confirms CBC returns `Infeasible`, and validates a post-hoc
structural check against it. All "confirmed" claims below were reproduced against the real
model in `seatrades/problem.py`.

## Problem Statement

When a solve is `INFEASIBLE`, the Scheduling Captain — who has no optimization background —
sees one static line (`assignment_failure_warning`) and `SolverStatus.message` is empty for
`INFEASIBLE` (only `ERROR` carries a message). There is no signal about *which* rule could
not be met, so the Captain cannot adjust inputs with intent. MILP infeasibility is opaque:
the solver reports "infeasible" with no culprit.

## Research findings

### "Solver failure" is three outcomes, not one (diagnose the outcome first)

Empirically, a solve ends in one of three states, and they need **different** diagnoses.
Conflating them is the root framing error this spike corrected:

| Outcome | PuLP code / `LpStatus` | What it means | Right diagnosis |
|---------|------------------------|---------------|-----------------|
| **Infeasible** | `-1` / `Infeasible` | a hard constraint provably can't be met | the constraint checks below (Proven / Suspected) |
| **Not solved / timeout** | `0` / `Not Solved` | **feasible**, but no proven schedule within `timeLimit` (0 variables assigned) | **scale / time**: raise `timeLimit`, loosen `gapRel`, cut cabins/seatrades/relationships |
| **Error** | crash | CBC binary missing, pty failure, etc. | surface the message (existing behavior) |

Confirmed: a 10-cabin / 96-camper **feasible** roster returns `Not Solved` at `timeLimit=1s`
and `Optimal` at `60s`. Per the `roster-scale-feasibility-ceiling` note (a real 22-cabin
deployment "won't schedule"), **timeout is likely the dominant real-world failure** — yet
none of the constraint checks below apply to it (the problem is feasible). Running them on a
timeout yields "no cause found," which is worse than useless.

**Two current bugs this exposes:**
1. `SolverState.from_pulp` maps code `0` → `ERROR`, so a timeout is shown to the Captain as
   *"The optimizer hit an unexpected error and couldn't finish: Not solved"* — it reads as a
   crash, not "needs more time / smaller problem." Timeout deserves its own state and copy.
2. The infeasibility-diagnosis suite must **only run on `INFEASIBLE`**, never on a timeout.

### A "success" is also two things: gap-closed vs. stopped-on-time

Even when a solve returns a usable schedule (`OPTIMAL`), there are two ways it got there, and
the app currently shows them **identically** — the success banner fires for any `OPTIMAL`
state and prints `optimality = 1 - gap` (`assignments_tab.py`), whether the solver *proved*
it reached the optimality gap or merely *stopped on the time limit* holding the best
schedule so far:

- **Gap-closed** — CBC drove the MIP gap to `≤ gapRel` (default 0.10) and stopped on
  optimality. "X% optimal" is meaningful and final. Confirmed: 12 cabins / 60 s → `gap=0.08`,
  a clean proven success.
- **Stopped-on-time** — CBC hit `timeLimit` while holding a feasible incumbent whose gap was
  never closed. The schedule is usable but *not proven near-optimal*; a longer solve may
  improve it. The banner should say so, not reuse the "X% optimal" copy.

The mechanism exists but isn't wired to the final result: `detect_timeout()` /
`SolveProgress.timed_out` live only on the **transient progress snapshot**, while the final
`SolverStatus` carries no timed-out flag — so at display time the banner cannot distinguish
the two. Fix: carry the stop reason (timed-out vs. gap-closed) onto `SolverStatus` and branch
the success copy.

> **Empirical caveat.** With CBC on this model I could **not** reproduce a *stopped-on-time
> success* (code `1` with an open gap): at the sizes tested, a timeout returns code `0`
> ("Not Solved", ~no assignments) — the mislabeled-`ERROR` case above — rather than a
> code-`1` incumbent. So in practice the more urgent split is INFEASIBLE / TIMEOUT / ERROR;
> the gap-closed-vs-stopped-on-time banner is a **defensive** distinction for the day a
> timed-out solve *does* return a usable incumbent (larger rosters, different solver, or a
> `gapRel` the solve can't reach in time). It is cheap to add and prevents overstating a
> schedule's quality.

### The model shape that drives every check

- Each camper takes **exactly one seatrade per half-week** (`FLEET_BLOCKS = [[1a,1b],[2a,2b]]`)
  → 2 sessions/week, restricted to their **4 preferred seatrades**.
- A cabin sits entirely in **one block (AM `a` / PM `b`) per half** (block-assignment +
  linking constraints).
- `cabin_max` = **4 same-cabin campers per session**; capacity gates each session to `0`
  campers (doesn't run) or `[campers_min, campers_max]` (runs).
- Besties share an **identical** 2-session schedule; friends share **≥1** session; frenemies
  share **0**.

### Failure modes: two tiers

**Proven** = a *necessary feasibility condition* is violated, so infeasibility follows with
certainty. Each was solver-confirmed `Infeasible` and its check fired on the broken fixture
but not on a feasible baseline.

| ID | Mode | Detection predicate (inputs + config only) | Config deps | Current gap |
|----|------|--------------------------------------------|-------------|-------------|
| P1 | Global preferred-capacity shortfall (**max side**) | `N > 2 · Σ campers_max` over the **preferred-seatrade union**; if `max_seatrades_per_fleet=k`, cap the sum to the *k* largest | `max_seatrades_per_fleet`; `allow_empty_sessions`/`campers_min` tighten it | not checked |
| M1 | Min-floor starvation (**min side**, dual of P1) | a seatrade is "dead" if `popularity(s) < campers_min(s)`; a camper with `< 2` **live** preferred seatrades can't fill 2 sessions | `campers_min`; `allow_empty_sessions` (min side only bites when a session must run) | not checked — **P1 misses this** |
| M2 | Top-2 guarantee both dead | a camper's `seatrade_1` **and** `seatrade_2` are both dead (`popularity < campers_min`) → the top-2 guarantee cannot hold even though the camper is placeable | `campers_min` | not checked |
| B1 | Besties **chain** pref-intersection < 2 | for each besties connected component, `|∩ prefs over all members| < 2` | — | **validation only checks pairwise** |
| B2 | Besties chain exceeds `cabin_max` | any besties component has `>4` members **in one cabin** (they must share a session) | — | not checked |
| B3 | Besties chain size > session capacity | a besties component of size *m* has `< 2` shared seatrades with `campers_max ≥ m` | — | not checked |
| R1 | Besties/frenemies contradiction | a frenemies pair lies inside a besties component (must be identical **and** disjoint) | — | not checked |
| FH | Friends "hub" / 2-cover | for a camper *h* and its friends *F*, no 2-subset of `prefs(h)` intersects **every** `prefs(h)∩prefs(f)` (*h* occupies only 2 seatrades) | — | **validation only checks pairwise** |
| FC | Frenemies clique (pigeonhole) | *k* mutual-frenemies in one cabin (forced to share a block) whose combined preferred seatrades number `< k` — each needs a distinct session per half | — | not checked |

> **Five of the six proven modes slip past today's `validate_relationships`**, which checks
> besties/friends *pairwise* only. The transitive-chain gap is real and reproduced: a chain
> `X–Y–Z` where every pair shares ≥2 prefs but `X∩Y∩Z = {A}` passes validation yet is
> solver-infeasible.

**Suspected** = pressure heuristics. The solver *can* be infeasible from these, but proving
it needs global reasoning, so they are advisory, not definitive.

| ID | Pressure signal | Why only suspected |
|----|-----------------|--------------------|
| S1 | `cabin_max` squeeze — a cabin clustered on few seatrades | **Confirmed NOT infeasible on its own** (cabin of 12, 4 prefs → `Optimal`). Only bites combined with capacity. |
| S2 | Frenemies forced overlap (**cross-cabin**) | Confirmed feasible in the simple case; depends on global block assignment. The same-cabin clique case is now Proven (**FC**). |
| S3 | Balance tension — besties / `force_same_fleet_all_week` pull cabins into the same block vs. the `≥ floor(n/2)` block & gender-balance floors | Emergent from the interaction of several constraints. |
| S4 | Top-2 guarantee squeeze — many campers' top-2 seatrades globally oversubscribed | Global capacity/assignment interaction. |
| S5 | Balance × min-floor — block/gender balance forces cabins to split across blocks, dropping a block's population below `campers_min` so no seatrade there can run | Confirmed: same roster, `min=3` → infeasible, `min=1` → optimal. Emergent from balance + capacity coupling. |

### The unifying abstraction — a bipartite matching deficiency (recommended backstop)

Five of the proven modes — **P1, M1, M2, B3, FH** — are the *same abstraction*: a set of
campers collectively needs *K* distinct feasible session-slots, but only *J < K* exist
(**Hall's condition** / a max-matching deficiency).

- P1 = all campers vs total seats (max side)
- M1 = one camper vs their **live** preferred seatrades (min side)
- M2 = a camper's top-2 vs live top-2 slots
- B3 = a besties group vs sessions large enough to hold it
- FH = a friends hub vs the 2 seatrades it can occupy

**Recommendation:** rather than trying to enumerate every mode (an open-ended list), ship the
ad-hoc checks as fast, specific first-line detectors *and* a single **matching-deficiency
backstop**: build the camper → feasible-session bipartite graph (a session is feasible for a
camper when the seatrade is preferred **and** can run — `popularity ≥ campers_min`, capacity
allows), then test Hall's condition. Any deficient camper set is a *provable* infeasibility,
and the deficient set **names the exact culprits** for the UX. Because it is a *necessary*
condition that ignores the besties/frenemies/balance coupling, it never false-positives; the
coupled cases (S5, frenemies-global) correctly fall through to the Suspected tier.

One refinement this makes obvious: **FH must run on the besties-*merged* entity**, not on
individuals. Merged besties occupy their 2 seatrades jointly, so their combined friends can
exceed the 2-cover even when neither member's friends do alone.

### Key negative result

`cabin_max` alone cannot cause infeasibility under the real schema (4 unique prefs, cabins
≤ 12): a single camper contributes 4 preferred seatrades, so the per-cabin union always
covers `ceil(size/4)` distinct seatrades. It is contributory, never a standalone cause.
This is why it lands in the Suspected tier despite being a hard constraint.

## Solution

### Branch on the outcome first

The feature is not "explain infeasibility" — it is "explain why the solve didn't produce a
usable schedule," and that starts by distinguishing the three outcomes above:

- **`INFEASIBLE`** → run the constraint-diagnosis suite (Proven pre-solve + Suspected
  post-mortem, below).
- **`NOT SOLVED` / timeout** → a distinct state + message: the problem is feasible but too
  large for the time budget. Advise raising `timeLimit`, loosening `gapRel`, or reducing
  cabins / seatrades / relationships (ties to `roster-scale-feasibility-ceiling`). This needs
  a new `SolverState` (e.g. `TIMEOUT`) so it is no longer mislabeled `ERROR`. Do **not** run
  the constraint checks here.
- **`ERROR`** → unchanged: surface the message.

And within a returned schedule (`OPTIMAL`), split the **success** banner by stop reason:
*"proven X% optimal"* (gap-closed) vs. *"stopped at the time limit — best schedule so far, a
longer solve may improve it"* (stopped-on-time). Requires carrying the timed-out flag onto
`SolverStatus` (today it lives only on the transient `SolveProgress`).

### Placement — recommendation (OPEN decision for maintainer)

The **Proven** checks are cheap *necessary conditions*, and five of them are natural
extensions of the existing pre-solve `validate_relationships` (which already does the
pairwise besties/friends checks). Running them **pre-solve** is strictly better UX than
solve-then-explain: fail fast with a precise, named message, and *fix five current
correctness gaps* along the way. This also matches the project's established
"surface-infeasibility-at-validation" principle.

The **Suspected** checks need a *failed* solve to be worth showing (they're advisory
pressures, prone to false positives pre-solve). These fit the **post-mortem** model from
triage: run only when the solver returns `INFEASIBLE`, and report the ranked pressures.

**Recommended hybrid:**

1. **Pre-solve (validation):** extend `validate_relationships` (and add a capacity
   precondition) with the Proven checks — B1, B2, B3, R1, FH, P1. Each raises a specific,
   named `ValidationError` naming the campers/seatrades involved, before any solve runs.
2. **Post-mortem (on `INFEASIBLE`):** a `diagnostics` module runs the Suspected pressure
   checks and returns a **ranked, multi-finding** report. If nothing fires, fall back to
   today's generic message (never worse than now).

This reconciles the triage decision ("solver fails, *then* diagnose") with the fact that the
provable cases are better caught before wasting a solve. **If the maintainer prefers the
pure post-mortem model** (all checks run only after a failed solve), every Proven check also
works post-hoc unchanged — the only cost is a wasted solve and later error surfacing.

### Reporting UX

- **Report all findings, ranked — not first-hit.** Heuristic (Suspected) checks aren't
  guaranteed to be *the* binding cause; stopping at the first risks a stuck loop (fix a
  non-cause, still fail, learn nothing). Run the whole suite, list every finding.
- **Tier the output:** proven causes first ("This *cannot* be scheduled because…"), then
  suspected pressures ("Likely contributing…").
- Each finding names the concrete entities (camper names via `(cabin, name)`, seatrade
  names) and the lever to pull (raise a `campers_max`, drop a besties link, loosen
  `max_seatrades_per_fleet`).

### Seam / interfaces

- New module `seatrades/diagnostics.py`, pure (no Streamlit, no solver): functions over the
  domain DataFrames + `OptimizationConfig`, returning a list of findings (`tier`,
  `message`, involved entities).
- **Pre-solve:** call the Proven checks from the existing validation path
  (`validate_relationships` / `join_and_validate`), raising `ValidationError` with the same
  collect-all-then-raise pattern already in use.
- **Post-mortem:** the service layer (`solve_run.py`) invokes the Suspected suite when the
  result is `INFEASIBLE`, writes the ranked findings into `SolverStatus.message` (empty
  today for `INFEASIBLE`). `assignment_failure_warning` (`app/tabs/assignments_tab.py`)
  already renders `status.message` for `ERROR` — extend it to render for `INFEASIBLE`.
- No change to the solver model, constraints, or session state.

## Testing decisions

- One fixture per Proven mode (P1, B1, B2, B3, R1, FH) that CBC confirms `Infeasible`
  (port from `scratchpad/infeasibility_spike.py`), asserting the check fires on the broken
  input and not on a feasible baseline. These become `@pytest.mark.slow` where they solve.
- A pure unit test per check (no solve) over crafted inputs — fast loop.
- Regression test for the transitive-besties gap: the `X–Y–Z` chain must now be rejected at
  validation (it currently passes).
- Post-mortem: assert `INFEASIBLE` with no Proven cause still yields the generic fallback.

## CONTEXT.md change

Add a new domain entry (after **Camper Relationship**), and update the frenemies note that
currently calls this "the out-of-scope solver-diagnostics case":

```markdown
### Infeasibility Diagnosis

A **post-mortem** explanation of why a solve returned no schedule. A solve ends in one of
three outcomes, diagnosed differently: **infeasible** (a hard constraint provably can't be
met — the checks below apply), **timeout / not-solved** (the problem is *feasible* but too
large for the time budget — advise more time or a smaller problem, a separate `SolverState`,
not an error), and **error** (a genuine crash). Infeasibility Diagnosis covers the first:
the MILP solver reports only "infeasible" with no culprit, so the app derives the cause from
the inputs + `OptimizationConfig`.

Two tiers:

- **Proven** — a *necessary feasibility condition* is violated, so infeasibility follows
  with certainty. These are cheap structural checks run **pre-solve** (extending
  `validate_relationships`): too few seats for the campers (**max side**) or too few campers
  to reach a seatrade's minimum so it can never run (**min side** — a camper with fewer than
  two runnable preferred seatrades, or whose top two are both un-runnable); a besties
  connected component whose members' preferences intersect in fewer than 2 seatrades, exceed
  `cabin_max` (4) within one cabin, or outnumber every shared seatrade's capacity; a
  frenemies pair inside a besties component; and a friends "hub" whose friends need more
  than the 2 seatrades the hub can occupy. Most of these are instances of one
  bipartite-matching deficiency (campers vs. runnable sessions), so a Hall's-condition check
  is the general backstop. Each raises a named `ValidationError`.
- **Suspected** — pressure heuristics reported **post-solve** only when the solver returns
  `INFEASIBLE`: `cabin_max` clustering, frenemies overlap pressure, block/gender-balance
  tension against `force_same_fleet_all_week`, and top-2 oversubscription. Advisory, ranked,
  multiple findings — never first-hit.

`cabin_max` alone cannot cause infeasibility under the 4-unique-preferences schema (cabins
≤ 12); it is contributory only, which is why it sits in the Suspected tier.
```

And replace, under **Camper Relationship**, the sentence calling frenemies feasibility "the
out-of-scope solver-diagnostics case" with a pointer to **Infeasibility Diagnosis** (frenemies
overlap is a Suspected pressure, not a pre-solve precondition).

## Out of scope

- Shipping the production feature — a follow-up issue implements this PRD.
- Changing the solver model or any hard constraint.
- IIS / constraint-relaxation probing (re-solving with constraint groups dropped). The
  spike found the Proven checks cover the provable cases cheaply; relaxation-probing is only
  worth revisiting if the Suspected tier proves too vague in practice.
- Exhaustive global infeasibility detection — some infeasible inputs will fire no Proven
  check and only vague Suspected ones; the generic fallback covers those.

## Open questions for the maintainer

1. **Placement:** hybrid (Proven pre-solve, Suspected post-mortem) as recommended, or pure
   post-mortem for everything?
2. **P1 capacity as validation:** OK to reject a solve pre-emptively on the capacity bound,
   or only advise (some Captains may want to attempt a solve anyway)?
3. **Ranking within a tier:** by likelihood, by fix-effort, or by entity count?
4. **Timeout as its own state:** add a `SolverState.TIMEOUT` (splitting today's `ERROR`
   mapping of code `0`) and a scale/time message? This fixes a current mislabel and is
   arguably higher-impact than the constraint checks at production scale — should it ship
   first, or as part of this work?
