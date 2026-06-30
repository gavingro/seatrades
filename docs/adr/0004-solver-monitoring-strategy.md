# Solver monitoring: log-polling with Streamlit fragments

The solver runs in a background thread. Progress is reported by reading the CBC log file and surfacing structured status to the UI via `@st.fragment` polling.

**Status: accepted**

## Why not callbacks?

PuLP's `.solve()` is a blocking call to CBC. The solver writes progress to a log file — that is the only progress signal. There is no API for mid-solve callbacks or progress hooks. A callback-based approach (`on_progress(percent)`) would only fire before and after the solve, not during.

## Why `@st.fragment`?

The current implementation uses a manual `while` loop with `time.sleep(2)`, a `queue.Queue` for status, and regex parsing of the log file — all inside `assignments_tab.py`. `@st.fragment(run_every=timedelta(seconds=2))` is Streamlit's built-in mechanism for periodic UI updates. It replaces the manual polling loop and keeps the UI responsive without blocking the main script.

## Architecture

The monitoring splits into two layers:

1. **Service layer** (`solve_run.py`) — the `SolveRun` seam runs the solve in a background thread, reads the CBC log, and exposes `progress()` (a `SolveProgress` snapshot: running, percent, message, log_text, timed_out) and `result()`. Percent is computed here (time-based, via the pure `percent_from_elapsed`/`detect_timeout` helpers), not stored on `SolverStatus`. No Streamlit imports.
2. **UI layer** (`app/tabs/`) — polls `SolveRun.progress()`/`result()` and renders progress widgets. Never touches the log file or manages threads.

## Implementation status

The service-layer seam landed in #73: `SolveRun` (in `solve_run.py`) now owns the thread and log reading, so the UI no longer imports `threading`/`queue` or reads the log file. The UI still polls via a `while` + `time.sleep(2)` loop reading `progress()`/`result()`; swapping that loop for `@st.fragment(run_every=...)` and moving `SolveRun` into `session_state` is the remaining step toward this ADR's end-state, tracked in #61.

## Consequences

- The UI never imports `threading`, `queue`, or reads log files directly.
- `SolveProgress` and `SolverStatus` are plain dataclasses with no Streamlit dependency — testable without the UI (`tests/test_seatrades/test_solve_run.py`).
- Log-parsing regex and thread management moved from `assignments_tab.py` to `solve_run.py` (`SolveRun`).
- Future: if a solver with callback support replaces PuLP, the service layer can switch to callbacks without changing the UI layer.
