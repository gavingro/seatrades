"""Background solve orchestration — run a solve in a thread and observe its progress.

`SolveRun` is the service-layer seam that ADR-0004 mandates: it owns running
``solver.run`` in a background thread and watching the CBC log, so the UI never
imports ``threading``/``queue`` or reads the log file. The UI constructs a
``SolveRun``, calls ``start()``, polls ``progress()``/``result()``, and renders.
"""

import re

_TIMEOUT_LOG_PATTERN = re.compile(r"Result - Stopped on time limit")


def percent_from_elapsed(elapsed: float, time_limit: float) -> float:
    """Fraction of the solver time limit elapsed, capped at 1.0."""
    return min(elapsed / time_limit, 1.0)


def detect_timeout(log_text: str) -> bool:
    """Whether the CBC log shows the solve stopped on its time limit."""
    return bool(_TIMEOUT_LOG_PATTERN.search(log_text))
