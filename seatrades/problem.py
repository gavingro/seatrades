"""SchedulingProblem — builds PuLP model from domain data."""

from typing import Hashable, Optional, cast

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
    # Fraction of a seatrade's capacity a cabin may fill for free before the soft
    # cabin-variety penalty kicks in. Fixed internal constant (not user-exposed);
    # structural effect is "ideally >= 4 cabins fill any seatrade."
    _CABIN_VARIETY_FREE_FRACTION = 0.25

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
        self.blocks = BLOCKS
        self.seatrades_full = [f"{block}_{seatrade}" for block in self.blocks for seatrade in self.seatrades]

        # Relationships reference campers by (cabin, camper); map them to integer IDs
        # so constraints can be expressed over the camper_assignments variables.
        camper_id_by_key: dict[tuple[str, str], int] = {
            (str(row.cabin), str(row.camper)): int(row.camper_id)  # type: ignore[arg-type]
            for row in joined_campers.itertuples(index=False)
        }

        def pairs_for(relationship: str) -> list[tuple[int, int]]:
            if relationships is None or relationships.empty:
                return []
            rows = relationships[relationships["relationship"] == relationship]
            return [
                (
                    camper_id_by_key[(str(row.cabin_1), str(row.camper_1))],
                    camper_id_by_key[(str(row.cabin_2), str(row.camper_2))],
                )
                for row in rows.itertuples(index=False)
            ]

        self.besties_pairs = pairs_for("besties")
        self.friends_pairs = pairs_for("friends")
        self.frenemies_pairs = pairs_for("frenemies")

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
        block_assignment = pulp.LpVariable.dicts(
            "Cabin_Block_Assignment",
            (self.cabins, self.blocks),
            lowBound=0,
            upBound=1,
            cat=pulp.LpBinary,
        )
        seatrade_assignment = pulp.LpVariable.dicts(
            "Seatrade_Fleet_Assignment",
            (self.blocks, self.seatrades),
            lowBound=0,
            upBound=1,
            cat=pulp.LpBinary,
        )

        self._add_linking_constraints(
            problem, camper_assignments, cabin_assignments, block_assignment, seatrade_assignment
        )
        self._add_assignment_constraints(problem, camper_assignments)
        self._add_no_duplicate_seatrade_constraints(problem, camper_assignments)
        self._add_capacity_constraints(problem, camper_assignments, seatrade_assignment, config)
        self._add_preference_constraints(problem, camper_assignments)
        self._add_top2_guarantee_constraints(problem, camper_assignments)
        self._add_cabin_share_cap_constraints(problem, camper_assignments, config)
        self._add_besties_constraints(problem, camper_assignments)
        self._add_friends_constraints(problem, camper_assignments)
        self._add_frenemies_constraints(problem, camper_assignments)
        self._add_block_assignment_constraints(problem, block_assignment)
        self._add_block_balance_constraints(problem, block_assignment)
        self._add_gender_balance_constraints(problem, block_assignment)
        self._add_same_fleet_constraints(problem, block_assignment, config)
        self._add_max_seatrades_per_fleet_constraints(problem, seatrade_assignment, config)
        self._add_objective(problem, camper_assignments, cabin_assignments, seatrade_assignment, config)

        return problem

    def _add_linking_constraints(
        self,
        problem: pulp.LpProblem,
        camper_assignments: VarDict,
        cabin_assignments: VarDict,
        block_assignment: VarDict,
        seatrade_assignment: VarDict,
    ) -> None:
        """Link helper variables to camper assignments so they track activation."""
        for s in self.seatrades_full:
            for cabin in self.cabins:
                for c in self.campers_by_cabin[cabin]:
                    problem += cabin_assignments[cabin][s] >= camper_assignments[c][s]

        for block in self.blocks:
            for seatrade in self.seatrades:
                full_name = f"{block}_{seatrade}"
                for cabin in self.cabins:
                    for c in self.campers_by_cabin[cabin]:
                        problem += block_assignment[cabin][block] >= camper_assignments[c][full_name]

        for block in self.blocks:
            for seatrade in self.seatrades:
                full_name = f"{block}_{seatrade}"
                for c in self.campers:
                    problem += seatrade_assignment[block][seatrade] >= camper_assignments[c][full_name]

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
                    pulp.lpSum([camper_assignments[c][f"{block}_{seatrade}"] for block in self.blocks]) <= 1,
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
            campers_max = self._seatrade_campers_max(s)
            camper_count = pulp.lpSum([camper_assignments[c][s] for c in self.campers])
            if config.allow_empty_sessions:
                running = seatrade_assignment[block][seatrade]
                problem += (camper_count >= campers_min * running, f"Min_if_running_{s}")
                problem += (camper_count <= campers_max * running, f"Max_if_running_{s}")
            else:
                problem += (camper_count >= campers_min, f"More_than_{campers_min}_in_{s}")
                problem += (camper_count <= campers_max, f"Less_than_{campers_max}_in_{s}")

    def _seatrade_campers_max(self, seatrade_full: str) -> int:
        """Max capacity of the seatrade named in a ``block_seatrade`` key (a pre-solve constant)."""
        return cast(int, self.seatrades_prefs.loc[seatrade_name(seatrade_full), "campers_max"])

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
                    for block in self.blocks
                    for s in preferences
                )
                <= 4,
                f"{c}_guaranteed_one_of_first_two_seatrades",
            )

    def _add_cabin_share_cap_constraints(
        self, problem: pulp.LpProblem, camper_assignments: VarDict, config: OptimizationConfig
    ) -> None:
        """Optional hard cap on any one cabin's share of a seatrade's capacity.

        Off by default: at ``max_cabin_share_per_seatrade == 1.0`` no constraint is added.
        Below 1.0, cap each cabin at ``round(share * campers_max)`` campers per seatrade —
        the same per-(cabin, session) sum as before, but per-seatrade and opt-in. Floored
        at 1 so a tiny-capacity seatrade (where ``round`` would give 0) never becomes
        unfillable — that would re-introduce the spurious infeasibility this feature removes.
        """
        if config.max_cabin_share_per_seatrade >= 1.0:
            return
        for s in self.seatrades_full:
            campers_max = self._seatrade_campers_max(s)
            cap = max(1, round(config.max_cabin_share_per_seatrade * campers_max))
            for cabin in self.cabins:
                problem += (
                    pulp.lpSum([camper_assignments[c][s] for c in self.campers_by_cabin[cabin]]) <= cap,
                    f"{cabin}_cabin_share_cap_{cap}_in_{s}",
                )

    def _add_besties_constraints(self, problem: pulp.LpProblem, camper_assignments: VarDict) -> None:
        """Besties pairs get identical schedules.

        Equating the camper's assignment for every block_seatrade forces the same
        seatrade in the same block for both blocks; the linking constraints then pull
        both campers' cabins into the same block. No auxiliary variables needed.
        """
        for c1, c2 in self.besties_pairs:
            for s in self.seatrades_full:
                problem += (
                    camper_assignments[c1][s] == camper_assignments[c2][s],
                    f"besties_{c1}_{c2}_{s}",
                )

    def _session_overlap_vars(
        self, problem: pulp.LpProblem, camper_assignments: VarDict, c1: int, c2: int
    ) -> dict[str, pulp.LpVariable]:
        """Auxiliary binary y[s] = AND(c1 in s, c2 in s), one per session.

        Linearized with the standard AND constraints so y[s] is 1 exactly when both
        campers occupy session s. Friends and frenemies both build on these.
        """
        overlap: dict[str, pulp.LpVariable] = {}
        for s in self.seatrades_full:
            y = pulp.LpVariable(f"overlap_{c1}_{c2}_{s}", cat=pulp.LpBinary)
            problem += y <= camper_assignments[c1][s]
            problem += y <= camper_assignments[c2][s]
            problem += y >= camper_assignments[c1][s] + camper_assignments[c2][s] - 1
            overlap[s] = y
        return overlap

    def _add_friends_constraints(self, problem: pulp.LpProblem, camper_assignments: VarDict) -> None:
        """Friends pairs share at least one session."""
        for c1, c2 in self.friends_pairs:
            overlap = self._session_overlap_vars(problem, camper_assignments, c1, c2)
            problem += (pulp.lpSum(overlap.values()) >= 1, f"friends_{c1}_{c2}")

    def _add_frenemies_constraints(self, problem: pulp.LpProblem, camper_assignments: VarDict) -> None:
        """Frenemies pairs share no session."""
        for c1, c2 in self.frenemies_pairs:
            overlap = self._session_overlap_vars(problem, camper_assignments, c1, c2)
            problem += (pulp.lpSum(overlap.values()) == 0, f"frenemies_{c1}_{c2}")

    def _add_block_assignment_constraints(self, problem: pulp.LpProblem, block_assignment: VarDict) -> None:
        """Each cabin is assigned to exactly one fleet per block pair."""
        for fleet_blocks in FLEET_BLOCKS:
            for cabin in self.cabins:
                problem += (
                    pulp.lpSum([block_assignment[cabin][f] for f in fleet_blocks]) == 1,
                    f"{cabin}_in_only_1_fleet_{fleet_blocks}",
                )

    def _add_block_balance_constraints(self, problem: pulp.LpProblem, block_assignment: VarDict) -> None:
        """Cabins are roughly evenly distributed across blocks."""
        half_of_the_cabins_min = len(self.cabins) // 2
        for block in self.blocks:
            problem += (
                pulp.lpSum([block_assignment[cabin][block] for cabin in self.cabins]) >= half_of_the_cabins_min,
                f"Roughly_half_of_cabins_in_block_{block}",
            )

    def _add_gender_balance_constraints(self, problem: pulp.LpProblem, block_assignment: VarDict) -> None:
        """Each gender's cabins are roughly evenly distributed across blocks."""
        for gender in self.cabin_genders.unique():
            gender_cabins = self.cabin_genders[self.cabin_genders == gender].index.tolist()
            half_of_the_gender_cabins_min = len(gender_cabins) // 2
            for block in self.blocks:
                problem += (
                    pulp.lpSum([block_assignment[cabin][block] for cabin in gender_cabins])
                    >= half_of_the_gender_cabins_min,
                    f"Roughly_half_of_{gender}_cabins_in_block_{block}",
                )

    def _add_same_fleet_constraints(
        self, problem: pulp.LpProblem, block_assignment: VarDict, config: OptimizationConfig
    ) -> None:
        """Optionally tie each cabin's fleet (AM/PM) to match across both halves (optional).

        When ``force_same_fleet_all_week`` is set, a cabin that is Morning (AM) in the first
        half must stay Morning in the second (and Afternoon stays Afternoon). Reuses the
        existing per-cabin block-selection variable — no new variables. Given each cabin
        already picks exactly one block per half, equating the AM blocks also pins the PM
        blocks, but both are stated for clarity.
        """
        if not config.force_same_fleet_all_week:
            return
        for cabin in self.cabins:
            problem += (block_assignment[cabin]["1a"] == block_assignment[cabin]["2a"], f"same_fleet_AM_{cabin}")
            problem += (block_assignment[cabin]["1b"] == block_assignment[cabin]["2b"], f"same_fleet_PM_{cabin}")

    def _add_max_seatrades_per_fleet_constraints(
        self, problem: pulp.LpProblem, seatrade_assignment: VarDict, config: OptimizationConfig
    ) -> None:
        """Cap the number of distinct seatrades per fleet (optional)."""
        if config.max_seatrades_per_fleet:
            for block in self.blocks:
                problem += (
                    pulp.lpSum([seatrade_assignment[block][seatrade] for seatrade in self.seatrades])
                    <= config.max_seatrades_per_fleet,
                    f"Ensure_{block}_has_less_than_{config.max_seatrades_per_fleet}_seatrades",
                )

    def _group_range_var(
        self,
        problem: pulp.LpProblem,
        label: str,
        memberships: list[tuple[int, pulp.LpAffineExpression]],
        big_m: int,
    ) -> pulp.LpAffineExpression:
        """Auxiliary range = maxAge - minAge for one age group, linearized.

        ``memberships`` pairs each candidate camper's age with its 0/1 membership
        expression for this group. Two continuous aux vars are pinned to reality:
        ``maxAge >= age*membership`` drives max down to the true max under minimization,
        ``minAge <= age + big_m*(1 - membership)`` drives min up to the true min. The final
        ``minAge <= maxAge`` pins an empty / not-running group to range 0. These links
        only define the aux vars — they forbid no assignment.
        """
        max_age = pulp.LpVariable(f"maxAge_{label}", lowBound=0)
        min_age = pulp.LpVariable(f"minAge_{label}", lowBound=0)
        for age, membership in memberships:
            problem += max_age >= age * membership
            problem += min_age <= age + big_m * (1 - membership)
        problem += min_age <= max_age
        return max_age - min_age

    def _age_penalty_term(
        self, problem: pulp.LpProblem, camper_assignments: VarDict, age_balance: float
    ) -> pulp.LpAffineExpression:
        """Unweighted age-grouping penalty: mean per-group age range, over sessions and blocks.

        ``age_balance`` blends the two levels, each normalized by its group count (mean
        range, not sum) so they are in comparable units and the midpoint is meaningful.
        Adds only definitional linking constraints; returns the objective term. The caller
        scales this by ``age_weight``.
        """
        ages = self.cabin_camper_prefs["age"].to_dict()
        big_m = int(self.cabin_camper_prefs["age"].max())

        session_ranges = []
        for s in self.seatrades_full:
            # Only preference-eligible campers can occupy this session; the rest are
            # pinned to 0 by the preference constraint and would add dead links.
            eligible = [c for c, prefs in self.camper_prefs.items() if seatrade_name(s) in prefs]
            memberships = [(ages[c], camper_assignments[c][s]) for c in eligible]
            session_ranges.append(self._group_range_var(problem, f"session_{s}", memberships, big_m))

        block_ranges = []
        for block in self.blocks:
            memberships = [
                (ages[c], pulp.lpSum(camper_assignments[c][f"{block}_{s}"] for s in self.seatrades))
                for c in self.campers
            ]
            block_ranges.append(self._group_range_var(problem, f"block_{block}", memberships, big_m))

        session_term = pulp.lpSum(session_ranges) / len(self.seatrades_full)
        fleet_term = pulp.lpSum(block_ranges) / len(self.blocks)
        return age_balance * session_term + (1 - age_balance) * fleet_term

    def _cabin_variety_penalty_term(
        self, problem: pulp.LpProblem, camper_assignments: VarDict
    ) -> pulp.LpAffineExpression:
        """Unweighted cabin-variety penalty: campers a cabin places in a seatrade above its
        free threshold, summed over all (cabin, session) pairs.

        Each seatrade gives a free threshold of ``round(_CABIN_VARIETY_FREE_FRACTION *
        campers_max)`` campers per cabin; each camper beyond it adds one to the penalty. The threshold keys off
        ``campers_max`` (a constant known pre-solve) so the term stays linear. Adds one
        non-negative ``excess`` variable per (cabin, session); the caller scales the sum by
        ``cabin_variety_weight``.
        """
        excess_vars = []
        for s in self.seatrades_full:
            campers_max = self._seatrade_campers_max(s)
            threshold = round(self._CABIN_VARIETY_FREE_FRACTION * campers_max)
            for cabin in self.cabins:
                cabin_count = pulp.lpSum(camper_assignments[c][s] for c in self.campers_by_cabin[cabin])
                excess = pulp.LpVariable(f"cabin_excess_{cabin}_{s}", lowBound=0)
                problem += excess >= cabin_count - threshold
                excess_vars.append(excess)
        return pulp.lpSum(excess_vars)

    def _add_objective(
        self,
        problem: pulp.LpProblem,
        camper_assignments: VarDict,
        cabin_assignments: VarDict,
        seatrade_assignment: VarDict,
        config: OptimizationConfig,
    ) -> None:
        """Minimize preference penalty, with optional cabin, sparsity, age-grouping, and cabin-variety terms."""
        objective = 0
        for c, preferences in self.camper_prefs.items():
            for block in self.blocks:
                objective += config.preference_weight * pulp.lpSum(
                    [camper_assignments[c][f"{block}_{s}"] * (preferences.index(s)) for s in preferences]
                )
        if config.cabins_weight:
            for s in self.seatrades_full:
                objective += config.cabins_weight * pulp.lpSum([cabin_assignments[cabin][s] for cabin in self.cabins])
        if config.sparsity_weight:
            for block in self.blocks:
                for s in self.seatrades:
                    objective += config.sparsity_weight * seatrade_assignment[block][s]
        if config.age_weight:
            objective += config.age_weight * self._age_penalty_term(problem, camper_assignments, config.age_balance)
        if config.cabin_variety_weight:
            objective += config.cabin_variety_weight * self._cabin_variety_penalty_term(problem, camper_assignments)
        problem += objective
