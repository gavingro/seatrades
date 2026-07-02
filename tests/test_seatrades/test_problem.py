"""Tests for SchedulingProblem — domain data parsing and model building."""

import pandas as pd
import pulp

from seatrades.config import OptimizationConfig
from seatrades.problem import SchedulingProblem, block_name, seatrade_name


class TestNamingHelpers:
    """``block_name`` and ``seatrade_name`` are complementary halves of the
    ``block_seatrade`` full-name format."""

    def test_block_name_strips_seatrade_suffix(self):
        assert block_name("1a_Archery") == "1a"

    def test_seatrade_name_strips_block_prefix(self):
        assert seatrade_name("1a_Archery") == "Archery"

    def test_helpers_split_on_first_underscore_only(self):
        # Seatrade names may themselves contain underscores; only the first splits.
        assert block_name("2b_Deep_Sea_Fishing") == "2b"
        assert seatrade_name("2b_Deep_Sea_Fishing") == "Deep_Sea_Fishing"


class TestSchedulingProblemInit:
    """SchedulingProblem.__init__ parses domain data from two DataFrames."""

    def test_init_parses_domain_data(self, scheduling_problem):
        problem = scheduling_problem

        assert problem.cabins == ["Cabin1", "Cabin2"]
        # Campers are zero-indexed integer IDs; names are tracked separately.
        assert problem.campers == [0, 1, 2, 3]
        assert problem.camper_names == ["Alice", "Bob", "Carol", "Dave"]

        assert problem.seatrades.tolist() == ["Archery", "Sailing", "Climbing", "Kayaking"]
        assert problem.blocks == ["1a", "1b", "2a", "2b"]

        # seatrades_full has all block_seatrade combinations
        assert "1a_Archery" in problem.seatrades_full
        assert "2b_Kayaking" in problem.seatrades_full
        assert len(problem.seatrades_full) == 4 * 4  # 4 blocks × 4 seatrades

        # cabin_camper_prefs indexed by integer camper_id, has cabin column
        assert problem.cabin_camper_prefs.index.name == "camper_id"
        assert "cabin" in problem.cabin_camper_prefs.columns

        # camper_prefs is a Series of preference lists
        assert isinstance(problem.camper_prefs, pd.Series)
        assert len(problem.camper_prefs) == 4

        # seatrades_prefs indexed by seatrade
        assert problem.seatrades_prefs.index.name == "seatrade"

        # campers_by_cabin is a pre-computed dict for O(1) lookup
        assert isinstance(problem.campers_by_cabin, dict)
        assert set(problem.campers_by_cabin.keys()) == set(problem.cabins)
        for _cabin, campers in problem.campers_by_cabin.items():
            assert all(c in problem.campers for c in campers)

        # cabin_genders maps each cabin to its majority gender
        assert set(problem.cabin_genders.index) == set(problem.cabins)

    def test_camper_ids_preserve_upload_order_not_alphabetical(self):
        """camper_id is the zero-indexed upload row position, never an alphabetical sort."""
        joined = pd.DataFrame(
            {
                "cabin": ["Cabin1", "Cabin1", "Cabin2", "Cabin2"],
                "camper": ["Zoe", "Alice", "Mona", "Bob"],
                "gender": ["F", "F", "F", "M"],
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
                "campers_min": [0] * 4,
                "campers_max": [10] * 4,
            }
        )

        problem = SchedulingProblem(joined, setup)

        assert problem.camper_ids == [0, 1, 2, 3]
        # Names stay in upload order — NOT sorted to Alice, Bob, Mona, Zoe.
        assert problem.camper_names == ["Zoe", "Alice", "Mona", "Bob"]


class TestSchedulingProblemBuild:
    """SchedulingProblem.build(config) creates an unsolved LpProblem."""

    def test_build_returns_unsolved_lp_problem(self, scheduling_problem, default_config):
        problem = scheduling_problem.build(default_config)

        assert isinstance(problem, pulp.LpProblem)
        assert problem.status == 0  # Not solved
        assert problem.name == "seatrades_assignment"

    def test_build_has_decision_variables(self, scheduling_problem, default_config):
        problem = scheduling_problem.build(default_config)

        # Should have camper assignment variables
        var_names = [v.name for v in problem.variables()]
        assert any("Camper_Assignments" in name for name in var_names)

    def test_build_has_constraints(self, scheduling_problem, default_config):
        problem = scheduling_problem.build(default_config)

        assert len(problem.constraints) > 0

    def test_build_has_objective(self, scheduling_problem, default_config):
        problem = scheduling_problem.build(default_config)

        assert problem.objective is not None

    def test_build_produces_consistent_constraints(self, scheduling_problem, default_config):
        """Build produces same constraint set on repeated calls — no solving required."""
        problem = scheduling_problem.build(default_config)
        assert len(problem.constraints) > 0

        problem2 = scheduling_problem.build(default_config)
        assert len(problem.constraints) == len(problem2.constraints)


class TestSchedulingProblemRebuild:
    """Build with different configs against same domain data."""

    def test_build_with_different_configs_produces_different_problems(self, scheduling_problem):
        config_a = OptimizationConfig(preference_weight=1)
        config_b = OptimizationConfig(preference_weight=10)

        problem_a = scheduling_problem.build(config_a)
        problem_b = scheduling_problem.build(config_b)

        assert problem_a is not problem_b
        assert problem_a.status == 0
        assert problem_b.status == 0

    def test_build_creates_fresh_problem_each_call(self, scheduling_problem, default_config):
        problem_a = scheduling_problem.build(default_config)
        problem_b = scheduling_problem.build(default_config)

        # Each call creates a new problem — no shared mutable state
        assert problem_a is not problem_b


class TestSchedulingProblemBesties:
    """Relationships map (cabin, camper) pairs to internal camper ids for the solver."""

    def test_besties_pair_mapped_to_camper_ids(self, joined_campers_df, seatrade_setup_df):
        relationships = pd.DataFrame(
            {
                "cabin_1": ["Cabin1"],
                "camper_1": ["Alice"],
                "cabin_2": ["Cabin2"],
                "camper_2": ["Carol"],
                "relationship": ["besties"],
            }
        )
        problem = SchedulingProblem(joined_campers_df, seatrade_setup_df, relationships=relationships)

        # Alice is row 0, Carol is row 2.
        assert problem.besties_pairs == [(0, 2)]

    def test_no_relationships_means_no_besties_pairs(self, scheduling_problem):
        assert scheduling_problem.besties_pairs == []

    def test_relationship_rows_split_by_type(self, joined_campers_df, seatrade_setup_df):
        relationships = pd.DataFrame(
            {
                "cabin_1": ["Cabin1", "Cabin1", "Cabin1"],
                "camper_1": ["Alice", "Bob", "Alice"],
                "cabin_2": ["Cabin2", "Cabin2", "Cabin2"],
                "camper_2": ["Carol", "Dave", "Dave"],
                "relationship": ["besties", "friends", "frenemies"],
            }
        )
        problem = SchedulingProblem(joined_campers_df, seatrade_setup_df, relationships=relationships)

        # camper_ids: Alice=0, Bob=1, Carol=2, Dave=3. Each list holds only its type.
        assert problem.besties_pairs == [(0, 2)]
        assert problem.friends_pairs == [(1, 3)]
        assert problem.frenemies_pairs == [(0, 3)]

    def test_no_relationships_means_no_friends_or_frenemies_pairs(self, scheduling_problem):
        assert scheduling_problem.friends_pairs == []
        assert scheduling_problem.frenemies_pairs == []


class TestSchedulingProblemConstraintGroups:
    """Each constraint-group method adds only its constraints to a fresh problem."""

    def _make_vars(self, sp):
        """Create variable dicts matching SchedulingProblem.build() structure."""
        return {
            "camper_assignments": pulp.LpVariable.dicts(
                "Camper_Assignments",
                (sp.campers, sp.seatrades_full),
                lowBound=0,
                upBound=1,
                cat=pulp.LpBinary,
            ),
            "cabin_assignments": pulp.LpVariable.dicts(
                "Cabin_Assignment",
                (sp.cabins, sp.seatrades_full),
                lowBound=0,
                upBound=1,
                cat=pulp.LpBinary,
            ),
            "block_assignment": pulp.LpVariable.dicts(
                "Cabin_Block_Assignment",
                (sp.cabins, sp.blocks),
                lowBound=0,
                upBound=1,
                cat=pulp.LpBinary,
            ),
            "seatrade_assignment": pulp.LpVariable.dicts(
                "Seatrade_Fleet_Assignment",
                (sp.blocks, sp.seatrades),
                lowBound=0,
                upBound=1,
                cat=pulp.LpBinary,
            ),
        }

    def test_add_linking_constraints(self, scheduling_problem):
        sp = scheduling_problem
        problem = pulp.LpProblem("test_linking")
        vars_ = self._make_vars(sp)

        sp._add_linking_constraints(problem, **vars_)

        group1 = sum(len(sp.campers_by_cabin[cabin]) for cabin in sp.cabins) * len(sp.seatrades_full)
        group2 = len(sp.blocks) * len(sp.seatrades) * sum(len(sp.campers_by_cabin[cabin]) for cabin in sp.cabins)
        group3 = len(sp.blocks) * len(sp.seatrades) * len(sp.campers)
        expected = group1 + group2 + group3
        assert len(problem.constraints) == expected

    def test_add_assignment_constraints(self, scheduling_problem):
        sp = scheduling_problem
        problem = pulp.LpProblem("test_assignment")
        vars_ = self._make_vars(sp)

        sp._add_assignment_constraints(problem, vars_["camper_assignments"])

        # 2 block pairs × 4 campers = 8
        assert len(problem.constraints) == 2 * len(sp.campers)
        assert any("_in_only_1_seatrade_block_" in name for name in problem.constraints)

    def test_add_no_duplicate_seatrade_constraints(self, scheduling_problem):
        sp = scheduling_problem
        problem = pulp.LpProblem("test_no_dup")
        vars_ = self._make_vars(sp)

        sp._add_no_duplicate_seatrade_constraints(problem, vars_["camper_assignments"])

        # 4 seatrades × 4 campers = 16
        assert len(problem.constraints) == len(sp.seatrades) * len(sp.campers)
        assert any("_cant_take_" in name and "_in_both_blocks" in name for name in problem.constraints)

    def test_add_capacity_constraints(self, scheduling_problem, default_config):
        sp = scheduling_problem
        problem = pulp.LpProblem("test_capacity")
        vars_ = self._make_vars(sp)

        sp._add_capacity_constraints(problem, vars_["camper_assignments"], vars_["seatrade_assignment"], default_config)

        # Conditional min (default): 2 constraints per seatrade_full entry, both gated on
        # the per-session running indicator.
        assert len(problem.constraints) == 2 * len(sp.seatrades_full)
        assert any("Min_if_running" in name for name in problem.constraints)
        assert any("Max_if_running" in name for name in problem.constraints)

    def test_add_capacity_constraints_legacy_force_fill(self, scheduling_problem):
        sp = scheduling_problem
        problem = pulp.LpProblem("test_capacity_legacy")
        vars_ = self._make_vars(sp)
        legacy_config = OptimizationConfig(allow_empty_sessions=False)

        sp._add_capacity_constraints(problem, vars_["camper_assignments"], vars_["seatrade_assignment"], legacy_config)

        # Legacy hard floor: ungated min + max per seatrade_full entry.
        assert len(problem.constraints) == 2 * len(sp.seatrades_full)
        assert any("More_than" in name for name in problem.constraints)
        assert any("Less_than" in name for name in problem.constraints)

    def test_add_preference_constraints(self, scheduling_problem):
        sp = scheduling_problem
        problem = pulp.LpProblem("test_preference")
        vars_ = self._make_vars(sp)

        sp._add_preference_constraints(problem, vars_["camper_assignments"])

        # 1 constraint per camper
        assert len(problem.constraints) == len(sp.campers)
        assert any("prefers_not_these" in name for name in problem.constraints)

    def test_add_top2_guarantee_constraints(self, scheduling_problem):
        sp = scheduling_problem
        problem = pulp.LpProblem("test_top2")
        vars_ = self._make_vars(sp)

        sp._add_top2_guarantee_constraints(problem, vars_["camper_assignments"])

        # 1 constraint per camper
        assert len(problem.constraints) == len(sp.campers)
        assert any("_guaranteed_one_of_first_two" in name for name in problem.constraints)

    def test_add_cabin_max_constraints(self, scheduling_problem):
        sp = scheduling_problem
        problem = pulp.LpProblem("test_cabin_max")
        vars_ = self._make_vars(sp)

        sp._add_cabin_max_constraints(problem, vars_["camper_assignments"])

        # 1 constraint per seatrade_full × cabin
        expected = len(sp.seatrades_full) * len(sp.cabins)
        assert len(problem.constraints) == expected
        assert any("_max_4_campers_to_" in name for name in problem.constraints)

    def test_add_block_assignment_constraints(self, scheduling_problem):
        sp = scheduling_problem
        problem = pulp.LpProblem("test_fleet_assign")
        vars_ = self._make_vars(sp)

        sp._add_block_assignment_constraints(problem, vars_["block_assignment"])

        # 2 block pairs × 2 cabins = 4
        expected = 2 * len(sp.cabins)
        assert len(problem.constraints) == expected
        assert any("_in_only_1_fleet_" in name for name in problem.constraints)

    def test_add_block_balance_constraints(self, scheduling_problem):
        sp = scheduling_problem
        problem = pulp.LpProblem("test_fleet_balance")
        vars_ = self._make_vars(sp)

        sp._add_block_balance_constraints(problem, vars_["block_assignment"])

        # 1 constraint per block
        assert len(problem.constraints) == len(sp.blocks)
        assert any("Roughly_half_of_cabins" in name for name in problem.constraints)

    def test_add_gender_balance_constraints(self, scheduling_problem):
        sp = scheduling_problem
        problem = pulp.LpProblem("test_gender_balance")
        vars_ = self._make_vars(sp)

        sp._add_gender_balance_constraints(problem, vars_["block_assignment"])

        # unique cabin genders × blocks (uses cabin_genders, not camper-level data)
        expected = len(sp.cabin_genders.unique()) * len(sp.blocks)
        assert len(problem.constraints) == expected
        assert any("Roughly_half_of" in name and "_cabins_in_block" in name for name in problem.constraints)

    def test_add_max_seatrades_per_fleet_constraints(self, scheduling_problem):
        sp = scheduling_problem
        problem = pulp.LpProblem("test_max_seatrades")
        vars_ = self._make_vars(sp)
        config = OptimizationConfig(max_seatrades_per_fleet=3)

        sp._add_max_seatrades_per_fleet_constraints(problem, vars_["seatrade_assignment"], config)

        assert len(problem.constraints) == len(sp.blocks)
        assert any("has_less_than" in name for name in problem.constraints)

    def test_add_max_seatrades_per_fleet_constraints_skipped_when_none(self, scheduling_problem):
        sp = scheduling_problem
        problem = pulp.LpProblem("test_max_seatrades_none")
        vars_ = self._make_vars(sp)
        config = OptimizationConfig(max_seatrades_per_fleet=None)

        sp._add_max_seatrades_per_fleet_constraints(problem, vars_["seatrade_assignment"], config)

        assert len(problem.constraints) == 0

    def test_add_besties_constraints(self, joined_campers_df, seatrade_setup_df):
        relationships = pd.DataFrame(
            {
                "cabin_1": ["Cabin1"],
                "camper_1": ["Alice"],
                "cabin_2": ["Cabin2"],
                "camper_2": ["Carol"],
                "relationship": ["besties"],
            }
        )
        sp = SchedulingProblem(joined_campers_df, seatrade_setup_df, relationships=relationships)
        problem = pulp.LpProblem("test_besties")
        vars_ = self._make_vars(sp)

        sp._add_besties_constraints(problem, vars_["camper_assignments"])

        # One equality per block_seatrade for the single besties pair.
        assert len(problem.constraints) == len(sp.seatrades_full)
        assert any(name.startswith("besties_") for name in problem.constraints)

    def test_add_besties_constraints_noop_without_relationships(self, scheduling_problem):
        sp = scheduling_problem
        problem = pulp.LpProblem("test_besties_none")
        vars_ = self._make_vars(sp)

        sp._add_besties_constraints(problem, vars_["camper_assignments"])

        assert len(problem.constraints) == 0

    def _relationships(self, relationship):
        return pd.DataFrame(
            {
                "cabin_1": ["Cabin1"],
                "camper_1": ["Alice"],
                "cabin_2": ["Cabin2"],
                "camper_2": ["Carol"],
                "relationship": [relationship],
            }
        )

    def test_add_friends_constraints(self, joined_campers_df, seatrade_setup_df):
        sp = SchedulingProblem(joined_campers_df, seatrade_setup_df, relationships=self._relationships("friends"))
        problem = pulp.LpProblem("test_friends")
        vars_ = self._make_vars(sp)

        sp._add_friends_constraints(problem, vars_["camper_assignments"])

        # Three AND-linearization constraints per session, plus one >=1 overlap sum.
        assert any(name.startswith("friends_") for name in problem.constraints)
        assert len(problem.constraints) == 3 * len(sp.seatrades_full) + 1

    def test_add_frenemies_constraints(self, joined_campers_df, seatrade_setup_df):
        sp = SchedulingProblem(joined_campers_df, seatrade_setup_df, relationships=self._relationships("frenemies"))
        problem = pulp.LpProblem("test_frenemies")
        vars_ = self._make_vars(sp)

        sp._add_frenemies_constraints(problem, vars_["camper_assignments"])

        assert any(name.startswith("frenemies_") for name in problem.constraints)
        assert len(problem.constraints) == 3 * len(sp.seatrades_full) + 1

    def test_add_friends_constraints_noop_without_relationships(self, scheduling_problem):
        sp = scheduling_problem
        problem = pulp.LpProblem("test_friends_none")
        vars_ = self._make_vars(sp)

        sp._add_friends_constraints(problem, vars_["camper_assignments"])
        sp._add_frenemies_constraints(problem, vars_["camper_assignments"])

        assert len(problem.constraints) == 0

    def test_add_objective(self, scheduling_problem):
        sp = scheduling_problem
        problem = pulp.LpProblem("test_objective")
        vars_ = self._make_vars(sp)
        config = OptimizationConfig()

        sp._add_objective(
            problem, vars_["camper_assignments"], vars_["cabin_assignments"], vars_["seatrade_assignment"], config
        )

        assert problem.objective is not None

    def test_add_age_penalty_creates_aux_vars_and_links(self, scheduling_problem, default_config):
        sp = scheduling_problem
        problem = pulp.LpProblem("test_age")
        vars_ = self._make_vars(sp)

        term = sp._age_penalty_term(problem, vars_["camper_assignments"], default_config.age_balance)

        # Two aux continuous vars (maxAge, minAge) per session group and per block group.
        var_names = [v.name for v in problem.variables()]
        assert any(name.startswith("maxAge_") for name in var_names)
        assert any(name.startswith("minAge_") for name in var_names)
        # Session links only for preference-eligible campers; block links over all campers.
        # Per group: 2 links per candidate camper + 1 (minAge <= maxAge).
        session_links = sum(
            2 * sum(1 for _c, prefs in sp.camper_prefs.items() if seatrade_name(s) in prefs) + 1
            for s in sp.seatrades_full
        )
        block_links = len(sp.blocks) * (2 * len(sp.campers) + 1)
        assert len(problem.constraints) == session_links + block_links
        assert term is not None

    def test_age_weight_zero_builds_no_age_penalty(self, scheduling_problem):
        """age_weight=0 reproduces the baseline: no age aux vars, no age links in the model."""
        problem = scheduling_problem.build(OptimizationConfig(age_weight=0))

        var_names = [v.name for v in problem.variables()]
        assert not any(name.startswith("maxAge_") or name.startswith("minAge_") for name in var_names)

    def test_empty_group_contributes_zero_age_range(self, scheduling_problem, default_config):
        """An empty / not-running session pins to range 0 — no negative-penalty farming."""
        problem = scheduling_problem.build(default_config)
        problem.solve(pulp.apis.PULP_CBC_CMD(msg=0))

        values = {v.name: v.value() for v in problem.variables()}
        session_ranges = [
            values[f"maxAge_session_{s}"] - values[f"minAge_session_{s}"] for s in scheduling_problem.seatrades_full
        ]
        # No group yields a negative range (the minAge <= maxAge pin holds).
        assert all(r >= -1e-6 for r in session_ranges)
        # 4 campers across 16 sessions leaves most sessions empty → range exactly 0.
        assert any(abs(r) < 1e-6 for r in session_ranges)

    def test_session_age_links_only_for_preference_eligible_campers(self, default_config):
        # 5 seatrades but 4 preferences each → every camper is ineligible for exactly one.
        joined = pd.DataFrame(
            {
                "cabin": ["Cabin1", "Cabin2"],
                "camper": ["Alice", "Bob"],
                "gender": ["F", "M"],
                "age": [13, 16],
                "seatrade_1": ["Archery", "Sailing"],
                "seatrade_2": ["Sailing", "Climbing"],
                "seatrade_3": ["Climbing", "Kayaking"],
                "seatrade_4": ["Kayaking", "Diving"],
            }
        )
        setup = pd.DataFrame(
            {
                "seatrade": ["Archery", "Sailing", "Climbing", "Kayaking", "Diving"],
                "campers_min": [0] * 5,
                "campers_max": [10] * 5,
            }
        )
        sp = SchedulingProblem(joined, setup)
        problem = pulp.LpProblem("test_age_eligibility")
        vars_ = self._make_vars(sp)
        camper_assignments = vars_["camper_assignments"]

        sp._age_penalty_term(problem, camper_assignments, default_config.age_balance)

        def in_session_links(session, assignment_var):
            """Whether assignment_var appears in the linking constraints of one session group."""
            group_vars = {f"maxAge_session_{session}", f"minAge_session_{session}"}
            return any(
                assignment_var.name in {v.name for v in con.keys()} and {v.name for v in con.keys()} & group_vars
                for con in problem.constraints.values()
            )

        # Alice (id 0) does not prefer Diving; Bob (id 1) does not prefer Archery — so they
        # are absent from those session groups' links...
        assert not in_session_links("1a_Diving", camper_assignments[0]["1a_Diving"])
        assert not in_session_links("1a_Archery", camper_assignments[1]["1a_Archery"])
        # ...but present in the session groups they are eligible for.
        assert in_session_links("1a_Archery", camper_assignments[0]["1a_Archery"])
        assert in_session_links("1a_Diving", camper_assignments[1]["1a_Diving"])
