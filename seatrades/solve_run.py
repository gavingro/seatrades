"""Background solve orchestration — run a solve in a thread and observe its progress.

`SolveRun` is the service-layer seam that ADR-0004 mandates: it owns running
``solver.run`` in a background thread and watching the CBC log, so the UI never
imports ``threading``/``queue`` or reads the log file. The UI constructs a
``SolveRun``, calls ``start()``, polls ``progress()``/``result()``, and renders.
"""

import re
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import pandas as pd

from seatrades import solver
from seatrades.config import OptimizationConfig
from seatrades.problem import SchedulingProblem
from seatrades.results import AssignmentSolution, SolverState, SolverStatus

_TIMEOUT_LOG_PATTERN = re.compile(r"Result - Stopped on time limit")

_OPTIMIZING_MESSAGE = "Optimizing seatrade assignments…"
_TIMEOUT_MESSAGE = "Finishing up — time limit reached…"


def percent_from_elapsed(elapsed: float, time_limit: float) -> float:
    """Fraction of the solver time limit elapsed, capped at 1.0."""
    return min(elapsed / time_limit, 1.0)


def detect_timeout(log_text: str) -> bool:
    """Whether the CBC log shows the solve stopped on its time limit."""
    return bool(_TIMEOUT_LOG_PATTERN.search(log_text))


@dataclass
class SolveProgress:
    """A snapshot of an in-flight (or finished) solve, observed via the CBC log."""

    running: bool
    percent: float
    message: str
    log_text: str
    timed_out: bool


class SolveRun:
    """Runs ``solve_fn(problem, config)`` in a background thread and watches the log.

    Construction is side-effect-free. ``start()`` owns the side effects (clear the
    log, record the start time, spawn the thread). ``progress()`` and ``result()``
    are cheap and idempotent so the caller can poll them from a ``while`` loop or a
    Streamlit fragment.
    """

    def __init__(
        self,
        problem: SchedulingProblem,
        config: OptimizationConfig,
        solve_fn: Callable[[SchedulingProblem, OptimizationConfig], AssignmentSolution] = solver.run,
    ) -> None:
        self._problem = problem
        self._config = config
        self._solve_fn = solve_fn
        self._thread: Optional[threading.Thread] = None
        self._start_time: Optional[float] = None
        self._result: Optional[AssignmentSolution] = None

    def start(self) -> None:
        """Clear the log, record the start time, and spawn the solver thread."""
        self._config.log_path.unlink(missing_ok=True)
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._solve, daemon=True)
        self._thread.start()

    def progress(self) -> SolveProgress:
        """Cheap, idempotent snapshot: thread-alive + elapsed time + log contents."""
        running = self._thread is not None and self._thread.is_alive()
        elapsed = time.time() - self._start_time if self._start_time is not None else 0.0
        time_limit = self._config.solver.timeLimit
        log_text = self._read_log()
        timed_out = detect_timeout(log_text) or elapsed > time_limit
        return SolveProgress(
            running=running,
            percent=percent_from_elapsed(elapsed, time_limit),
            message=_TIMEOUT_MESSAGE if timed_out else _OPTIMIZING_MESSAGE,
            log_text=log_text,
            timed_out=timed_out,
        )

    def result(self) -> Optional[AssignmentSolution]:
        """The finished solution, or None while the solve is still running."""
        return self._result

    def _solve(self) -> None:
        """Thread target: run the solve, turning any crash into an ERROR solution."""
        try:
            self._result = self._solve_fn(self._problem, self._config)
        except Exception as exc:  # noqa: BLE001 — any solver crash becomes an ERROR result
            self._result = self._error_solution(str(exc))

    def _error_solution(self, message: str) -> AssignmentSolution:
        """Synthesize an ERROR solution from the held problem and a crash message.

        Mirrors how ``solver.run`` assembles an AssignmentSolution, but with empty
        assignments — so the UI sees one status-keyed code path for crashes.
        """
        camper_names = pd.Series(
            self._problem.camper_names,
            index=pd.Index(self._problem.camper_ids, name="camper_id"),
        )
        return AssignmentSolution(
            assignments=pd.DataFrame(),
            status=SolverStatus(state=SolverState.ERROR, message=message),
            cabins=self._problem.cabins,
            campers=self._problem.camper_names,
            seatrades_full=self._problem.seatrades_full,
            cabin_camper_prefs=self._problem.cabin_camper_prefs,
            camper_prefs=self._problem.camper_prefs,
            camper_names=camper_names,
        )

    def _read_log(self) -> str:
        """Raw CBC log contents (chronological); '' if the log isn't there yet."""
        try:
            return self._config.log_path.read_text()
        except (FileNotFoundError, OSError):
            return ""
