# Solver monitoring: log-polling with Streamlit fragments

The solver runs in a background thread. Progress is reported by reading the CBC log file and surfacing structured status to the UI via `@st.fragment` polling.

**Status: accepted**

## Why not callbacks?

PuLP's `.solve()` is a blocking call to CBC. The solver writes progress to a log file — that is the only progress signal. There is no API for mid-solve callbacks or progress hooks. A callback-based approach (`on_progress(percent)`) would only fire before and after the solve, not during.

## Why `@st.fragment`?

The original implementation used a manual `while` loop with `time.sleep(2)`, a `queue.Queue` for status, and regex parsing of the log file — all inside `assignments_tab.py`, which blocked the whole script while CBC solved. `@st.fragment(run_every=2)` is Streamlit's built-in mechanism for periodic UI updates. It replaces the manual polling loop and keeps the UI responsive without blocking the main script: the fragment re-runs on its own timer, polls `SolveRun.progress()`, and re-renders only its own subtree.

## Architecture

The monitoring splits into two layers:

1. **Service layer** (`solve_run.py`) — the `SolveRun` seam runs the solve in a background thread, reads the CBC log, and exposes `progress()` (a `SolveProgress` snapshot: running, percent, message, log_text, timed_out) and `result()`. Percent is computed here (time-based, via the pure `percent_from_elapsed`/`detect_timeout` helpers), not stored on `SolverStatus`. No Streamlit imports.
2. **UI layer** (`app/tabs/`) — polls `SolveRun.progress()`/`result()` and renders progress widgets. Never touches the log file or manages threads.

## Implementation status

**Fully implemented.** The service-layer seam landed in #73: `SolveRun` (in `solve_run.py`) owns the thread and log reading, so the UI no longer imports `threading`/`queue` or reads the log file. #61 completed the migration: the active `SolveRun` lives in `session_state`, the UI polls it via `@st.fragment(run_every=2)` instead of a blocking `while`/`sleep` loop, the run's presence *is* a single-run guard (the Assign button is disabled while a solve is in flight), and the fragment self-terminates by finalizing the result and triggering a full-script rerun once the solve completes. The broken "Stop" button and the last orchestration global (`log_counter`) were removed (Stop deferral: ADR-0008 / #74).

## Consequences

- The UI never imports `threading`, `queue`, or reads log files directly, and holds no orchestration globals — the single active `SolveRun` lives in `session_state`.
- Exactly one solve runs at a time: the active run's presence both drives the polling fragment and disables the Assign button, so concurrent CBC solves are impossible (resolves the #61 OOM risk).
- `finalize_solve` stashes the final CBC log into `session_state` as the run is cleared, so the done view keeps a collapsed (chronological, non-live) "solver logs" expander for post-solve inspection after a solve or timeout — the live stream only exists while the run is in flight.
- `SolveProgress` and `SolverStatus` are plain dataclasses with no Streamlit dependency — testable without the UI (`tests/test_seatrades/test_solve_run.py`). The fragment's lifetime/guard logic is pulled into pure functions (`solve_view_state`, `finalize_solve`) tested without driving Streamlit timers (`tests/test_app/test_assignments_tab.py`, `test_assignments_guard.py`).
- Log-parsing regex and thread management moved from `assignments_tab.py` to `solve_run.py` (`SolveRun`).
- Future: if a solver with callback support replaces PuLP, the service layer can switch to callbacks without changing the UI layer.
