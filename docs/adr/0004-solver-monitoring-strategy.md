# Solver monitoring: log-polling with Streamlit fragments

The solver runs in a background thread. Progress is reported by reading the CBC log file and surfacing structured status to the UI via `@st.fragment` polling.

**Status: accepted**

## Why not callbacks?

PuLP's `.solve()` is a blocking call to CBC. The solver writes progress to a log file — that is the only progress signal. There is no API for mid-solve callbacks or progress hooks. A callback-based approach (`on_progress(percent)`) would only fire before and after the solve, not during.

## Why `@st.fragment`?

The current implementation uses a manual `while` loop with `time.sleep(2)`, a `queue.Queue` for status, and regex parsing of the log file — all inside `assignments_tab.py`. `@st.fragment(run_every=timedelta(seconds=2))` is Streamlit's built-in mechanism for periodic UI updates. It replaces the manual polling loop and keeps the UI responsive without blocking the main script.

## Architecture

The monitoring splits into two layers:

1. **Service layer** (`solver.py`) — runs the solver in a background thread, reads the CBC log, writes structured progress to a `SolverStatus` object (percent, message, state). No Streamlit imports.
2. **UI layer** (`app/tabs/`) — `@st.fragment` reads `SolverStatus` from session state and renders progress widgets. Never touches the log file or manages threads.

## Consequences

- The UI never imports `threading`, `queue`, or reads log files directly.
- `SolverStatus` is a plain dataclass with no Streamlit dependency — testable without the UI.
- Log-parsing regex and thread management move from `assignments_tab.py` to `solver.py`.
- Future: if a solver with callback support replaces PuLP, the service layer can switch to callbacks without changing the UI layer.
