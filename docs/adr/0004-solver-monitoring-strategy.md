# Solver monitoring: log-polling with Streamlit fragments

The solver runs in a background thread. Progress is reported by reading the CBC log file and surfacing structured status to the UI via `@st.fragment` polling.

**Status: accepted**

## Why not callbacks?

PuLP's `.solve()` is a blocking call to CBC. The solver writes progress to a log file — that is the only progress signal. There is no API for mid-solve callbacks or progress hooks. A callback-based approach (`on_progress(percent)`) would only fire before and after the solve, not during.

## Why `@st.fragment`?

The original implementation used a manual `while` loop with `time.sleep(2)`, a `queue.Queue` for status, and regex parsing of the log file — all inside `assignments_tab.py`, which blocked the whole script while CBC solved. `@st.fragment(run_every=2)` is Streamlit's built-in mechanism for periodic UI updates. It replaces the manual polling loop and keeps the UI responsive without blocking the main script: the fragment re-runs on its own timer, polls `SolveRun.progress()`, and re-renders only its own subtree.

## Architecture

The monitoring splits into two layers:

1. **Service layer** (`solve_run.py`) — the `SolveRun` seam runs the solve in a background thread, reads the CBC log, and exposes `progress()` (a `SolveProgress` snapshot: running, percent, message, log_text, timed_out) and `result()`. Percent is computed here (time-based, via the pure `percent_from_elapsed` helper), not stored on `SolverStatus`. The CBC-log parsers themselves (`detect_timeout`, the gap regex) live in `solver.py` beside the other log parsers; `progress()` calls `solver.detect_timeout` (#110). No Streamlit imports.
2. **UI layer** (`app/tabs/`) — polls `SolveRun.progress()`/`result()` and renders progress widgets. Never touches the log file or manages threads.

## Live streaming: give cbc a pty (#100)

The log-polling above only shows live progress if the log file actually grows during the
solve. It didn't: cbc is a C++ binary, and when its stdout is a plain file, C stdio
block-buffers (~8 KB), so the file stayed frozen (often at 0 bytes) until cbc exited — the
"technical details" panel looked hung for up to the full time limit.

Fix (`seatrades/live_cbc_log.py`): give cbc a **pty** instead of a plain file. On a tty,
C stdio line-buffers, so each line flushes as produced. The `live_cbc_log` context manager
sets the solver's `logPath` option to the pty's **slave fd** (PuLP opens `logPath` with a
bare `open(...)`, and `open()` accepts an integer fd — so cbc gets a tty with no PuLP
subclassing), and a background reader tees the pty output into the configured log file,
normalizing the line discipline's `\r\n` back to `\n`. `solver.run` wraps just the
`lp_problem.solve(...)` call in this context manager, so the reader is drained on exit
*before* the MIP-gap is parsed from the log. Unix-only (macOS + Linux CI); Windows is out
of scope (`pty` is Unix-only).

## Implementation status

**Fully implemented.** The service-layer seam landed in #73: `SolveRun` (in `solve_run.py`) owns the thread and log reading, so the UI no longer imports `threading`/`queue` or reads the log file. #61 completed the migration: the active `SolveRun` lives in `session_state`, the UI polls it via `@st.fragment(run_every=2)` instead of a blocking `while`/`sleep` loop, the run's presence *is* a single-run guard (the Assign button is disabled while a solve is in flight), and the fragment self-terminates by finalizing the result and triggering a full-script rerun once the solve completes. The broken "Stop" button and the last orchestration global (`log_counter`) were removed (Stop deferral: ADR-0008 / #74).

## Consequences

- The UI never imports `threading`, `queue`, or reads log files directly, and holds no orchestration globals — the single active `SolveRun` lives in `session_state`.
- Exactly one solve runs at a time: the active run's presence both drives the polling fragment and disables the Assign button, so concurrent CBC solves are impossible (resolves the #61 OOM risk).
- `finalize_solve` stashes the final CBC log into `session_state` as the run is cleared, so the done view keeps a collapsed (chronological, non-live) "solver logs" expander for post-solve inspection after a solve or timeout — the live stream only exists while the run is in flight (and streams line-by-line via the pty tee above, not block-buffered).
- `SolveProgress` and `SolverStatus` are plain dataclasses with no Streamlit dependency — testable without the UI (`tests/test_seatrades/test_solve_run.py`). The fragment's lifetime/guard logic is pulled into pure functions (`solve_view_state`, `finalize_solve`) tested without driving Streamlit timers (`tests/test_app/test_assignments_tab.py`, `test_assignments_guard.py`).
- Thread management moved from `assignments_tab.py` to `solve_run.py` (`SolveRun`); the CBC-log parsing regexes (`detect_timeout`, gap) live in `solver.py` beside the other log parsers (#110), called from `solve_run.py`.
- Future: if a solver with callback support replaces PuLP, the service layer can switch to callbacks without changing the UI layer.
