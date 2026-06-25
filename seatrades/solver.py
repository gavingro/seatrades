"""Solver entry point — build, solve, and extract assignments."""

import re
from pathlib import Path
from typing import Optional

import pandas as pd
import pulp

from seatrades.config import OptimizationConfig
from seatrades.problem import SchedulingProblem
from seatrades.results import AssignmentSolution, SolverStatus

_GAP_PATTERN = re.compile(r"(?<=Gap:                            )(\d+\.?\d*)")


def _mangle(name: str) -> str:
    """Mangle a name to match PuLP's internal variable naming.

    Uses PuLP's own translation table so the mapping stays in sync
    if PuLP ever changes which characters it replaces.
    """
    return name.translate(pulp.LpVariable.trans)


def _extract_camper_assignments(
    variables: list[pulp.LpVariable],
    campers: list[str],
    seatrades_full: list[str],
) -> pd.DataFrame:
    """Extract camper assignment values from solved LpProblem variables.

    Looks up each (camper, seatrade_full) variable by its PuLP-mangled name
    rather than parsing variable names, avoiding breakage on spaces/dots.
    """
    var_lookup = {v.name: pulp.value(v) for v in variables}
    camper_vars: dict[str, dict[str, float]] = {}
    expected = len(campers) * len(seatrades_full)
    found = 0
    for camper in campers:
        camper_vars[camper] = {}
        for seatrade_name in seatrades_full:
            var_name = f"Camper_Assignments_{_mangle(camper)}_{_mangle(seatrade_name)}"
            if var_name in var_lookup:
                found += 1
            camper_vars[camper][seatrade_name] = var_lookup.get(var_name, 0.0)
    if found != expected:
        raise ValueError(f"Expected {expected} assignment variables, found {found}")
    return pd.DataFrame(camper_vars).transpose()


def _extract_gap_from_log(log_path: Path) -> Optional[float]:
    """Parse the MIP gap from the CBC solver log file.

    Returns the gap as a float (e.g. 0.05 for 5%) or None if not found.
    """
    try:
        text = log_path.read_text()
    except (FileNotFoundError, OSError):
        return None
    match = _GAP_PATTERN.search(text)
    return float(match.group(1)) if match else None


def run(problem: SchedulingProblem, config: OptimizationConfig) -> AssignmentSolution:
    """Build and solve a scheduling problem, returning an AssignmentSolution.

    Parameters
    ----------
    problem : SchedulingProblem
        The scheduling problem containing domain data.
    config : OptimizationConfig
        Optimization weights and solver configuration.

    Returns
    -------
    AssignmentSolution
        The solved assignment with status and domain data.
    """
    lp_problem = problem.build(config)
    status_code = lp_problem.solve(config.solver)

    assignments = _extract_camper_assignments(lp_problem.variables(), problem.campers, problem.seatrades_full)

    solver_status = SolverStatus.from_pulp(status_code)
    if solver_status.is_optimal:
        solver_status.gap = _extract_gap_from_log(config.log_path)

    return AssignmentSolution(
        assignments=assignments,
        status=solver_status,
        cabins=problem.cabins,
        campers=problem.campers,
        seatrades_full=problem.seatrades_full,
        cabin_camper_prefs=problem.cabin_camper_prefs,
        camper_prefs=problem.camper_prefs,
    )
