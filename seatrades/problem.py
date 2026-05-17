"""SchedulingProblem — builds PuLP model from domain data."""

import logging
from typing import Any

import pandas as pd
import pulp

from seatrades.config import OptimizationConfig
from seatrades.preferences import add_index_to_campername

logger = logging.getLogger(__name__)


class SchedulingProblem:
    """Parses domain data and builds PuLP optimization models.

    Holds parsed domain state from camper/seatrade DataFrames.
    Call ``build(config)`` to create an unsolved LpProblem with a specific
    optimization configuration.
    """

    def __init__(self, joined_campers: pd.DataFrame, seatrade_setup: pd.DataFrame):
        joined_campers = add_index_to_campername(joined_campers)
        self.cabin_camper_prefs = joined_campers.set_index("camper")
        self.cabins = joined_campers["cabin"].unique().tolist()
        self.campers_by_cabin = joined_campers.groupby("cabin")["camper"].apply(list).to_dict()
        self.camper_prefs = joined_campers.set_index("camper")[
            ["seatrade_1", "seatrade_2", "seatrade_3", "seatrade_4"]
        ].apply(list, axis="columns")
        self.campers = joined_campers["camper"].tolist()
        self.cabin_genders = self.cabin_camper_prefs.groupby("cabin")["gender"].agg(lambda grp: pd.Series.mode(grp)[0])

        self.seatrades_prefs = seatrade_setup.set_index("seatrade")
        self.seatrades = seatrade_setup["seatrade"]
        self.seatrades1a = [f"1a_{seatrade}" for seatrade in self.seatrades]
        self.seatrades1b = [f"1b_{seatrade}" for seatrade in self.seatrades]
        self.seatrades2a = [f"2a_{seatrade}" for seatrade in self.seatrades]
        self.seatrades2b = [f"2b_{seatrade}" for seatrade in self.seatrades]
        self.seatrades_full = self.seatrades1a + self.seatrades1b + self.seatrades2a + self.seatrades2b
        self.fleets = ["1a", "1b", "2a", "2b"]

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
        self._add_capacity_constraints(problem, camper_assignments)
        self._add_preference_constraints(problem, camper_assignments)
        self._add_top2_guarantee_constraints(problem, camper_assignments)
        self._add_cabin_max_constraints(problem, camper_assignments)
        self._add_fleet_assignment_constraints(problem, fleet_assignment)
        self._add_fleet_balance_constraints(problem, fleet_assignment)
        self._add_gender_balance_constraints(problem, fleet_assignment)
        self._add_max_seatrades_per_fleet_constraints(problem, seatrade_assignment, config)
        self._add_objective(problem, camper_assignments, cabin_assignments, seatrade_assignment, config)

        return problem

    VarDict = dict[Any, dict[Any, pulp.LpVariable]]

    def _add_linking_constraints(
        self,
        problem: pulp.LpProblem,
        camper_assignments: VarDict,
        cabin_assignments: VarDict,
        fleet_assignment: VarDict,
        seatrade_assignment: VarDict,
    ):
        """Link helper variables to camper assignments so they track activation."""
        for s in self.seatrades_full:
            for cabin in self.cabins:
                for c in self.campers_by_cabin[cabin]:
                    problem += cabin_assignments[cabin][s] >= camper_assignments[c][s]

        for fleet in self.fleets:
            for seatrade in self.seatrades:
                s = f"{fleet}_{seatrade}"
                for cabin in self.cabins:
                    for c in self.campers_by_cabin[cabin]:
                        problem += fleet_assignment[cabin][fleet] >= camper_assignments[c][s]

        for fleet in self.fleets:
            for seatrade in self.seatrades:
                s = f"{fleet}_{seatrade}"
                for c in self.campers:
                    problem += seatrade_assignment[fleet][seatrade] >= camper_assignments[c][s]

    def _add_assignment_constraints(self, problem: pulp.LpProblem, camper_assignments: VarDict):
        """Each camper is assigned exactly one seatrade per block pair."""
        for block_index, seatrades in enumerate(
            [self.seatrades1a + self.seatrades1b, self.seatrades2a + self.seatrades2b],
        ):
            for c in self.campers:
                problem += (
                    pulp.lpSum([camper_assignments[c][s] for s in seatrades]) == 1,
                    f"{c}_in_only_1_seatrade_block_{block_index}",
                )

    def _add_no_duplicate_seatrade_constraints(self, problem: pulp.LpProblem, camper_assignments: VarDict):
        """No camper takes the same seatrade in more than one block pair."""
        for seatrade in self.seatrades:
            for c in self.campers:
                problem += (
                    pulp.lpSum(
                        [
                            camper_assignments[c][f"1a_{seatrade}"],
                            camper_assignments[c][f"1b_{seatrade}"],
                            camper_assignments[c][f"2a_{seatrade}"],
                            camper_assignments[c][f"2b_{seatrade}"],
                        ]
                    )
                    <= 1,
                    f"{c} can't take {seatrade} in both blocks",
                )

    def _add_capacity_constraints(self, problem: pulp.LpProblem, camper_assignments: VarDict):
        """Seatrade camper counts stay within min/max capacity bounds."""
        for s in self.seatrades_full:
            seatrade = s[3:]
            seatrade_campers_min = self.seatrades_prefs.loc[seatrade, "campers_min"]
            problem += (
                pulp.lpSum([camper_assignments[c][s] for c in self.campers]) >= seatrade_campers_min,
                f"More_than_{seatrade_campers_min}_in_{s}",
            )
            seatrade_campers_max = self.seatrades_prefs.loc[seatrade, "campers_max"]
            problem += (
                pulp.lpSum([camper_assignments[c][s] for c in self.campers]) <= seatrade_campers_max,
                f"Less_than_{seatrade_campers_max}_in_{s}",
            )

    def _add_preference_constraints(self, problem: pulp.LpProblem, camper_assignments: VarDict):
        """Campers cannot be assigned to seatrades they didn't request."""
        for c, seatrade_prefs in self.camper_prefs.items():
            problem += (
                pulp.lpSum([camper_assignments[c][s] for s in self.seatrades_full if s[3:] not in seatrade_prefs]) == 0,
                f"{c}_prefers_not_these_seatrades.",
            )

    def _add_top2_guarantee_constraints(self, problem: pulp.LpProblem, camper_assignments: VarDict):
        """Each camper gets at least one seatrade from their top 2 choices."""
        for c, preferences in self.camper_prefs.items():
            # sum(pref_index) <= 4 guarantees at least one choice from top-2 (rank 0 or 1)
            problem += (
                pulp.lpSum(
                    [camper_assignments[c][f"1a_{s}"] * (preferences.index(s)) for s in preferences]
                    + [camper_assignments[c][f"1b_{s}"] * (preferences.index(s)) for s in preferences]
                    + [camper_assignments[c][f"2a_{s}"] * (preferences.index(s)) for s in preferences]
                    + [camper_assignments[c][f"2b_{s}"] * (preferences.index(s)) for s in preferences]
                )
                <= 4,
                f"{c} guaranteed one of the first two seatrades.",
            )

    def _add_cabin_max_constraints(self, problem: pulp.LpProblem, camper_assignments: VarDict):
        """At most 4 campers from the same cabin per seatrade."""
        for s in self.seatrades_full:
            for cabin in self.cabins:
                problem += (
                    pulp.lpSum([camper_assignments[c][s] for c in self.campers_by_cabin[cabin]]) <= 4,
                    f"{cabin} must contribute <= 4 campers to {s}.",
                )

    def _add_fleet_assignment_constraints(self, problem: pulp.LpProblem, fleet_assignment: VarDict):
        """Each cabin is assigned to exactly one fleet per block pair."""
        for fleet_blocks in [["1a", "1b"], ["2a", "2b"]]:
            for cabin in self.cabins:
                problem += (
                    pulp.lpSum([fleet_assignment[cabin][f] for f in fleet_blocks]) == 1,
                    f"{cabin}_in_only_1_fleet_{fleet_blocks}",
                )

    def _add_fleet_balance_constraints(self, problem: pulp.LpProblem, fleet_assignment: VarDict):
        """Cabins are roughly evenly distributed across fleets."""
        half_of_the_cabins_min = len(self.cabins) // 2
        for fleet in self.fleets:
            problem += (
                pulp.lpSum([fleet_assignment[cabin][fleet] for cabin in self.cabins]) >= half_of_the_cabins_min,
                f"Roughly_half_of_cabins_in_fleet_{fleet}",
            )

    def _add_gender_balance_constraints(self, problem: pulp.LpProblem, fleet_assignment: VarDict):
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
    ):
        """Cap the number of distinct seatrades per fleet (optional)."""
        if config.max_seatrades_per_fleet:
            for fleet in self.fleets:
                problem += (
                    pulp.lpSum([seatrade_assignment[fleet][seatrade] for seatrade in self.seatrades])
                    <= config.max_seatrades_per_fleet,
                    f"Ensure_{fleet}_has_less_than_{config.max_seatrades_per_fleet}_seatrades.",
                )

    def _add_objective(
        self,
        problem: pulp.LpProblem,
        camper_assignments: VarDict,
        cabin_assignments: VarDict,
        seatrade_assignment: VarDict,
        config: OptimizationConfig,
    ):
        """Minimize preference penalty, with optional cabin-distribution and sparsity terms."""
        obj = 0
        for c, preferences in self.camper_prefs.items():
            for block in self.fleets:
                obj += config.preference_weight * pulp.lpSum(
                    [camper_assignments[c][f"{block}_{s}"] * (preferences.index(s)) for s in preferences]
                )
        if config.cabins_weight:
            for s in self.seatrades_full:
                obj += config.cabins_weight * pulp.lpSum([cabin_assignments[cabin][s] for cabin in self.cabins])
        if config.sparsity_weight:
            for fleet in self.fleets:
                for s in self.seatrades:
                    obj += config.sparsity_weight * seatrade_assignment[fleet][s]
        problem += obj
