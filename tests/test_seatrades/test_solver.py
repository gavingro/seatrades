"""Tests for seatrades.solver — the solver.run() entry point."""

import itertools
from collections.abc import Sequence

import pandas as pd
import pulp
import pytest

from seatrades.config import OptimizationConfig
from seatrades.diagnostics import Finding, Tier
from seatrades.preferences import validate_relationships
from seatrades.problem import SchedulingProblem, seatrade_name
from seatrades.results import (
    AssignmentSolution,
    SolverState,
    SolverStatus,
    wrangle_assignments_to_longform,
    wrangle_assignments_to_wideform,
)
from seatrades.simulation import simulate_camper_relationships
from seatrades.solver import (
    _RELATIONSHIP_GROUPS,
    _RELAXATION_TIME_LIMIT_S,
    _relaxation_solver,
    _relaxed_solve_found_schedule,
    detect_timeout,
    diagnose_infeasibility,
    run,
)


class TestDetectTimeout:
    def test_true_when_log_has_time_limit_line(self):
        """CBC's time-limit line marks the solve as timed out."""
        log_text = "Cbc0010I After 0 nodes\nResult - Stopped on time limit\nTotal time 60.0"
        assert detect_timeout(log_text) is True

    def test_false_when_log_lacks_time_limit_line(self):
        """A normal optimal log is not a timeout."""
        log_text = "Result - Optimal solution found\nObjective value 42.0"
        assert detect_timeout(log_text) is False


def _oversubscribed_problem() -> SchedulingProblem:
    """12 campers all wanting 4 seatrades that seat 1 each — a capacity shortfall.

    2·Σcampers_max = 2·4 = 8 seats < 12 campers, so the P1 check fires.
    """
    seatrades = ["Archery", "Crafts", "Climbing", "Sailing"]
    joined_campers = pd.DataFrame(
        [
            {
                "camper_id": i,
                "cabin": "Cabin1",
                "camper": f"Camper {i}",
                "gender": "F",
                "age": 14,
                "seatrade_1": seatrades[0],
                "seatrade_2": seatrades[1],
                "seatrade_3": seatrades[2],
                "seatrade_4": seatrades[3],
            }
            for i in range(12)
        ]
    )
    seatrade_setup = pd.DataFrame({"seatrade": seatrades, "campers_min": 0, "campers_max": 1})
    return SchedulingProblem(joined_campers, seatrade_setup)


def _roster_problem(rows: list[dict], seatrade_setup: pd.DataFrame, relationships=None) -> SchedulingProblem:
    """Build a SchedulingProblem from explicit (cabin, camper, prefs) rows.

    Fills the identity columns the solver needs (gender/age) with defaults; each
    row supplies its four ranked seatrades so a crafted cause can be reproduced.
    """
    joined = pd.DataFrame(
        [
            {
                "camper_id": i,
                "cabin": row["cabin"],
                "camper": row["camper"],
                "gender": row.get("gender", "F"),
                "age": row.get("age", 14),
                "seatrade_1": row["prefs"][0],
                "seatrade_2": row["prefs"][1],
                "seatrade_3": row["prefs"][2],
                "seatrade_4": row["prefs"][3],
            }
            for i, row in enumerate(rows)
        ]
    )
    return SchedulingProblem(joined, seatrade_setup, relationships=relationships)


_POPULAR = ["Sailing", "Kayaking", "Rowing", "Canoeing"]


def _crowd(cabin: str, n: int) -> list[dict]:
    """n campers all wanting the four popular seatrades — healthy filler that runs."""
    return [{"cabin": cabin, "camper": f"Crowd {i}", "prefs": _POPULAR} for i in range(n)]


class TestDiagnoseInfeasibility:
    """The single post-mortem call site: diagnosis runs only on INFEASIBLE."""

    def test_names_the_capacity_cause_on_infeasible(self):
        problem = _oversubscribed_problem()
        findings = diagnose_infeasibility(SolverStatus(state=SolverState.INFEASIBLE), problem, OptimizationConfig())
        assert findings, "an oversubscribed infeasible solve should be explained"
        assert "campers" in findings[0].cause.lower()

    def test_not_run_on_optimal(self):
        problem = _oversubscribed_problem()
        assert diagnose_infeasibility(SolverStatus(state=SolverState.OPTIMAL), problem, OptimizationConfig()) == []

    def test_not_run_on_timeout(self):
        problem = _oversubscribed_problem()
        status = SolverStatus(state=SolverState.TIMEOUT, timed_out=True)
        assert diagnose_infeasibility(status, problem, OptimizationConfig()) == []

    @pytest.mark.slow
    def test_real_solver_confirms_the_capacity_shortfall(self):
        """Reality check: the real solver returns INFEASIBLE on this fixture and the
        capacity check agrees — proving the mode is real, not just a structural guess."""
        solution = run(_oversubscribed_problem(), OptimizationConfig())
        assert solution.status.state is SolverState.INFEASIBLE
        assert any("Too many campers" in f.cause for f in solution.findings)


def _frenemies_cycle_problem() -> SchedulingProblem:
    """Five same-cabin frenemies wired in a 5-cycle, ranking only two live seatrades.

    Their two other picks (C, D) are dead (``campers_min`` 6 > their popularity 5), so
    they can use only A and B. A cabin shares one block, so the five must take distinct
    seatrades where they are adjacent — but a 5-cycle needs three colours and only two
    seatrades exist, so it is infeasible. The cycle is *not* a clique, so the frenemies
    clash check stays quiet, and the backstop ignores frenemies coupling, so it too is
    quiet — leaving the relaxation re-solve as the only thing that can name the cause.
    """
    names = [f"Fr{i}" for i in range(5)]
    rows = [{"cabin": "Otter", "camper": n, "prefs": ["A", "B", "C", "D"]} for n in names]
    setup = pd.DataFrame({"seatrade": ["A", "B", "C", "D"], "campers_min": [0, 0, 6, 6], "campers_max": 10})
    cycle = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 0)]
    rels = pd.DataFrame(
        [("Otter", names[a], "Otter", names[b], "frenemies") for a, b in cycle],
        columns=["cabin_1", "camper_1", "cabin_2", "camper_2", "relationship"],
    )
    return _roster_problem(rows, setup, relationships=rels)


class TestRelaxationResolve:
    """The as-needed fallback: drop a relationship group, see if the solve flips feasible."""

    def test_resolve_is_time_capped_not_the_full_limit(self):
        """The re-solve uses a bounded ~5–10s cap, never the full solve time budget."""
        assert 5 <= _RELAXATION_TIME_LIMIT_S <= 10
        assert _relaxation_solver().timeLimit == _RELAXATION_TIME_LIMIT_S
        assert _relaxation_solver().timeLimit < OptimizationConfig().solver.timeLimit

    def test_only_an_optimal_re_solve_counts_as_a_flip(self):
        """A flip is a schedule actually found (OPTIMAL) — not a bare timeout.

        CBC reports code 1 the instant it holds a valid schedule (proven or an
        incumbent kept at the cap), and code 0 only when it found *no* usable
        schedule in the cap. So a timeout is not evidence the group lets a schedule
        form — naming it there would overclaim PROVEN. Only OPTIMAL is a real flip;
        TIMEOUT (no schedule) and still-INFEASIBLE (drop didn't help) are not.
        """
        assert _relaxed_solve_found_schedule(1)  # OPTIMAL — a schedule was found
        assert not _relaxed_solve_found_schedule(0)  # TIMEOUT — no schedule found
        assert not _relaxed_solve_found_schedule(-1)  # INFEASIBLE — drop didn't help

    def test_relationship_group_prefixes_match_built_constraint_names(self):
        """Each ``_RELATIONSHIP_GROUPS`` prefix must name real constraints in the model.

        The relaxation re-solve deletes a group's constraints by ``name.startswith(prefix)``
        and its ``pairs_attr`` off the problem. Both are an unenforced convention shared with
        ``problem.py``'s constraint naming — if a prefix (or attr) drifts, ``_flips_feasible_without``
        silently deletes nothing, never flips feasible, and the fallback names no cause with no
        error. Guard the contract: with a pair of every relationship type present, each prefix
        matches ≥1 constraint and each ``pairs_attr`` is non-empty.
        """
        rows = [
            {"cabin": "Otter", "camper": "a", "prefs": ["A", "B", "C", "D"]},
            {"cabin": "Otter", "camper": "b", "prefs": ["A", "B", "C", "D"]},
            {"cabin": "Otter", "camper": "c", "prefs": ["A", "B", "C", "D"]},
            {"cabin": "Otter", "camper": "d", "prefs": ["A", "B", "C", "D"]},
            {"cabin": "Seal", "camper": "e", "prefs": ["A", "B", "C", "D"]},
        ]
        setup = pd.DataFrame({"seatrade": ["A", "B", "C", "D"], "campers_min": 0, "campers_max": 10})
        rels = _rel(
            [
                ("Otter", "a", "Otter", "b", "besties"),
                ("Otter", "c", "Otter", "d", "friends"),
                ("Seal", "e", "Otter", "a", "frenemies"),
            ]
        )
        problem = _roster_problem(rows, setup, relationships=rels)
        lp = problem.build(OptimizationConfig())
        for _group, prefix, pairs_attr in _RELATIONSHIP_GROUPS:
            assert getattr(problem, pairs_attr), f"no {pairs_attr} on the problem"
            assert any(name.startswith(prefix) for name in lp.constraints), f"no constraint named {prefix}*"

    def test_not_invoked_when_a_named_cause_already_fired(self, monkeypatch):
        """A named cause short-circuits the fallback — the re-solve never runs."""
        monkeypatch.setattr(
            "seatrades.solver._relaxation_resolve",
            lambda *_args, **_kwargs: pytest.fail("relaxation re-solve ran despite a named cause"),
        )
        findings = diagnose_infeasibility(
            SolverStatus(state=SolverState.INFEASIBLE), _oversubscribed_problem(), OptimizationConfig()
        )
        assert any("Too many campers" in f.cause for f in findings)

    def test_advisory_hints_alone_do_not_suppress_the_relaxation_resolve(self, monkeypatch):
        """Suspected pressure hints aren't a proven cause, so the fallback still runs.

        When only advisory hints fire, the proven relaxation result must lead and the
        hints ride below it — a suspected-only diagnosis must never short-circuit the
        re-solve the way a proven named cause does.
        """
        hint = Finding(tier=Tier.SUSPECTED, cause="something looks tight", fix="ease it")
        named = Finding(tier=Tier.PROVEN, cause="dropping frenemies lets a schedule form", fix="drop a link")
        monkeypatch.setattr("seatrades.solver.diagnostics.diagnose", lambda *_a, **_k: [hint])
        monkeypatch.setattr("seatrades.solver._relaxation_resolve", lambda *_a, **_k: [named])

        findings = diagnose_infeasibility(
            SolverStatus(state=SolverState.INFEASIBLE), _oversubscribed_problem(), OptimizationConfig()
        )

        assert findings[0] is named, "the proven relaxation result should lead"
        assert hint in findings, "the advisory hint should ride below the proven cause"

    @pytest.mark.slow
    def test_flips_feasible_re_solve_names_the_dropped_group(self):
        """Reality: an infeasibility no pure check sees, named by dropping frenemies.

        The real solver proves INFEASIBLE, the named checks and backstop come up empty
        (``diagnose`` returns nothing on its own), and dropping the frenemies group flips
        the solve feasible — so the fallback names frenemies as the load-bearing group.
        """
        problem = _frenemies_cycle_problem()
        solution = run(problem, OptimizationConfig())

        assert solution.status.state is SolverState.INFEASIBLE
        assert solution.findings, "the relaxation re-solve should name a cause"
        assert any("frenemies" in f.cause for f in solution.findings)


class TestMatchingBackstopReality:
    """Slow reality fixture: the real solver confirms the matching-backstop deficiency."""

    @pytest.mark.slow
    def test_real_solver_confirms_subset_deficiency_the_named_checks_miss(self):
        """Five campers over four seatrades seating one — 2·4 = 8 seats < 2·5 demand.

        Every named check stays quiet (the demand-1 capacity bound sees 5 ≤ 8, the picks
        are all live, no relationships), so only the matching backstop catches the
        demand-2 shortfall. The real solver agrees it is INFEASIBLE and the backstop names
        the deficient campers — proving the mode is real, not just a structural guess.
        """
        rows = [{"cabin": "Otter", "camper": f"Camper {i}", "prefs": ["A", "B", "C", "D"]} for i in range(5)]
        setup = pd.DataFrame({"seatrade": ["A", "B", "C", "D"], "campers_min": 0, "campers_max": 1})
        solution = run(_roster_problem(rows, setup), OptimizationConfig())

        assert solution.status.state is SolverState.INFEASIBLE
        assert any("can't all be placed" in f.cause and "Camper 0" in f.cause for f in solution.findings)


class TestStarvationReality:
    """Slow reality fixtures: the real solver confirms M1/M2 are genuine infeasibility."""

    def _starved_setup(self, niche: Sequence[str]) -> pd.DataFrame:
        seatrades = [*_POPULAR, *niche]
        # min campers 2: a seatrade only one camper ranks can never reach it, so it's dead.
        return pd.DataFrame({"seatrade": seatrades, "campers_min": 2, "campers_max": 10})

    @pytest.mark.slow
    def test_real_solver_confirms_starved_seatrade(self):
        """M1: a camper whose four picks are all solo-ranked niche seatrades can't be placed."""
        victim = {"cabin": "Cabin1", "camper": "Robin", "prefs": ["Whittling", "Birding", "Poetry", "Origami"]}
        problem = _roster_problem(_crowd("Cabin1", 6) + [victim], self._starved_setup(victim["prefs"]))

        solution = run(problem, OptimizationConfig())

        assert solution.status.state is SolverState.INFEASIBLE
        assert any("Robin" in f.cause and "too few seatrades" in f.cause for f in solution.findings)

    @pytest.mark.slow
    def test_real_solver_confirms_top2_both_starved(self):
        """M2: a camper whose top two picks are dead (but picks 3–4 live) breaks top-2."""
        victim = {"cabin": "Cabin1", "camper": "Robin", "prefs": ["Whittling", "Birding", "Sailing", "Kayaking"]}
        problem = _roster_problem(_crowd("Cabin1", 6) + [victim], self._starved_setup(["Whittling", "Birding"]))

        solution = run(problem, OptimizationConfig())

        assert solution.status.state is SolverState.INFEASIBLE
        assert any("Robin" in f.cause and "top two" in f.cause for f in solution.findings)


def _besties_rel(pairs: list[tuple[str, str, str, str]]) -> pd.DataFrame:
    """A besties relationships frame from (cabin_1, camper_1, cabin_2, camper_2) tuples."""
    return pd.DataFrame(
        [(*pair, "besties") for pair in pairs],
        columns=["cabin_1", "camper_1", "cabin_2", "camper_2", "relationship"],
    )


class TestBestiesReality:
    """Slow reality fixtures: the real solver confirms the besties causes B1/B2/B3."""

    def test_transitive_besties_chain_slips_validation_then_named_by_postmortem(self):
        """B1 / issue-112: a chain that is pairwise-valid but has no common pair.

        Validation checks besties only pairwise, so this passes it — then the solver
        proves INFEASIBLE and the post-mortem names the chain (the accepted trade of a
        single post-mortem seam). Not marked slow: it must always run to guard the seam.
        """
        rows = [
            {"cabin": "Otter", "camper": "Ash", "prefs": ["Sailing", "Kayaking", "Rowing", "Canoeing"]},
            {"cabin": "Otter", "camper": "Bo", "prefs": ["Sailing", "Kayaking", "Archery", "Crafts"]},
            {"cabin": "Otter", "camper": "Cy", "prefs": ["Kayaking", "Archery", "Climbing", "Dance"]},
        ]
        all_seatrades = sorted({s for row in rows for s in row["prefs"]})
        setup = pd.DataFrame({"seatrade": all_seatrades, "campers_min": 0, "campers_max": 10})
        rels = _besties_rel([("Otter", "Ash", "Otter", "Bo"), ("Otter", "Bo", "Otter", "Cy")])
        problem = _roster_problem(rows, setup, relationships=rels)

        joined = problem.cabin_camper_prefs.reset_index()
        validate_relationships(rels, joined)  # pairwise-valid → does not raise

        solution = run(problem, OptimizationConfig())

        assert solution.status.state is SolverState.INFEASIBLE
        assert any(all(name in f.cause for name in ("Ash", "Bo", "Cy")) for f in solution.findings)

    @pytest.mark.slow
    def test_real_solver_confirms_besties_too_big_for_seatrade(self):
        """B3: a same-cabin besties trio whose only two shared seatrades seat two."""
        rows = [
            {"cabin": "Otter", "camper": "Ash", "prefs": ["Sailing", "Kayaking", "Rowing", "Canoeing"]},
            {"cabin": "Otter", "camper": "Bo", "prefs": ["Sailing", "Kayaking", "Archery", "Crafts"]},
            {"cabin": "Otter", "camper": "Cy", "prefs": ["Sailing", "Kayaking", "Climbing", "Dance"]},
        ]
        setup = pd.DataFrame(
            {
                "seatrade": ["Sailing", "Kayaking", "Rowing", "Canoeing", "Archery", "Crafts", "Climbing", "Dance"],
                "campers_min": 0,
                "campers_max": [2, 2, 10, 10, 10, 10, 10, 10],
            }
        )
        rels = _besties_rel([("Otter", "Ash", "Otter", "Bo"), ("Otter", "Bo", "Otter", "Cy")])

        solution = run(_roster_problem(rows, setup, relationships=rels), OptimizationConfig())

        assert solution.status.state is SolverState.INFEASIBLE
        assert any("Ash" in f.cause and "seat fewer than" in f.cause for f in solution.findings)

    @pytest.mark.slow
    def test_real_solver_confirms_besties_too_big_for_cabin(self):
        """B2: a same-cabin besties trio under a 25% cabin-share cap (per-cabin seats 2 < 3)."""
        rows = [
            {"cabin": "Otter", "camper": "Ash", "prefs": ["Sailing", "Kayaking", "Rowing", "Canoeing"]},
            {"cabin": "Otter", "camper": "Bo", "prefs": ["Sailing", "Kayaking", "Archery", "Crafts"]},
            {"cabin": "Otter", "camper": "Cy", "prefs": ["Sailing", "Kayaking", "Climbing", "Dance"]},
        ]
        all_seatrades = sorted({s for row in rows for s in row["prefs"]})
        setup = pd.DataFrame({"seatrade": all_seatrades, "campers_min": 0, "campers_max": 10})
        rels = _besties_rel([("Otter", "Ash", "Otter", "Bo"), ("Otter", "Bo", "Otter", "Cy")])
        config = OptimizationConfig(max_cabin_share_per_seatrade=0.25)

        solution = run(_roster_problem(rows, setup, relationships=rels), config)

        assert solution.status.state is SolverState.INFEASIBLE
        assert any("cabin" in f.cause.lower() and "Ash" in f.cause for f in solution.findings)


def _rel(rows: list[tuple[str, str, str, str, str]]) -> pd.DataFrame:
    """A relationships frame from (cabin_1, camper_1, cabin_2, camper_2, type) tuples."""
    return pd.DataFrame(rows, columns=["cabin_1", "camper_1", "cabin_2", "camper_2", "relationship"])


class TestRelationshipCauseReality:
    """Slow reality fixtures: the real solver confirms R1/FH/FC are genuine infeasibility."""

    @pytest.mark.slow
    def test_real_solver_confirms_besties_frenemies_contradiction(self):
        """R1: a besties chain with a frenemies pair inside it can't be satisfied."""
        rows = [
            {"cabin": "Otter", "camper": "Ash", "prefs": ["Sailing", "Kayaking", "Rowing", "Canoeing"]},
            {"cabin": "Otter", "camper": "Bo", "prefs": ["Sailing", "Kayaking", "Archery", "Crafts"]},
            {"cabin": "Otter", "camper": "Cy", "prefs": ["Sailing", "Kayaking", "Climbing", "Dance"]},
        ]
        all_seatrades = sorted({s for row in rows for s in row["prefs"]})
        setup = pd.DataFrame({"seatrade": all_seatrades, "campers_min": 0, "campers_max": 10})
        rels = _rel(
            [
                ("Otter", "Ash", "Otter", "Bo", "besties"),
                ("Otter", "Bo", "Otter", "Cy", "besties"),
                ("Otter", "Ash", "Otter", "Cy", "frenemies"),
            ]
        )

        solution = run(_roster_problem(rows, setup, relationships=rels), OptimizationConfig())

        assert solution.status.state is SolverState.INFEASIBLE
        assert any("Ash" in f.cause and "Cy" in f.cause and "besties group" in f.cause for f in solution.findings)

    @pytest.mark.slow
    def test_real_solver_confirms_friends_hub(self):
        """FH: a hub whose four friends each want a different one of its seatrades."""
        rows = [
            {"cabin": "Otter", "camper": "Hub", "prefs": ["Sailing", "Kayaking", "Rowing", "Canoeing"]},
            {"cabin": "Otter", "camper": "F1", "prefs": ["Sailing", "Archery", "Crafts", "Dance"]},
            {"cabin": "Otter", "camper": "F2", "prefs": ["Kayaking", "Archery", "Crafts", "Dance"]},
            {"cabin": "Otter", "camper": "F3", "prefs": ["Rowing", "Archery", "Crafts", "Dance"]},
            {"cabin": "Otter", "camper": "F4", "prefs": ["Canoeing", "Archery", "Crafts", "Dance"]},
        ]
        all_seatrades = sorted({s for row in rows for s in row["prefs"]})
        setup = pd.DataFrame({"seatrade": all_seatrades, "campers_min": 0, "campers_max": 10})
        rels = _rel([("Otter", "Hub", "Otter", f"F{i}", "friends") for i in range(1, 5)])

        solution = run(_roster_problem(rows, setup, relationships=rels), OptimizationConfig())

        assert solution.status.state is SolverState.INFEASIBLE
        assert any("Hub" in f.cause and "friends" in f.cause for f in solution.findings)

    @pytest.mark.slow
    def test_real_solver_confirms_frenemies_clash(self):
        """FC: five same-cabin mutual frenemies sharing only four seatrades (pigeonhole)."""
        shared = ["Sailing", "Kayaking", "Rowing", "Canoeing"]
        names = [f"Fr{i}" for i in range(5)]
        rows = [{"cabin": "Otter", "camper": n, "prefs": shared} for n in names]
        setup = pd.DataFrame({"seatrade": shared, "campers_min": 0, "campers_max": 10})
        rels = _rel([("Otter", a, "Otter", b, "frenemies") for a, b in itertools.combinations(names, 2)])

        solution = run(_roster_problem(rows, setup, relationships=rels), OptimizationConfig())

        assert solution.status.state is SolverState.INFEASIBLE
        assert any("refuse to share" in f.cause for f in solution.findings)


class TestSolverRun:
    """solver.run(problem, config) -> AssignmentSolution."""

    def test_run_returns_assignment_solution(self, scheduling_problem, default_config):
        solution = run(scheduling_problem, default_config)
        assert isinstance(solution, AssignmentSolution)
        assert solution.status.state == SolverState.OPTIMAL

    def test_assignments_has_campers_as_index(self, scheduling_problem, default_config):
        solution = run(scheduling_problem, default_config)
        assert set(solution.assignments.index) == set(scheduling_problem.campers)

    def test_assignments_columns_match_seatrades_full(self, scheduling_problem, default_config):
        solution = run(scheduling_problem, default_config)
        assert list(solution.assignments.columns) == scheduling_problem.seatrades_full

    def test_domain_data_comes_from_problem(self, scheduling_problem, default_config):
        solution = run(scheduling_problem, default_config)
        assert solution.cabins == scheduling_problem.cabins
        # solution exposes camper NAMES; the problem's campers are internal integer IDs.
        assert solution.campers == scheduling_problem.camper_names
        assert solution.seatrades_full == scheduling_problem.seatrades_full
        assert solution.cabin_camper_prefs.equals(scheduling_problem.cabin_camper_prefs)
        assert solution.camper_prefs.equals(scheduling_problem.camper_prefs)

    def test_each_camper_assigned_one_seatrade_per_block(self, scheduling_problem, default_config):
        solution = run(scheduling_problem, default_config)
        for camper in solution.assignments.index:
            for block_pair in [("1a", "1b"), ("2a", "2b")]:
                cols = [
                    c
                    for c in solution.assignments.columns
                    if c.startswith(f"{block_pair[0]}_") or c.startswith(f"{block_pair[1]}_")
                ]
                total = solution.assignments.loc[camper, cols].sum()
                assert total == 1.0, f"Camper {camper} has sum {total} in block {block_pair}"

    def test_seatrade_names_with_spaces(self):
        """Seatrade names containing spaces must round-trip through PuLP without breakage."""
        joined = pd.DataFrame(
            {
                "cabin": ["Cabin1", "Cabin1", "Cabin2", "Cabin2"],
                "camper": ["Alice", "Bob", "Carol", "Dave"],
                "gender": ["F", "M", "F", "M"],
                "age": [13, 14, 15, 16],
                "seatrade_1": ["Canoeing and Kayaking", "High Ropes", "Laser Tag", "Giant Swing"],
                "seatrade_2": ["High Ropes", "Canoeing and Kayaking", "Giant Swing", "Laser Tag"],
                "seatrade_3": ["Laser Tag", "Giant Swing", "Canoeing and Kayaking", "High Ropes"],
                "seatrade_4": ["Giant Swing", "Laser Tag", "High Ropes", "Canoeing and Kayaking"],
            }
        )
        setup = pd.DataFrame(
            {
                "seatrade": ["Canoeing and Kayaking", "High Ropes", "Laser Tag", "Giant Swing"],
                "campers_min": [0, 0, 0, 0],
                "campers_max": [10, 10, 10, 10],
            }
        )
        problem = SchedulingProblem(joined, setup)
        config = OptimizationConfig(solver=__import__("pulp").apis.PULP_CBC_CMD(msg=0))
        solution = run(problem, config)

        assert solution.status.state == SolverState.OPTIMAL
        assert list(solution.assignments.columns) == problem.seatrades_full
        # Verify column names contain spaces (not mangled to underscores)
        assert "1a_Canoeing and Kayaking" in solution.assignments.columns

    def test_resolve_produces_clean_names_no_suffix(self):
        """Re-solving the same data yields clean camper names — no .N index suffix leaks."""
        joined = pd.DataFrame(
            {
                "cabin": ["Cabin1", "Cabin1", "Cabin2", "Cabin2"],
                "camper": ["Alice", "Bob", "Carol", "Dave"],
                "gender": ["F", "M", "F", "M"],
                "age": [13, 14, 15, 16],
                "seatrade_1": ["Archery", "Climbing", "Sailing", "Archery"],
                "seatrade_2": ["Sailing", "Archery", "Archery", "Climbing"],
                "seatrade_3": ["Climbing", "Sailing", "Climbing", "Sailing"],
                "seatrade_4": ["Kayaking", "Kayaking", "Kayaking", "Kayaking"],
            }
        )
        setup = pd.DataFrame(
            {
                "seatrade": ["Archery", "Sailing", "Climbing", "Kayaking"],
                "campers_min": [0, 0, 0, 0],
                "campers_max": [10, 10, 10, 10],
            }
        )
        config = OptimizationConfig(solver=pulp.apis.PULP_CBC_CMD(msg=0))

        # Build and solve twice from the same source data — the old suffix hack
        # mutated names and leaked compounding suffixes on repeated construction.
        run(SchedulingProblem(joined, setup), config)
        solution = run(SchedulingProblem(joined, setup), config)

        names = wrangle_assignments_to_longform(solution)["camper"].unique().tolist()
        assert set(names) == {"Alice", "Bob", "Carol", "Dave"}
        assert all("." not in name for name in names)
        assert solution.campers == ["Alice", "Bob", "Carol", "Dave"]

    def test_same_name_different_cabin(self):
        """Two campers sharing a name stay distinct: internally by camper_id, in output by the (cabin, camper) key."""
        joined = pd.DataFrame(
            {
                "cabin": ["Cabin1", "Cabin1", "Cabin2", "Cabin2"],
                "camper": ["Alex", "Bob", "Alex", "Dave"],
                "gender": ["F", "M", "F", "M"],
                "age": [13, 14, 15, 16],
                "seatrade_1": ["Archery", "Climbing", "Sailing", "Archery"],
                "seatrade_2": ["Sailing", "Archery", "Archery", "Climbing"],
                "seatrade_3": ["Climbing", "Sailing", "Climbing", "Sailing"],
                "seatrade_4": ["Kayaking", "Kayaking", "Kayaking", "Kayaking"],
            }
        )
        setup = pd.DataFrame(
            {
                "seatrade": ["Archery", "Sailing", "Climbing", "Kayaking"],
                "campers_min": [0, 0, 0, 0],
                "campers_max": [10, 10, 10, 10],
            }
        )
        config = OptimizationConfig(solver=pulp.apis.PULP_CBC_CMD(msg=0))

        solution = run(SchedulingProblem(joined, setup), config)
        longform = wrangle_assignments_to_longform(solution)

        alex_rows = longform[longform["camper"] == "Alex"]
        assert set(alex_rows["cabin"].unique()) == {"Cabin1", "Cabin2"}

        wideform = wrangle_assignments_to_wideform(longform)
        alex_wide = wideform[wideform["camper"] == "Alex"]
        assert len(alex_wide) == 2
        assert set(alex_wide["cabin"]) == {"Cabin1", "Cabin2"}


class TestBestiesConstraint:
    """A besties pair must receive an identical schedule end-to-end."""

    _joined = pd.DataFrame(
        {
            "cabin": ["Cabin1", "Cabin1", "Cabin2", "Cabin2"],
            "camper": ["Alice", "Bob", "Carol", "Dave"],
            "gender": ["F", "M", "F", "M"],
            "age": [13, 14, 15, 16],
            "seatrade_1": ["Archery", "Climbing", "Sailing", "Archery"],
            "seatrade_2": ["Sailing", "Archery", "Archery", "Climbing"],
            "seatrade_3": ["Climbing", "Sailing", "Climbing", "Sailing"],
            "seatrade_4": ["Kayaking", "Kayaking", "Kayaking", "Kayaking"],
        }
    )
    _setup = pd.DataFrame(
        {
            "seatrade": ["Archery", "Sailing", "Climbing", "Kayaking"],
            "campers_min": [0, 0, 0, 0],
            "campers_max": [10, 10, 10, 10],
        }
    )

    def test_besties_pair_gets_identical_schedule(self):
        # Alice and Bob are both in Cabin1 and share Archery/Sailing/Climbing/Kayaking.
        # A same-cabin pair stays feasible under fleet-balance regardless of cabin count.
        relationships = pd.DataFrame(
            {
                "cabin_1": ["Cabin1"],
                "camper_1": ["Alice"],
                "cabin_2": ["Cabin1"],
                "camper_2": ["Bob"],
                "relationship": ["besties"],
            }
        )
        problem = SchedulingProblem(self._joined, self._setup, relationships=relationships)
        config = OptimizationConfig(solver=pulp.apis.PULP_CBC_CMD(msg=0))

        solution = run(problem, config)

        assert solution.status.state == SolverState.OPTIMAL
        # camper_ids: Alice=0, Bob=1. Identical assignment row across all seatrades.
        alice = solution.assignments.loc[0]
        bob = solution.assignments.loc[1]
        assert (alice == bob).all(), f"besties schedules differ:\n{alice}\n{bob}"

    def test_without_relationships_pair_need_not_match(self):
        """Sanity: the identical-schedule outcome comes from the constraint, not the data."""
        problem = SchedulingProblem(self._joined, self._setup)
        config = OptimizationConfig(solver=pulp.apis.PULP_CBC_CMD(msg=0))

        solution = run(problem, config)

        assert solution.status.state == SolverState.OPTIMAL
        besties_names = [name for name in problem.build(config).constraints if name.startswith("besties_")]
        assert besties_names == []


class TestFriendsFrenemiesConstraints:
    """Friends pairs share a session end-to-end; frenemies pairs share none."""

    _joined = pd.DataFrame(
        {
            "cabin": ["Cabin1", "Cabin1", "Cabin2", "Cabin2"],
            "camper": ["Alice", "Bob", "Carol", "Dave"],
            "gender": ["F", "M", "F", "M"],
            "age": [13, 14, 15, 16],
            "seatrade_1": ["Archery", "Archery", "Sailing", "Archery"],
            "seatrade_2": ["Sailing", "Sailing", "Archery", "Climbing"],
            "seatrade_3": ["Climbing", "Climbing", "Climbing", "Sailing"],
            "seatrade_4": ["Kayaking", "Kayaking", "Kayaking", "Kayaking"],
        }
    )
    _setup = pd.DataFrame(
        {
            "seatrade": ["Archery", "Sailing", "Climbing", "Kayaking"],
            "campers_min": [0, 0, 0, 0],
            "campers_max": [10, 10, 10, 10],
        }
    )
    _config = OptimizationConfig(solver=pulp.apis.PULP_CBC_CMD(msg=0))

    def _shared_sessions(self, solution, c1, c2):
        """Columns where both campers are assigned (both == 1)."""
        both = (solution.assignments.loc[c1] == 1) & (solution.assignments.loc[c2] == 1)
        return [s for s in solution.assignments.columns if both[s]]

    def test_friends_pair_shares_a_session(self):
        relationships = pd.DataFrame(
            {
                "cabin_1": ["Cabin1"],
                "camper_1": ["Alice"],
                "cabin_2": ["Cabin1"],
                "camper_2": ["Bob"],
                "relationship": ["friends"],
            }
        )
        problem = SchedulingProblem(self._joined, self._setup, relationships=relationships)

        solution = run(problem, self._config)

        assert solution.status.state == SolverState.OPTIMAL
        # Alice=0, Bob=1 must overlap in at least one session.
        assert len(self._shared_sessions(solution, 0, 1)) >= 1

    def test_frenemies_pair_shares_no_session(self):
        relationships = pd.DataFrame(
            {
                "cabin_1": ["Cabin1"],
                "camper_1": ["Alice"],
                "cabin_2": ["Cabin2"],
                "camper_2": ["Carol"],
                "relationship": ["frenemies"],
            }
        )
        problem = SchedulingProblem(self._joined, self._setup, relationships=relationships)

        solution = run(problem, self._config)

        assert solution.status.state == SolverState.OPTIMAL
        # Alice=0, Carol=2 must not overlap in any session.
        assert self._shared_sessions(solution, 0, 2) == []

    def test_contradictory_chain_is_infeasible(self):
        # besties(Alice,Bob) → identical schedules; friends(Bob,Carol) → Carol shares
        # a session with Bob; frenemies(Alice,Carol) → Carol shares none with Alice.
        # Alice≡Bob, so Carol must both share and not share that schedule — infeasible.
        relationships = pd.DataFrame(
            {
                "cabin_1": ["Cabin1", "Cabin1", "Cabin1"],
                "camper_1": ["Alice", "Bob", "Alice"],
                "cabin_2": ["Cabin1", "Cabin2", "Cabin2"],
                "camper_2": ["Bob", "Carol", "Carol"],
                "relationship": ["besties", "friends", "frenemies"],
            }
        )
        # The set passes validation — the conflict only surfaces at solve time.
        validate_relationships(relationships, self._joined)

        problem = SchedulingProblem(self._joined, self._setup, relationships=relationships)
        solution = run(problem, self._config)

        assert solution.status.state == SolverState.INFEASIBLE


def _cabin_fleet_per_half(solution, problem):
    """Map each cabin to (first_half_fleet, second_half_fleet) read from assignments.

    A camper's assigned column ``{block}_{seatrade}`` encodes the block; the block's
    letter is the fleet ('a' = Morning/AM, 'b' = Afternoon/PM). All campers in a cabin
    share a fleet per half, so reading any one camper is enough.
    """
    fleets = {}
    for cabin, camper_ids in problem.campers_by_cabin.items():
        row = solution.assignments.loc[camper_ids[0]]
        assigned = [col for col in row.index if row[col] == 1]
        first = next(col for col in assigned if col.startswith(("1a_", "1b_")))
        second = next(col for col in assigned if col.startswith(("2a_", "2b_")))
        fleets[cabin] = (first[1], second[1])
    return fleets


class TestSameFleetAllWeek:
    """force_same_fleet_all_week ties each cabin's AM/PM choice across both halves.

    The roster below is tuned (with sparsity_weight high) so the *unconstrained* optimum
    rotates some cabins between AM and PM across the two halves — making the toggle bind.
    """

    # 4 cabins, 2 campers each. With the flag off, the sparsity-minimal schedule moves at
    # least one cabin between fleets across the halves (verified empirically).
    _joined = pd.DataFrame(
        {
            "cabin": ["C0", "C0", "C1", "C1", "C2", "C2", "C3", "C3"],
            "camper": ["C0_0", "C0_1", "C1_0", "C1_1", "C2_0", "C2_1", "C3_0", "C3_1"],
            "gender": ["M", "M", "F", "F", "M", "M", "F", "F"],
            "age": [13, 14, 13, 14, 15, 16, 15, 16],
            "seatrade_1": ["P", "P", "Q", "Q", "U", "U", "T", "T"],
            "seatrade_2": ["U", "U", "R", "R", "P", "P", "U", "U"],
            "seatrade_3": ["T", "T", "U", "U", "R", "R", "R", "R"],
            "seatrade_4": ["Q", "Q", "P", "P", "T", "T", "Q", "Q"],
        }
    )
    _setup = pd.DataFrame(
        {
            "seatrade": ["P", "Q", "R", "T", "U"],
            "campers_min": [0] * 5,
            "campers_max": [50] * 5,
        }
    )

    def _config(self, force):
        return OptimizationConfig(
            solver=pulp.apis.PULP_CBC_CMD(msg=0),
            sparsity_weight=5,
            cabins_weight=0,
            preference_weight=1,
            force_same_fleet_all_week=force,
        )

    def test_flag_off_lets_a_cabin_switch_fleets(self):
        """Baseline: without the toggle, the optimum rotates at least one cabin's fleet."""
        problem = SchedulingProblem(self._joined, self._setup)

        solution = run(problem, self._config(force=False))

        assert solution.status.state == SolverState.OPTIMAL
        fleets = _cabin_fleet_per_half(solution, problem)
        assert any(first != second for first, second in fleets.values()), fleets

    def test_flag_off_adds_no_same_fleet_constraints(self):
        """Off-path is the current model: no same-fleet constraints are built."""
        problem = SchedulingProblem(self._joined, self._setup)

        constraints = problem.build(self._config(force=False)).constraints
        assert [name for name in constraints if name.startswith("same_fleet_")] == []

    def test_flag_on_holds_every_cabin_in_one_fleet(self):
        problem = SchedulingProblem(self._joined, self._setup)

        solution = run(problem, self._config(force=True))

        assert solution.status.state == SolverState.OPTIMAL
        fleets = _cabin_fleet_per_half(solution, problem)
        for cabin, (first, second) in fleets.items():
            assert first == second, f"{cabin} switches fleet: 1st={first} 2nd={second}"

    def test_flag_on_costs_optimality(self):
        """The toggle is a real hard constraint: holding fleet fixed costs a worse optimum."""
        problem = SchedulingProblem(self._joined, self._setup)

        off_obj = self._solved_objective(problem, force=False)
        on_obj = self._solved_objective(problem, force=True)

        # Objective is minimized, so a larger value is a worse (more-constrained) schedule.
        assert on_obj > off_obj, f"toggle did not bind: off={off_obj} on={on_obj}"

    @staticmethod
    def _solved_objective(problem, force):
        config = OptimizationConfig(
            solver=pulp.apis.PULP_CBC_CMD(msg=0),
            sparsity_weight=5,
            cabins_weight=0,
            preference_weight=1,
            force_same_fleet_all_week=force,
        )
        lp = problem.build(config)
        config.solver.solve(lp)
        return pulp.value(lp.objective)


class TestSeededRosterSolves:
    """The mock generator's seeded relationships must solve end-to-end (CONTEXT.md:86)."""

    _identity = pd.DataFrame(
        {
            "cabin": ["Puffin", "Puffin", "Tillikum", "Tillikum", "Orca", "Narwhal"],
            "camper": ["Alice", "Bob", "Carlos", "Dana", "Eve", "Frank"],
            "gender": ["female", "female", "male", "male", "female", "male"],
            "age": [13, 14, 13, 14, 15, 16],
        }
    )
    # Alice&Bob (same cabin) share ≥2 → besties; Carlos&Dana (same cabin) share ≥1 →
    # friends; the remaining cross-cabin pair → frenemies.
    _preferences = pd.DataFrame(
        {
            "camper": ["Alice", "Bob", "Carlos", "Dana", "Eve", "Frank"],
            "seatrade_1": ["Sailing", "Climbing", "Archery", "Sailing", "Climbing", "Kayaking"],
            "seatrade_2": ["Climbing", "Sailing", "Sailing", "Archery", "Kayaking", "Tubing"],
            "seatrade_3": ["Archery", "Archery", "Kayaking", "Crafts", "Tubing", "Wibit"],
            "seatrade_4": ["Crafts", "Swimming", "Tubing", "Wibit", "Wibit", "Swimming"],
        }
    )
    _setup = pd.DataFrame(
        {
            "seatrade": ["Sailing", "Climbing", "Archery", "Crafts", "Kayaking", "Tubing", "Wibit", "Swimming"],
            "campers_min": [0] * 8,
            "campers_max": [10] * 8,
        }
    )
    _config = OptimizationConfig(solver=pulp.apis.PULP_CBC_CMD(msg=0))

    def test_all_three_seeded_relationships_solve(self):
        relationships = simulate_camper_relationships(self._identity, self._preferences)
        # Guard the premise: the generator must actually seed all three types.
        assert set(relationships["relationship"]) == {"besties", "friends", "frenemies"}

        joined = self._identity.merge(self._preferences, on="camper")
        problem = SchedulingProblem(joined, self._setup, relationships=relationships)

        solution = run(problem, self._config)

        assert solution.status.state == SolverState.OPTIMAL


class TestMangle:
    """Name mangling must match PuLP's internal variable naming."""

    def test_spaces_replaced_with_underscores(self):
        from seatrades.solver import _mangle

        assert _mangle("Canoeing and Kayaking") == "Canoeing_and_Kayaking"

    def test_hyphens_replaced_with_underscores(self):
        from seatrades.solver import _mangle

        assert _mangle("Jean-Luc") == "Jean_Luc"

    def test_dots_preserved(self):
        from seatrades.solver import _mangle

        assert _mangle("J.R.") == "J.R."

    def test_plus_sign_replaced(self):
        from seatrades.solver import _mangle

        assert _mangle("C++") == "C__"

    def test_unicode_letters_preserved(self):
        from seatrades.solver import _mangle

        assert _mangle("Bárbara") == "Bárbara"
        assert _mangle("José") == "José"
        assert _mangle("François") == "François"

    def test_no_special_chars(self):
        from seatrades.solver import _mangle

        assert _mangle("Alice") == "Alice"


class TestExtractCamperAssignments:
    """_extract_camper_assignments must find all expected variables."""

    def test_raises_when_variable_name_missing(self):
        """If _mangle produces a name that doesn't match, extraction must raise, not silently default to 0."""
        import pulp

        from seatrades.solver import _extract_camper_assignments

        # Create a minimal solved problem with known variables
        prob = pulp.LpProblem("test", pulp.LpMinimize)
        x = pulp.LpVariable("x", lowBound=0)
        prob += x
        prob.solve(pulp.PULP_CBC_CMD(msg=0))

        # Request a camper id whose variables don't exist in the problem
        with pytest.raises(ValueError, match="Expected.*variables.*found"):
            _extract_camper_assignments(prob.variables(), [0], ["1a_Archery"])


class TestStatusCodeMapping:
    """Solver status code must map PuLP codes correctly."""

    def test_optimal_status_passes_through(self, scheduling_problem, default_config):
        solution = run(scheduling_problem, default_config)
        assert solution.status.state == SolverState.OPTIMAL

    def test_optimal_solution_has_gap(self, scheduling_problem, default_config):
        solution = run(scheduling_problem, default_config)
        # Gap may be None if CBC doesn't write a gap line (small problems solve instantly)
        # but the field should be populated when available
        assert solution.status.gap is None or isinstance(solution.status.gap, float)

    def test_optimal_solution_that_finished_is_not_flagged_timed_out(self, scheduling_problem, default_config):
        # A small problem solves to optimality well inside the time limit, so its CBC log
        # carries no "Stopped on time limit" line — the final status must read proven, not
        # stopped-on-time. (The True branch is covered by detect_timeout's own unit tests.)
        solution = run(scheduling_problem, default_config)
        assert solution.status.state == SolverState.OPTIMAL
        assert solution.status.timed_out is False

    def test_infeasible_solution_has_no_gap(self):
        joined = pd.DataFrame(
            {
                "cabin": ["Cabin1", "Cabin1"],
                "camper": ["Alice", "Bob"],
                "gender": ["F", "M"],
                "age": [13, 14],
                "seatrade_1": ["Archery", "Archery"],
                "seatrade_2": ["Archery", "Archery"],
                "seatrade_3": ["Archery", "Archery"],
                "seatrade_4": ["Archery", "Archery"],
            }
        )
        setup = pd.DataFrame(
            {
                "seatrade": ["Archery"],
                "campers_min": [2],
                "campers_max": [2],
            }
        )
        problem = SchedulingProblem(joined, setup)
        config = OptimizationConfig(solver=__import__("pulp").apis.PULP_CBC_CMD(msg=0))
        solution = run(problem, config)
        assert solution.status.state == SolverState.INFEASIBLE
        assert solution.status.gap is None

    def test_infeasible_problem_returns_infeasible(self):
        """An infeasible problem should return SolverState.INFEASIBLE, not ERROR."""

        # 2 campers, 1 seatrade with max 1 — can't assign both
        joined = pd.DataFrame(
            {
                "cabin": ["Cabin1", "Cabin1"],
                "camper": ["Alice", "Bob"],
                "gender": ["F", "M"],
                "age": [13, 14],
                "seatrade_1": ["Archery", "Archery"],
                "seatrade_2": ["Archery", "Archery"],
                "seatrade_3": ["Archery", "Archery"],
                "seatrade_4": ["Archery", "Archery"],
            }
        )
        setup = pd.DataFrame(
            {
                "seatrade": ["Archery"],
                "campers_min": [2],
                "campers_max": [2],
            }
        )
        problem = SchedulingProblem(joined, setup)
        config = OptimizationConfig(solver=__import__("pulp").apis.PULP_CBC_CMD(msg=0))
        solution = run(problem, config)
        # Infeasible should map to INFEASIBLE, not be swallowed as ERROR
        assert solution.status.state == SolverState.INFEASIBLE


class TestConditionalMinCapacity:
    """`campers_min` is a viability threshold, not a forced quota (issue #48).

    A session may have either 0 campers (it doesn't run) or a count within
    [campers_min, campers_max] (it runs). A seatrade nobody ranked simply drops.
    """

    # Four campers rank only pick1-pick4 (enough to fill both block pairs for
    # everyone). notpicked1 has campers_min > 0 but nobody ranks it.
    _joined = pd.DataFrame(
        {
            "cabin": ["Cabin1", "Cabin1", "Cabin2", "Cabin2"],
            "camper": ["Alice", "Bob", "Carol", "Dave"],
            "gender": ["F", "F", "M", "M"],
            "age": [13, 14, 15, 16],
            "seatrade_1": ["pick1", "pick2", "pick3", "pick4"],
            "seatrade_2": ["pick2", "pick3", "pick4", "pick1"],
            "seatrade_3": ["pick3", "pick4", "pick1", "pick2"],
            "seatrade_4": ["pick4", "pick1", "pick2", "pick3"],
        }
    )
    _setup = pd.DataFrame(
        {
            "seatrade": ["pick1", "pick2", "pick3", "pick4", "notpicked1"],
            "campers_min": [0, 0, 0, 0, 2],
            "campers_max": [10, 10, 10, 10, 10],
        }
    )

    def test_unranked_session_drops_instead_of_infeasible(self):
        """Default (conditional min): notpicked1's sessions drop to 0; solve is OPTIMAL."""
        problem = SchedulingProblem(self._joined, self._setup)
        config = OptimizationConfig(solver=pulp.apis.PULP_CBC_CMD(msg=0))
        solution = run(problem, config)

        assert solution.status.state == SolverState.OPTIMAL
        notpicked_cols = [c for c in solution.assignments.columns if c.endswith("_notpicked1")]
        assert notpicked_cols  # the columns exist...
        assert solution.assignments[notpicked_cols].to_numpy().sum() == 0  # ...but hold no campers

    def test_dropped_session_absent_from_exports(self):
        """A non-running session yields no assigned rows, so it never reaches the
        wrangled exports/charts (user story 5)."""
        problem = SchedulingProblem(self._joined, self._setup)
        config = OptimizationConfig(solver=pulp.apis.PULP_CBC_CMD(msg=0))
        solution = run(problem, config)

        longform = wrangle_assignments_to_longform(solution)
        assigned = longform[longform["assignment"] == 1.0]
        assert "notpicked1" not in assigned["seatrade"].to_numpy()

        wideform = wrangle_assignments_to_wideform(longform)
        assert "notpicked1" not in wideform.to_numpy()

    def test_legacy_force_fill_is_infeasible(self):
        """allow_empty_sessions=False restores the hard floor: notpicked1 can't fill -> INFEASIBLE."""
        problem = SchedulingProblem(self._joined, self._setup)
        config = OptimizationConfig(allow_empty_sessions=False, solver=pulp.apis.PULP_CBC_CMD(msg=0))
        solution = run(problem, config)

        assert solution.status.state == SolverState.INFEASIBLE


class TestAgeGroupingPenalty:
    """The soft age penalty tightens age spread when weighted, never forces infeasibility.

    Both cabins are age-mixed (a 13 and a 16). At age_weight=0 the cabins_weight goal
    packs each cabin's pair into one shared session — a wide age range. A high age_weight
    with age_balance=1 pays a tiny preference/cohesion cost to split the odd-aged camper
    out, collapsing session ranges. This binds the constraint by making the tight schedule
    worse-but-valid, never by infeasibility.
    """

    _joined = pd.DataFrame(
        {
            "cabin": ["Cabin1", "Cabin1", "Cabin2", "Cabin2"],
            "camper": ["Alice", "Bob", "Carol", "Dave"],
            "gender": ["F", "F", "F", "F"],
            "age": [13, 16, 13, 16],
            "seatrade_1": ["Archery", "Archery", "Archery", "Archery"],
            "seatrade_2": ["Sailing", "Sailing", "Sailing", "Sailing"],
            "seatrade_3": ["Climbing", "Climbing", "Climbing", "Climbing"],
            "seatrade_4": ["Kayaking", "Kayaking", "Kayaking", "Kayaking"],
        }
    )
    _setup = pd.DataFrame(
        {
            "seatrade": ["Archery", "Sailing", "Climbing", "Kayaking"],
            "campers_min": [0, 0, 0, 0],
            "campers_max": [10, 10, 10, 10],
        }
    )

    def _config(self, age_weight, age_balance=0.5):
        return OptimizationConfig(
            age_weight=age_weight,
            age_balance=age_balance,
            solver=pulp.apis.PULP_CBC_CMD(msg=0),
        )

    def _max_session_age_range(self, solution):
        ages = solution.cabin_camper_prefs["age"]
        spreads = [
            int(ages.loc[solution.assignments.index[solution.assignments[s] == 1]].agg(lambda a: a.max() - a.min()))
            for s in solution.assignments.columns
            if solution.assignments[s].sum() >= 1
        ]
        return max(spreads)

    def test_high_age_weight_tightens_session_spread(self):
        problem = SchedulingProblem(self._joined, self._setup)

        loose = run(problem, self._config(age_weight=0))
        tight = run(problem, self._config(age_weight=100, age_balance=1.0))

        assert loose.status.state == SolverState.OPTIMAL
        assert tight.status.state == SolverState.OPTIMAL
        # Baseline packs the mixed-age cabin together (range spans the 13–16 gap)...
        assert self._max_session_age_range(loose) >= 3
        # ...and the weighted solve splits it, collapsing the widest session range.
        assert self._max_session_age_range(tight) < self._max_session_age_range(loose)

    def test_soft_penalty_never_infeasible(self):
        """Even an overwhelming age_weight only nudges the objective — it stays solvable."""
        problem = SchedulingProblem(self._joined, self._setup)

        solution = run(problem, self._config(age_weight=1000, age_balance=0.5))

        assert solution.status.state == SolverState.OPTIMAL


class TestAgeGroupingBalanceSelectsLevel:
    """age_balance routes the penalty: 0 tightens blocks, 1 tightens sessions.

    A young and an old cabin *share* each preference group, so the sparsity goal packs
    them into the same block — mixing ages block-wide (range 3) at baseline. Separating
    them into age-pure blocks costs sparsity (the shared seatrades then run in two blocks),
    a worse-but-valid schedule the block-level penalty is willing to buy. The session-level
    penalty is indifferent to blocks, so it leaves the block spread loose.
    """

    _pref_p = ["Archery", "Sailing", "Diving", "Rowing"]
    _pref_q = ["Climbing", "Kayaking", "Surfing", "Fishing"]

    @classmethod
    def _roster(cls):
        rows = []
        for cabin, age, prefs in [
            ("Y1", 13, cls._pref_p),
            ("O1", 16, cls._pref_p),
            ("Y2", 13, cls._pref_q),
            ("O2", 16, cls._pref_q),
        ]:
            for i in range(2):
                rows.append(
                    {
                        "cabin": cabin,
                        "camper": f"{cabin}{i}",
                        "gender": "F",
                        "age": age,
                        "seatrade_1": prefs[0],
                        "seatrade_2": prefs[1],
                        "seatrade_3": prefs[2],
                        "seatrade_4": prefs[3],
                    }
                )
        joined = pd.DataFrame(rows)
        setup = pd.DataFrame({"seatrade": cls._pref_p + cls._pref_q, "campers_min": [0] * 8, "campers_max": [20] * 8})
        return SchedulingProblem(joined, setup)

    def _config(self, age_weight, age_balance):
        return OptimizationConfig(age_weight=age_weight, age_balance=age_balance, solver=pulp.apis.PULP_CBC_CMD(msg=0))

    def _max_block_age_range(self, solution, problem):
        ages = solution.cabin_camper_prefs["age"]
        spreads = []
        for block in problem.blocks:
            cols = [f"{block}_{s}" for s in problem.seatrades]
            members = solution.assignments.index[solution.assignments[cols].sum(axis=1) >= 1]
            if len(members):
                block_ages = ages.loc[members]
                spreads.append(int(block_ages.max() - block_ages.min()))
        return max(spreads)

    def test_block_focus_tightens_block_spread(self):
        problem = self._roster()

        loose = run(problem, self._config(age_weight=0, age_balance=0.0))
        tight = run(problem, self._config(age_weight=200, age_balance=0.0))

        assert loose.status.state == SolverState.OPTIMAL
        assert tight.status.state == SolverState.OPTIMAL
        # Baseline packs a young + old cabin into each block (spans the 13–16 gap)...
        assert self._max_block_age_range(loose, problem) >= 3
        # ...and block-weighted grouping separates them into age-pure blocks.
        assert self._max_block_age_range(tight, problem) < self._max_block_age_range(loose, problem)

    def test_session_focus_leaves_block_spread_loose(self):
        """age_balance=1 optimizes sessions only — it does not tighten block spread."""
        problem = self._roster()

        session_focus = run(problem, self._config(age_weight=200, age_balance=1.0))

        assert session_focus.status.state == SolverState.OPTIMAL
        # Session-level tightening leaves at least one block age-mixed (blocks are not its concern).
        assert self._max_block_age_range(session_focus, problem) >= 3


def _max_cabin_concentration(solution, problem, cabin):
    """Largest number of ``cabin``'s campers sharing a single session."""
    counts: dict[str, int] = {}
    for cid in problem.campers_by_cabin[cabin]:
        row = solution.assignments.loc[cid]
        for col in row.index[row == 1]:
            counts[col] = counts.get(col, 0) + 1
    return max(counts.values())


def _preference_penalty(solution, problem):
    """Sum of assigned-seatrade preference ranks over all campers (lower = happier)."""
    total = 0
    for cid, prefs in problem.camper_prefs.items():
        row = solution.assignments.loc[cid]
        for col in row.index[row == 1]:
            total += prefs.index(seatrade_name(col))
    return total


class TestCabinVarietyPenalty:
    """cabin_variety_weight discourages one cabin from dominating a single seatrade.

    One 6-camper cabin (C0) all share the ranking [A, B, C, D]. With cabin togetherness
    pulling and variety off, the optimum packs all six into one session per half. Raising
    cabin_variety_weight spreads that cabin across seatrades — a worse-but-valid preference
    cost, never infeasible.
    """

    _joined = pd.DataFrame(
        {
            "cabin": ["C0"] * 6,
            "camper": [f"C0_{i}" for i in range(6)],
            "gender": ["M", "F", "M", "F", "M", "F"],
            "age": [13, 13, 14, 14, 15, 15],
            "seatrade_1": ["A"] * 6,
            "seatrade_2": ["B"] * 6,
            "seatrade_3": ["C"] * 6,
            "seatrade_4": ["D"] * 6,
        }
    )
    # campers_max=8 → free threshold round(0.25 * 8) = 2 campers per cabin per seatrade.
    _setup = pd.DataFrame(
        {
            "seatrade": ["A", "B", "C", "D"],
            "campers_min": [0] * 4,
            "campers_max": [8] * 4,
        }
    )

    def _config(self, cabin_variety_weight):
        return OptimizationConfig(
            solver=pulp.apis.PULP_CBC_CMD(msg=0),
            preference_weight=1,
            cabins_weight=5,
            sparsity_weight=0,
            age_weight=0,
            cabin_variety_weight=cabin_variety_weight,
        )

    def test_variety_off_packs_the_cabin_into_one_seatrade(self):
        """Baseline: with variety off, cohesion packs all six cabinmates into one session."""
        problem = SchedulingProblem(self._joined, self._setup)

        solution = run(problem, self._config(cabin_variety_weight=0))

        assert solution.status.state == SolverState.OPTIMAL
        assert _max_cabin_concentration(solution, problem, "C0") == 6

    def test_high_variety_spreads_the_cabin_at_a_worse_preference_cost(self):
        """Raising the weight spreads the cabin across seatrades — worse-but-valid, not infeasible."""
        problem = SchedulingProblem(self._joined, self._setup)

        off = run(problem, self._config(cabin_variety_weight=0))
        on = run(problem, self._config(cabin_variety_weight=50))

        assert on.status.state == SolverState.OPTIMAL
        assert _max_cabin_concentration(on, problem, "C0") < _max_cabin_concentration(off, problem, "C0")
        # The spread is not free: campers drop to lower-ranked seatrades.
        assert _preference_penalty(on, problem) > _preference_penalty(off, problem)


class TestMaxCabinSharePerSeatrade:
    """The optional hard cap forbids one cabin from over-filling a seatrade.

    A three-bestie chain in one cabin shares an identical schedule, so all three land in
    the same session. campers_max=8 → a 25% cap allows only round(0.25*8)=2 per cabin,
    which the trio must exceed.
    """

    _joined = pd.DataFrame(
        {
            "cabin": ["Cabin1"] * 3,
            "camper": ["Alice", "Bob", "Cara"],
            "gender": ["F", "M", "F"],
            "age": [13, 14, 15],
            "seatrade_1": ["A"] * 3,
            "seatrade_2": ["B"] * 3,
            "seatrade_3": ["C"] * 3,
            "seatrade_4": ["D"] * 3,
        }
    )
    _setup = pd.DataFrame(
        {
            "seatrade": ["A", "B", "C", "D"],
            "campers_min": [0] * 4,
            "campers_max": [8] * 4,
        }
    )
    _relationships = pd.DataFrame(
        {
            "cabin_1": ["Cabin1", "Cabin1"],
            "camper_1": ["Alice", "Bob"],
            "cabin_2": ["Cabin1", "Cabin1"],
            "camper_2": ["Bob", "Cara"],
            "relationship": ["besties", "besties"],
        }
    )

    def _config(self, share):
        return OptimizationConfig(
            solver=pulp.apis.PULP_CBC_CMD(msg=0),
            max_cabin_share_per_seatrade=share,
        )

    def test_default_share_is_a_no_op(self):
        """At the default 1.0 the cap is off — the over-filling trio still solves."""
        problem = SchedulingProblem(self._joined, self._setup, relationships=self._relationships)

        solution = run(problem, self._config(share=1.0))

        assert solution.status.state == SolverState.OPTIMAL

    def test_low_share_forbids_domination(self):
        """Sliding the cap to 25% caps a cabin at 2 per seatrade — the trio is infeasible."""
        problem = SchedulingProblem(self._joined, self._setup, relationships=self._relationships)

        solution = run(problem, self._config(share=0.25))

        assert solution.status.state == SolverState.INFEASIBLE


class TestBestiesChainOverFourSolves:
    """Regression: the old hardcoded max-4-per-cabin forced INFEASIBLE for a 5-bestie chain
    sharing a cabin (mode B2). With the cap gone by default, it now solves."""

    _joined = pd.DataFrame(
        {
            "cabin": ["Cabin1"] * 5,
            "camper": [f"C{i}" for i in range(5)],
            "gender": ["F", "M", "F", "M", "F"],
            "age": [13, 14, 15, 16, 13],
            "seatrade_1": ["A"] * 5,
            "seatrade_2": ["B"] * 5,
            "seatrade_3": ["C"] * 5,
            "seatrade_4": ["D"] * 5,
        }
    )
    _setup = pd.DataFrame(
        {
            "seatrade": ["A", "B", "C", "D"],
            "campers_min": [0] * 4,
            "campers_max": [10] * 4,
        }
    )
    # Chain C0–C1–C2–C3–C4: all five merge into one besties component.
    _relationships = pd.DataFrame(
        {
            "cabin_1": ["Cabin1"] * 4,
            "camper_1": [f"C{i}" for i in range(4)],
            "cabin_2": ["Cabin1"] * 4,
            "camper_2": [f"C{i + 1}" for i in range(4)],
            "relationship": ["besties"] * 4,
        }
    )

    def test_five_besties_in_one_cabin_solves_by_default(self):
        problem = SchedulingProblem(self._joined, self._setup, relationships=self._relationships)

        solution = run(problem, OptimizationConfig(solver=pulp.apis.PULP_CBC_CMD(msg=0)))

        assert solution.status.state == SolverState.OPTIMAL
