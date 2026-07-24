# Spike #115 — empirical suspected-tier pressure thresholds

Parent PRD: [`infeasibility-diagnosis.md`](infeasibility-diagnosis.md) (issue #78).
Replaces the conservative placeholder thresholds #114 shipped for the five suspected
pressure signals with values measured against real solves.

## Method

Throwaway harness (`scratchpad/spike_115.py`, `spike_115_top2_flip.py` — not shipped).
For each signal we dialled its pressure axis up while holding the rest of the roster
healthy, ran a **real CBC solve** per step (3 seeds each), and recorded
`(raw signal value, solve outcome)`. A separate sampler read each signal's raw value on
25 random, comfortably-feasible 8-cabin rosters — the "healthy baseline" a cutoff must
sit above to avoid crying wolf. ~180 solves total.

Two calibration modes fell out:

- **Signals that can drive infeasibility** — put the cutoff at the observed
  feasible→infeasible flip (or just above the healthy baseline when the flip is far off).
- **Signals that only contribute** (never infeasible alone) — put the cutoff above the
  healthy-roster distribution and flag the weak discriminating power.

## Findings per signal

| Signal | Constant | Healthy max | Feasible→infeasible flip | #114 placeholder | Recommended | Discriminating power |
|---|---|---|---|---|---|---|
| Cross-cabin frenemies overlap | `SUSPECTED_FRENEMIES_CLUSTERING_RATIO` | (none form on random rosters) | **2.0 → 2.25** (clean) | 1.0 | **2.0** | **Strong.** Only signal with a crisp boundary. |
| Top-2 oversubscription | `SUSPECTED_TOP2_OVERSUBSCRIPTION_FACTOR` | 1.17 | 3.67 → 4.0 | 1.5 | **1.5** (keep) | Moderate. Flips only at high ratios; 1.5 flags early strain above healthy noise. |
| Cabin clustering | `SUSPECTED_CABIN_CLUSTERING_SHARE` / `_MIN_CAMPERS` | 0.0 | never (5 timeouts) | 0.75 / 8 | **0.75 / 8** (keep) | Weak for infeasibility; flags solver *strain* (only signal that caused timeouts). |
| Balance vs minimum | `SUSPECTED_BALANCE_MIN_POPULARITY_FACTOR` | n/a (no floors on healthy) | never (feasible at ratio 1.0) | 2.0 | **2.0** (keep) | Weak — **drop candidate.** Genuine case already Proven starvation. |
| Gender dominance vs. same-fleet lock | `SUSPECTED_GENDER_DOMINANCE_SHARE` | 0.875 | never (provably can't) | 0.75 | **0.9** | **Zero — top drop candidate.** Placeholder fired *below* the healthy baseline. |

### Detail

**Cross-cabin frenemies overlap — raise 1.0 → 2.0 (the headline correction).**
A cross-cabin frenemies clique all ranking the same seatrades: feasible through
`size/distinct-seatrades = 2.0` in every seed, infeasible from 2.25 up. #114's placeholder
`1.0` fired across the entire feasible 1.0–2.0 band — a false positive on every tight-but-solvable
group. `2.0` sits exactly at the empirical boundary.

**Top-2 oversubscription — keep 1.5.** Because a seatrade runs in all four week-blocks
(`4·campers_max` real seats) while the raw signal's denominator is the half measure
(`2·campers_max`), hard infeasibility only appears at raw ~4.0 (feasible through 3.67,
mixed/timeout at 4.0, infeasible from 4.33). Healthy rosters top out at 1.17, so `1.5` is
the smallest round value above healthy noise — it flags real early-demand concentration
well before it breaks, which is the point of an *advisory* hint.

**Cabin clustering — keep 0.75 / 8.** Random healthy rosters never cluster (raw 0.0), so any
firing is already abnormal and the cutoff can't cry wolf. It never produced infeasibility, but
it was the *only* signal that provoked solver **timeouts** (extreme cohesion makes the MILP
hard) — so it earns its keep as a strain hint, not an infeasibility predictor.

**Balance vs minimum — keep 2.0, flag as drop candidate.** Even at ratio 1.0 (popularity ==
floor) every solve was feasible: campers who'd lose a split-out seatrade fall back to their
other live picks. The only genuinely infeasible version (a seatrade that is a camper's *only*
option) is already covered by the Proven starvation check, so this suspected signal adds little.

**Gender dominance — raise 0.75 → 0.9, top drop candidate.** Two problems. (1) The same-fleet
lock *provably cannot* make a feasible week infeasible (fleet/gender balance are lower-bound-only
and symmetric across the two halves — Decisions-Log #16), so this signal has no path to the
outcome it advises about. (2) Random healthy rosters already reach 0.875, so the placeholder
`0.75` fired *below* the healthy baseline — guaranteed wolf-crying. Real camps run
deliberately single-gender cabins, pushing legitimate dominance even higher, so no cutoff makes
this trustworthy. Raised to `0.9` to blunt false alarms; the honest fix is to drop the signal.

## Recommendations to #78 / #114

- **Adopt** the two raised cutoffs (frenemies `2.0`, gender `0.9`); the other three keep their
  values, now evidence-backed rather than placeholders.
- **Drop candidates** for a later slice: *gender dominance vs. same-fleet lock* (no causal path,
  cries wolf) and *balance vs minimum* (subsumed by Proven starvation). Both were left in place
  and conservative rather than removed, to keep this spike to "tune numbers, don't reshape checks."
- **Cabin clustering** is better understood as a solver-*strain* hint than an infeasibility cause;
  its copy already hedges appropriately.
