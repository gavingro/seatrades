"""Solver entry point — build, solve, and extract assignments."""

import re
from pathlib import Path
from typing import Optional

import pandas as pd
import pulp

from seatrades import diagnostics
from seatrades.config import OptimizationConfig
from seatrades.diagnostics import Finding, Tier
from seatrades.live_cbc_log import live_cbc_log
from seatrades.problem import SchedulingProblem
from seatrades.results import AssignmentSolution, SolverState, SolverStatus

_GAP_PATTERN = re.compile(r"(?<=Gap:                            )(\d+\.?\d*)")
_TIMEOUT_LOG_PATTERN = re.compile(r"Result - Stopped on time limit")

# CBC proves infeasibility fast once the model is instantiated, so each relaxation
# re-solve is capped well below the full solve budget: a still-infeasible drop returns
# quickly, a now-feasible one finds a schedule. A bounded probe, not the real solve.
_RELAXATION_TIME_LIMIT_S = 8

# Each relationship group's hard constraints share a name prefix in the built model,
# and the pairs it was built from live on the problem. Dropping a group and re-solving
# tests whether that group alone is what makes the problem infeasible.
_RELATIONSHIP_GROUPS = [
    ("besties", "besties_", "besties_pairs"),
    ("friends", "friends_", "friends_pairs"),
    ("frenemies", "frenemies_", "frenemies_pairs"),
]


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
    except OSError:  # includes FileNotFoundError
        return ""


def _extract_gap_from_log(log_path: Path) -> Optional[float]:
    """Parse the MIP gap from the CBC solver log file.

    Returns the gap as a float (e.g. 0.05 for 5%) or None if not found.
    """
    match = _GAP_PATTERN.search(_read_log_text(log_path))
    return float(match.group(1)) if match else None


def diagnose_infeasibility(
    status: SolverStatus, problem: SchedulingProblem, config: OptimizationConfig
) -> list[Finding]:
    """The single post-mortem call site: explain an infeasible solve, else nothing.

    Diagnosis is a pure post-mortem — it runs *only* when the solver proved the
    problem INFEASIBLE, never on a proven/stopped OPTIMAL result and never on a
    TIMEOUT (which is feasible, just unfinished). Feeds the diagnostics module the
    joined domain data the problem already parsed plus the config knobs it needs.
    """
    if status.state != SolverState.INFEASIBLE:
        return []
    findings = diagnostics.diagnose(
        problem.cabin_camper_prefs.reset_index(),
        problem.seatrades_prefs.reset_index(),
        relationships=problem.relationships,
        max_seatrades_per_fleet=config.max_seatrades_per_fleet,
        max_cabin_share_per_seatrade=config.max_cabin_share_per_seatrade,
    )
    # The pure checks (named + matching backstop) explained it — no re-solve needed.
    if findings:
        return findings
    # Last resort: they came up empty, so drop each relationship group in turn and see
    # if the solve flips feasible, pointing at the group that makes it infeasible.
    return _relaxation_resolve(problem, config)


def _relaxation_solver() -> pulp.apis.LpSolver:
    """A short-capped CBC for relaxation re-solves — bounded, not the full solve budget."""
    return pulp.apis.PULP_CBC_CMD(timeLimit=_RELAXATION_TIME_LIMIT_S, msg=0)


def _relaxation_resolve(problem: SchedulingProblem, config: OptimizationConfig) -> list[Finding]:
    """Drop one relationship group at a time; if the solve flips feasible, name the group.

    Runs only when the pure checks found nothing. Removing a group and getting a feasible
    solve proves that group is load-bearing for the infeasibility (it belongs to a minimal
    infeasible subset), so the finding is PROVEN — it names the group, not exact campers.
    Skips groups the problem has no pairs for, and stops at the first group that flips.
    """
    for group, prefix, pairs_attr in _RELATIONSHIP_GROUPS:
        if not getattr(problem, pairs_attr):
            continue
        if not _flips_feasible_without(problem, config, prefix):
            continue
        return [
            Finding(
                tier=Tier.PROVEN,
                cause=(
                    f"Removing the {group} relationships lets a schedule form, so those "
                    f"relationships are what make this infeasible — some combination of them "
                    "can't all be satisfied together, though no single named cause pins it down."
                ),
                fix=(
                    f"Review the {group} links and drop or loosen one — the exact pair the "
                    "named checks couldn't isolate is somewhere in that group."
                ),
            )
        ]
    return []


def _relaxed_solve_found_schedule(status_code: int) -> bool:
    """Whether a relaxation re-solve actually produced a feasible schedule.

    Only an OPTIMAL outcome means CBC returned a valid schedule — proven, or an
    incumbent it kept when it stopped on the cap (CBC reports code 1 the instant it
    holds a valid solution). A TIMEOUT means it found *no* usable schedule in the
    cap, and INFEASIBLE means dropping the group didn't help; neither demonstrates a
    schedule, so the group isn't named. Stricter than "not infeasible" on purpose — a
    bare timeout must not overclaim PROVEN that dropping the group lets a schedule form.
    """
    return SolverState.from_pulp(status_code) is SolverState.OPTIMAL


def _flips_feasible_without(problem: SchedulingProblem, config: OptimizationConfig, prefix: str) -> bool:
    """Whether the model finds a schedule once every constraint named ``prefix*`` is dropped.

    Rebuilds a fresh model (so the probe never mutates the real one), deletes the group's
    constraints by name, and re-solves under the bounded relaxation cap. Only an OPTIMAL
    re-solve — CBC returned an actual schedule — means dropping the group relieved the
    infeasibility, so the group is implicated (see ``_relaxed_solve_found_schedule``).
    """
    lp = problem.build(config)
    for name in [name for name in lp.constraints if name.startswith(prefix)]:
        del lp.constraints[name]
    status_code = lp.solve(_relaxation_solver())
    return _relaxed_solve_found_schedule(status_code)


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
        findings=diagnose_infeasibility(solver_status, problem, config),
    )
