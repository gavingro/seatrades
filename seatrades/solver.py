"""Solver entry point — build, solve, and extract assignments."""

import re
from pathlib import Path
from typing import Optional

import pandas as pd
import pulp

from seatrades.config import OptimizationConfig
from seatrades.live_cbc_log import live_cbc_log
from seatrades.problem import SchedulingProblem
from seatrades.results import AssignmentSolution, SolverStatus

_GAP_PATTERN = re.compile(r"(?<=Gap:                            )(\d+\.?\d*)")
_TIMEOUT_LOG_PATTERN = re.compile(r"Result - Stopped on time limit")


def detect_timeout(log_text: str) -> bool:
    """Whether the CBC log shows the solve stopped on its time limit."""
    return bool(_TIMEOUT_LOG_PATTERN.search(log_text))


def _mangle(name: str) -> str:
    """Mangle a name to match PuLP's internal variable naming.

    Uses PuLP's own translation table so the mapping stays in sync
    if PuLP ever changes which characters it replaces.
    """
    return name.translate(pulp.LpVariable.trans)


def _extract_camper_assignments(
    variables: list[pulp.LpVariable],
    campers: list[int],
    seatrades_full: list[str],
) -> pd.DataFrame:
    """Extract camper assignment values from solved LpProblem variables.

    Looks up each (camper, seatrade_full) variable by its PuLP-mangled name
    rather than parsing variable names, avoiding breakage on spaces/dots.
    Campers are integer IDs; they are stringified to build the variable name.
    """
    var_lookup = {v.name: pulp.value(v) for v in variables}
    camper_vars: dict[int, dict[str, float]] = {}
    expected = len(campers) * len(seatrades_full)
    found = 0
    for camper in campers:
        camper_vars[camper] = {}
        for seatrade_name in seatrades_full:
            var_name = f"Camper_Assignments_{_mangle(str(camper))}_{_mangle(seatrade_name)}"
            if var_name in var_lookup:
                found += 1
            camper_vars[camper][seatrade_name] = var_lookup.get(var_name, 0.0)
    if found != expected:
        raise ValueError(f"Expected {expected} assignment variables, found {found}")
    return pd.DataFrame(camper_vars).transpose()


def _read_log_text(log_path: Path) -> str:
    """CBC log contents, or '' if the log isn't there yet / can't be read."""
    try:
        return log_path.read_text()
    except (FileNotFoundError, OSError):
        return ""


def _extract_gap_from_log(log_path: Path) -> Optional[float]:
    """Parse the MIP gap from the CBC solver log file.

    Returns the gap as a float (e.g. 0.05 for 5%) or None if not found.
    """
    match = _GAP_PATTERN.search(_read_log_text(log_path))
    return float(match.group(1)) if match else None


def run(problem: SchedulingProblem, config: OptimizationConfig) -> AssignmentSolution:
    """Build and solve a scheduling problem, returning an AssignmentSolution."""
    lp_problem = problem.build(config)
    # Tee cbc's log through a pty so it streams line-by-line instead of block-buffering
    # to a plain file. Exiting the context drains the reader, so the log is complete
    # before we read it below.
    with live_cbc_log(config.solver, config.log_path):
        status_code = lp_problem.solve(config.solver)

    assignments = _extract_camper_assignments(lp_problem.variables(), problem.campers, problem.seatrades_full)
    assignments.index.name = "camper_id"

    solver_status = SolverStatus.from_pulp(status_code)
    if solver_status.is_optimal:
        solver_status.gap = _extract_gap_from_log(config.log_path)
        # A gap-closed solve holds no "Stopped on time limit" line; an incumbent kept when
        # CBC hit the limit does — carry that stop reason onto the final status so the
        # success banner can tell a proven result from a stopped-on-time one.
        solver_status.timed_out = detect_timeout(_read_log_text(config.log_path))

    # camper_id -> camper_name translation map; ids stay internal, names go out.
    camper_names = pd.Series(problem.camper_names, index=pd.Index(problem.camper_ids, name="camper_id"))

    return AssignmentSolution(
        assignments=assignments,
        status=solver_status,
        cabins=problem.cabins,
        campers=problem.camper_names,
        seatrades_full=problem.seatrades_full,
        cabin_camper_prefs=problem.cabin_camper_prefs,
        camper_prefs=problem.camper_prefs,
        camper_names=camper_names,
    )
