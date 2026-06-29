"""SchedulingProblem — builds PuLP model from domain data."""

from typing import Hashable, Optional

import pandas as pd
import pulp

from seatrades.config import PREF_COLS, OptimizationConfig

BLOCKS = ["1a", "1b", "2a", "2b"]
FLEET_BLOCKS = [["1a", "1b"], ["2a", "2b"]]


def block_name(seatrade_full: str) -> str:
    """Strip the seatrade suffix from a full seatrade name (``1a_Archery`` → ``1a``)."""
    return seatrade_full.split("_", 1)[0]


def seatrade_name(seatrade_full: str) -> str:
    """Strip the block prefix from a full seatrade name (``1a_Archery`` → ``Archery``)."""
    return seatrade_full.split("_", 1)[1]


class SchedulingProblem:
    """Parses domain data and builds PuLP optimization models.

    Holds parsed domain state from camper/seatrade DataFrames.
    Call ``build(config)`` to create an unsolved LpProblem with a specific
    optimization configuration.
    """

    VarDict = dict[Hashable, dict[str, pulp.LpVariable]]
    _CABIN_MAX_PER_SEATRADE = 4

    def __init__(
        self,
        joined_campers: pd.DataFrame,
        seatrade_setup: pd.DataFrame,
        relationships: Optional[pd.DataFrame] = None,
    ):
        # Campers are identified internally by zero-indexed integer IDs (row
        # position), never by name. IDs are unique by construction, so they key
        # PuLP variables without the name-collision hack and never leak to output.
        joined_campers = joined_campers.reset_index(drop=True).copy()
        joined_campers["camper_id"] = range(len(joined_campers))

        self.camper_ids = joined_campers["camper_id"].tolist()
        self.camper_names = joined_campers["camper"].tolist()
        self.campers = self.camper_ids  # MILP identifier — integer IDs

        self.cabin_camper_prefs = joined_campers.set_index("camper_id")
        self.cabins = joined_campers["cabin"].unique().tolist()
        self.campers_by_cabin = joined_campers.groupby("cabin")["camper_id"].apply(list).to_dict()
        self.camper_prefs = joined_campers.set_index("camper_id")[PREF_COLS].apply(list, axis="columns")
        self.cabin_genders = self.cabin_camper_prefs.groupby("cabin")["gender"].agg(lambda grp: pd.Series.mode(grp)[0])

        self.seatrades_prefs = seatrade_setup.set_index("seatrade")
        self.seatrades = seatrade_setup["seatrade"]
        self.fleets = BLOCKS
        self.seatrades_full = [f"{block}_{seatrade}" for block in self.fleets for seatrade in self.seatrades]

        # Relationships reference campers by (cabin, camper); map them to integer IDs
        # so constraints can be expressed over the camper_assignments variables.
        camper_id_by_key: dict[tuple[str, str], int] = {
            (str(row.cabin), str(row.camper)): int(row.camper_id)  # type: ignore[arg-type]
            for row in joined_campers.itertuples(index=False)
        }
        self.besties_pairs: list[tuple[int, int]] = []
        if relationships is not None and not relationships.empty:
            besties = relationships[relationships["relationship"] == "besties"]
            for row in besties.itertuples(index=False):
                self.besties_pairs.append(
                    (
                        camper_id_by_key[(str(row.cabin_1), str(row.camper_1))],
                        camper_id_by_key[(str(row.cabin_2), str(row.camper_2))],
                    )
                )

    def build(self, config: OptimizationConfig) -> pulp.LpProblem:
        """Build an unsolved LpProblem from domain data and optimization config.

        Returns a PuLP problem with all variables, constraints, and objective
        set up but NOT solved. Call ``problem.solve()`` separately.
        """
        problem = pulp.LpProblem(name="seatrades_assignment")

        camper_assignments = pulp.LpVariable.dicts(
            "Camper_Assignments",
            (self.campers, self.seatrades_full),
            lowBound=0,
            upBound=1,
            cat=pulp.LpBinary,
        )
        cabin_assignments = pulp.LpVariable.dicts(
            "Cabin_Assignment",
            (self.cabins, self.seatrades_full),
            lowBound=0,
            upBound=1,
            cat=pulp.LpBinary,
        )
        fleet_assignment = pulp.LpVariable.dicts(
            "Cabin_Fleet_Assignment",
            (self.cabins, self.fleets),
            lowBound=0,
            upBound=1,
            cat=pulp.LpBinary,
        )
        seatrade_assignment = pulp.LpVariable.dicts(
            "Seatrade_Fleet_Assignment",
            (self.fleets, self.seatrades),
            lowBound=0,
            upBound=1,
            cat=pulp.LpBinary,
        )

        self._add_linking_constraints(
            problem, camper_assignments, cabin_assignments, fleet_assignment, seatrade_assignment
        )
        self._add_assignment_constraints(problem, camper_assignments)
        self._add_no_duplicate_seatrade_constraints(problem, camper_assignments)
        self._add_capacity_constraints(problem, camper_assignments, seatrade_assignment, config)
        self._add_preference_constraints(problem, camper_assignments)
        self._add_top2_guarantee_constraints(problem, camper_assignments)
        self._add_cabin_max_constraints(problem, camper_assignments)
        self._add_besties_constraints(problem, camper_assignments)
        self._add_fleet_assignment_constraints(problem, fleet_assignment)
        self._add_fleet_balance_constraints(problem, fleet_assignment)
        self._add_gender_balance_constraints(problem, fleet_assignment)
        self._add_max_seatrades_per_fleet_constraints(problem, seatrade_assignment, config)
        self._add_objective(problem, camper_assignments, cabin_assignments, seatrade_assignment, config)

        return problem

    def _add_linking_constraints(
        self,
        problem: pulp.LpProblem,
        camper_assignments: VarDict,
        cabin_assignments: VarDict,
        fleet_assignment: VarDict,
        seatrade_assignment: VarDict,
    ) -> None:
        """Link helper variables to camper assignments so they track activation."""
        for s in self.seatrades_full:
            for cabin in self.cabins:
                for c in self.campers_by_cabin[cabin]:
                    problem += cabin_assignments[cabin][s] >= camper_assignments[c][s]

        for fleet in self.fleets:
            for seatrade in self.seatrades:
                full_name = f"{fleet}_{seatrade}"
                for cabin in self.cabins:
                    for c in self.campers_by_cabin[cabin]:
                        problem += fleet_assignment[cabin][fleet] >= camper_assignments[c][full_name]

        for fleet in self.fleets:
            for seatrade in self.seatrades:
                full_name = f"{fleet}_{seatrade}"
                for c in self.campers:
                    problem += seatrade_assignment[fleet][seatrade] >= camper_assignments[c][full_name]

    def _add_assignment_constraints(self, problem: pulp.LpProblem, camper_assignments: VarDict) -> None:
        """Each camper is assigned exactly one seatrade per block pair."""
        for block_index, fleet_blocks in enumerate(FLEET_BLOCKS):
            block_seatrades = [f"{block}_{seatrade}" for block in fleet_blocks for seatrade in self.seatrades]
            for c in self.campers:
                problem += (
                    pulp.lpSum([camper_assignments[c][s] for s in block_seatrades]) == 1,
                    f"{c}_in_only_1_seatrade_block_{block_index}",
                )

    def _add_no_duplicate_seatrade_constraints(self, problem: pulp.LpProblem, camper_assignments: VarDict) -> None:
        """No camper takes the same seatrade in more than one block pair."""
        for seatrade in self.seatrades:
            for c in self.campers:
                problem += (
                    pulp.lpSum([camper_assignments[c][f"{fleet}_{seatrade}"] for fleet in self.fleets]) <= 1,
                    f"{c}_cant_take_{seatrade}_in_both_blocks",
                )

    def _add_capacity_constraints(
        self,
        problem: pulp.LpProblem,
        camper_assignments: VarDict,
        seatrade_assignment: VarDict,
        config: OptimizationConfig,
    ) -> None:
        """Bound each session's camper count by min/max capacity.

        With ``allow_empty_sessions`` (default), the min/max bounds are gated on the
        per-session ``running`` indicator: a session may have 0 campers (it doesn't run)
        or a count in ``[campers_min, campers_max]`` (it runs). With the flag off, the
        legacy hard floor force-fills ``campers_min`` into every session.
        """
        for s in self.seatrades_full:
            block = block_name(s)
            seatrade = seatrade_name(s)
            campers_min = self.seatrades_prefs.loc[seatrade, "campers_min"]
            campers_max = self.seatrades_prefs.loc[seatrade, "campers_max"]
            camper_count = pulp.lpSum([camper_assignments[c][s] for c in self.campers])
            if config.allow_empty_sessions:
                running = seatrade_assignment[block][seatrade]
                problem += (camper_count >= campers_min * running, f"Min_if_running_{s}")
                problem += (camper_count <= campers_max * running, f"Max_if_running_{s}")
            else:
                problem += (camper_count >= campers_min, f"More_than_{campers_min}_in_{s}")
                problem += (camper_count <= campers_max, f"Less_than_{campers_max}_in_{s}")

    def _add_preference_constraints(self, problem: pulp.LpProblem, camper_assignments: VarDict) -> None:
        """Campers cannot be assigned to seatrades they didn't request."""
        for c, seatrade_prefs in self.camper_prefs.items():
            problem += (
                pulp.lpSum(
                    [camper_assignments[c][s] for s in self.seatrades_full if seatrade_name(s) not in seatrade_prefs]
                )
                == 0,
                f"{c}_prefers_not_these_seatrades",
            )

    def _add_top2_guarantee_constraints(self, problem: pulp.LpProblem, camper_assignments: VarDict) -> None:
        """Each camper gets at least one seatrade from their top 2 choices."""
        for c, preferences in self.camper_prefs.items():
            # sum(pref_index) <= 4 guarantees at least one choice from top-2 (rank 0 or 1)
            problem += (
                pulp.lpSum(
                    camper_assignments[c][f"{block}_{s}"] * (preferences.index(s))
                    for block in self.fleets
                    for s in preferences
                )
                <= 4,
                f"{c}_guaranteed_one_of_first_two_seatrades",
            )

    def _add_cabin_max_constraints(self, problem: pulp.LpProblem, camper_assignments: VarDict) -> None:
        """At most _CABIN_MAX_PER_SEATRADE campers from the same cabin per seatrade."""
        for s in self.seatrades_full:
            for cabin in self.cabins:
                problem += (
                    pulp.lpSum([camper_assignments[c][s] for c in self.campers_by_cabin[cabin]])
                    <= self._CABIN_MAX_PER_SEATRADE,
                    f"{cabin}_max_{self._CABIN_MAX_PER_SEATRADE}_campers_to_{s}",
                )

    def _add_besties_constraints(self, problem: pulp.LpProblem, camper_assignments: VarDict) -> None:
        """Besties pairs get identical schedules.

        Equating the camper's assignment for every block_seatrade forces the same
        seatrade in the same block for both blocks; the linking constraints then pull
        both campers' cabins into the same fleet. No auxiliary variables needed.
        """
        for c1, c2 in self.besties_pairs:
            for s in self.seatrades_full:
                problem += (
                    camper_assignments[c1][s] == camper_assignments[c2][s],
                    f"besties_{c1}_{c2}_{s}",
                )

    def _add_fleet_assignment_constraints(self, problem: pulp.LpProblem, fleet_assignment: VarDict) -> None:
        """Each cabin is assigned to exactly one fleet per block pair."""
        for fleet_blocks in FLEET_BLOCKS:
            for cabin in self.cabins:
                problem += (
                    pulp.lpSum([fleet_assignment[cabin][f] for f in fleet_blocks]) == 1,
                    f"{cabin}_in_only_1_fleet_{fleet_blocks}",
                )

    def _add_fleet_balance_constraints(self, problem: pulp.LpProblem, fleet_assignment: VarDict) -> None:
        """Cabins are roughly evenly distributed across fleets."""
        half_of_the_cabins_min = len(self.cabins) // 2
        for fleet in self.fleets:
            problem += (
                pulp.lpSum([fleet_assignment[cabin][fleet] for cabin in self.cabins]) >= half_of_the_cabins_min,
                f"Roughly_half_of_cabins_in_fleet_{fleet}",
            )

    def _add_gender_balance_constraints(self, problem: pulp.LpProblem, fleet_assignment: VarDict) -> None:
        """Each gender's cabins are roughly evenly distributed across fleets."""
        for gender in self.cabin_genders.unique():
            gender_cabins = self.cabin_genders[self.cabin_genders == gender].index.tolist()
            half_of_the_gender_cabins_min = len(gender_cabins) // 2
            for fleet in self.fleets:
                problem += (
                    pulp.lpSum([fleet_assignment[cabin][fleet] for cabin in gender_cabins])
                    >= half_of_the_gender_cabins_min,
                    f"Roughly_half_of_{gender}_cabins_in_fleet_{fleet}",
                )

    def _add_max_seatrades_per_fleet_constraints(
        self, problem: pulp.LpProblem, seatrade_assignment: VarDict, config: OptimizationConfig
    ) -> None:
        """Cap the number of distinct seatrades per fleet (optional)."""
        if config.max_seatrades_per_fleet:
            for fleet in self.fleets:
                problem += (
                    pulp.lpSum([seatrade_assignment[fleet][seatrade] for seatrade in self.seatrades])
                    <= config.max_seatrades_per_fleet,
                    f"Ensure_{fleet}_has_less_than_{config.max_seatrades_per_fleet}_seatrades",
                )

    def _add_objective(
        self,
        problem: pulp.LpProblem,
        camper_assignments: VarDict,
        cabin_assignments: VarDict,
        seatrade_assignment: VarDict,
        config: OptimizationConfig,
    ) -> None:
        """Minimize preference penalty, with optional cabin-distribution and sparsity terms."""
        objective = 0
        for c, preferences in self.camper_prefs.items():
            for block in self.fleets:
                objective += config.preference_weight * pulp.lpSum(
                    [camper_assignments[c][f"{block}_{s}"] * (preferences.index(s)) for s in preferences]
                )
        if config.cabins_weight:
            for s in self.seatrades_full:
                objective += config.cabins_weight * pulp.lpSum([cabin_assignments[cabin][s] for cabin in self.cabins])
        if config.sparsity_weight:
            for fleet in self.fleets:
                for s in self.seatrades:
                    objective += config.sparsity_weight * seatrade_assignment[fleet][s]
        problem += objective
