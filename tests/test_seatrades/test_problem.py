"""Tests for SchedulingProblem — domain data parsing and model building."""

import pandas as pd
import pulp

from seatrades.config import OptimizationConfig
from seatrades.problem import SchedulingProblem


class TestSchedulingProblemInit:
    """SchedulingProblem.__init__ parses domain data from two DataFrames."""

    def test_init_parses_domain_data(self, scheduling_problem):
        problem = scheduling_problem

        assert problem.cabins == ["Cabin1", "Cabin2"]
        # Campers get .{index} suffix from add_index_to_campername
        assert len(problem.campers) == 4
        assert all("." in c for c in problem.campers)

        assert problem.seatrades.tolist() == ["Archery", "Sailing", "Climbing", "Kayaking"]
        assert problem.fleets == ["1a", "1b", "2a", "2b"]

        # seatrades_full has all block_seatrade combinations
        assert "1a_Archery" in problem.seatrades_full
        assert "2b_Kayaking" in problem.seatrades_full
        assert len(problem.seatrades_full) == 4 * 4  # 4 fleets × 4 seatrades

        # cabin_camper_prefs indexed by camper with suffix, has cabin column
        assert problem.cabin_camper_prefs.index.name == "camper"
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
            "fleet_assignment": pulp.LpVariable.dicts(
                "Cabin_Fleet_Assignment",
                (sp.cabins, sp.fleets),
                lowBound=0,
                upBound=1,
                cat=pulp.LpBinary,
            ),
            "seatrade_assignment": pulp.LpVariable.dicts(
                "Seatrade_Fleet_Assignment",
                (sp.fleets, sp.seatrades),
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
        group2 = len(sp.fleets) * len(sp.seatrades) * sum(len(sp.campers_by_cabin[cabin]) for cabin in sp.cabins)
        group3 = len(sp.fleets) * len(sp.seatrades) * len(sp.campers)
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

    def test_add_capacity_constraints(self, scheduling_problem):
        sp = scheduling_problem
        problem = pulp.LpProblem("test_capacity")
        vars_ = self._make_vars(sp)

        sp._add_capacity_constraints(problem, vars_["camper_assignments"])

        # 2 constraints per seatrade_full entry (min + max)
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

    def test_add_fleet_assignment_constraints(self, scheduling_problem):
        sp = scheduling_problem
        problem = pulp.LpProblem("test_fleet_assign")
        vars_ = self._make_vars(sp)

        sp._add_fleet_assignment_constraints(problem, vars_["fleet_assignment"])

        # 2 block pairs × 2 cabins = 4
        expected = 2 * len(sp.cabins)
        assert len(problem.constraints) == expected
        assert any("_in_only_1_fleet_" in name for name in problem.constraints)

    def test_add_fleet_balance_constraints(self, scheduling_problem):
        sp = scheduling_problem
        problem = pulp.LpProblem("test_fleet_balance")
        vars_ = self._make_vars(sp)

        sp._add_fleet_balance_constraints(problem, vars_["fleet_assignment"])

        # 1 constraint per fleet
        assert len(problem.constraints) == len(sp.fleets)
        assert any("Roughly_half_of_cabins" in name for name in problem.constraints)

    def test_add_gender_balance_constraints(self, scheduling_problem):
        sp = scheduling_problem
        problem = pulp.LpProblem("test_gender_balance")
        vars_ = self._make_vars(sp)

        sp._add_gender_balance_constraints(problem, vars_["fleet_assignment"])

        # unique cabin genders × fleets (uses cabin_genders, not camper-level data)
        expected = len(sp.cabin_genders.unique()) * len(sp.fleets)
        assert len(problem.constraints) == expected
        assert any("Roughly_half_of" in name and "_cabins_in_fleet" in name for name in problem.constraints)

    def test_add_max_seatrades_per_fleet_constraints(self, scheduling_problem):
        sp = scheduling_problem
        problem = pulp.LpProblem("test_max_seatrades")
        vars_ = self._make_vars(sp)
        config = OptimizationConfig(max_seatrades_per_fleet=3)

        sp._add_max_seatrades_per_fleet_constraints(problem, vars_["seatrade_assignment"], config)

        assert len(problem.constraints) == len(sp.fleets)
        assert any("has_less_than" in name for name in problem.constraints)

    def test_add_max_seatrades_per_fleet_constraints_skipped_when_none(self, scheduling_problem):
        sp = scheduling_problem
        problem = pulp.LpProblem("test_max_seatrades_none")
        vars_ = self._make_vars(sp)
        config = OptimizationConfig(max_seatrades_per_fleet=None)

        sp._add_max_seatrades_per_fleet_constraints(problem, vars_["seatrade_assignment"], config)

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


class TestSeatradesDelegation:
    """Seatrades delegates domain parsing and model building to SchedulingProblem."""

    def test_seatrades_delegates_to_scheduling_problem(self, joined_campers_df, seatrade_setup_df):
        from seatrades.preferences import CamperSeatradePreferences, SeatradesConfig
        from seatrades.seatrades import Seatrades

        seatrades = Seatrades(
            CamperSeatradePreferences(joined_campers_df.copy()),
            SeatradesConfig(seatrade_setup_df.copy()),
        )

        assert isinstance(seatrades._problem, SchedulingProblem)
        assert seatrades.cabins == seatrades._problem.cabins
        assert seatrades.campers == seatrades._problem.campers
        assert seatrades.seatrades_full == seatrades._problem.seatrades_full

    def test_seatrades_assign_uses_scheduling_problem(self, joined_campers_df, seatrade_setup_df):
        from seatrades.preferences import CamperSeatradePreferences, SeatradesConfig
        from seatrades.seatrades import Seatrades

        seatrades = Seatrades(
            CamperSeatradePreferences(joined_campers_df.copy()),
            SeatradesConfig(seatrade_setup_df.copy()),
        )
        config = OptimizationConfig(solver=pulp.apis.PULP_CBC_CMD(msg=0))
        problem = seatrades.assign(config)

        assert isinstance(problem, pulp.LpProblem)
        assert seatrades.status == 1  # Optimal
