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
