# Solve cancellation: removed-then-deferred, not "fix the Stop button"

The solve runs asynchronously (ADR-0004; the `@st.fragment` migration in #61). A natural ask is to let the Scheduling Captain *stop* a running solve. We deliberately do **not** have one yet, and the path to one is a spike — not a quick wiring fix.

**Status: accepted**

## Context

The original UI had a "Stop Optimizing" button. It never worked: it raised `KeyboardInterrupt` on the Streamlit callback, not on the daemon solver thread, so the solve kept running. Worse, clearing the UI while that daemon ran left a path to launching a second concurrent CBC solve (#61).

When #61 moved the solve to `@st.fragment` polling behind a single-run guard, it **removed** the non-functional button rather than leave a control that lied about what it did.

## Decision

1. There is **no Stop control** in the UI for now. A running solve finishes on its own or stops at the configured time limit.
2. **True cancellation is deferred to #74**, which is a *spike-first* issue — the mechanism is unknown, not merely unbuilt.

## Why not just wire up a working Stop button?

Because there is no cheap wire to connect.

- **PuLP exposes no handle to the running solver.** `COIN_CMD.solve_CBC` launches CBC via a `subprocess.Popen` held in a local variable that is never surfaced. There is no API to terminate an in-flight solve.
- A real Stop therefore needs a **process-level mechanism** (killing the solver and any children, cleaning up CBC's leaked temp files, deciding abandon-vs-best-so-far, possibly moving `SolveRun` from a thread to a child process). That carries genuine cost and risk and must be validated on the deployment target — hence a spike, not a feature.
- **The value is low for this tool.** It is a single-user internal app. The solver time limit already bounds a runaway solve, and #61's single-run guard prevents concurrent solves from piling up. So waiting out (or re-running after) a solve is an acceptable interim.

## Consequences

- The UI shows progress and the Captain waits; there is no mid-solve abandon (an abandon that freed the UI while the work continued would reintroduce the concurrent-solve risk the guard exists to prevent).
- #74 owns the investigation and will record the chosen approach before any implementation.
- **Future architecture reviews should not re-suggest "just make the Stop button work."** The button was removed on purpose, and real cancellation is a tracked, scoped spike (#74) — not an oversight.
