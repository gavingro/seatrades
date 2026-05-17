"""Seatrades — orchestrates scheduling via SchedulingProblem."""

import logging

import pandas as pd
import pulp

from seatrades.config import OptimizationConfig
from seatrades.preferences import (
    CamperSeatradePreferences,
    SeatradesConfig,
)
from seatrades.problem import SchedulingProblem

logger = logging.getLogger(__name__)


class Seatrades:
    """Orchestrates seatrade assignment via SchedulingProblem + solver."""

    def __init__(
        self,
        cabin_camper_prefs: CamperSeatradePreferences,
        seatrades_prefs: SeatradesConfig,
    ):
        self._problem = SchedulingProblem(cabin_camper_prefs, seatrades_prefs)  # type: ignore[arg-type]
        self.assignments: pd.DataFrame
        self.status = 0

    @property
    def cabins(self) -> list[str]:
        return self._problem.cabins

    @property
    def campers(self) -> list[str]:
        return self._problem.campers

    @property
    def seatrades_full(self) -> list[str]:
        return self._problem.seatrades_full

    @property
    def cabin_camper_prefs(self) -> pd.DataFrame:
        return self._problem.cabin_camper_prefs

    @property
    def camper_prefs(self) -> pd.Series:
        return self._problem.camper_prefs

    @property
    def seatrades_prefs(self) -> pd.DataFrame:
        return self._problem.seatrades_prefs

    @property
    def seatrades(self) -> pd.Series:
        return self._problem.seatrades

    @property
    def fleets(self) -> list[str]:
        return self._problem.fleets

    def assign(self, config: OptimizationConfig) -> pulp.LpProblem:
        """Build and solve the scheduling problem.

        Parameters
        ----------
        config : OptimizationConfig
            Optimization weights and solver configuration.

        Returns
        -------
        pulp.LpProblem
            The solved LpProblem instance.
        """
        problem = self._problem.build(config)
        status = problem.solve(config.solver)
        self.status = status if status else -1
        # Extract camper assignment variables from solved problem
        camper_vars: dict[str, dict[str, float]] = {}
        for v in problem.variables():
            if v.name.startswith("Camper_Assignments_"):
                # Variable name format: Camper_Assignments_{camper}_{seatrade}
                # Remove prefix, split on last underscore... but camper names have dots
                # Format: Camper_Assignments_{camper}_{fleet}_{seatrade}
                # camper may contain dots (e.g., "Alice.0")
                # seatrade is fleet_seatrade (e.g., "1a_Archery")
                name = v.name[len("Camper_Assignments_") :]
                # Find the first underscore that's part of a fleet prefix (1a_, 1b_, 2a_, 2b_)
                # to split camper from seatrade_slot
                camper = None
                seatrade_slot = None
                for fleet in self.fleets:
                    prefix = f"_{fleet}_"
                    idx = name.find(prefix)
                    if idx != -1:
                        camper = name[:idx]
                        seatrade_slot = name[idx + 1 :]  # fleet_seatrade
                        break
                if camper and seatrade_slot:
                    if camper not in camper_vars:
                        camper_vars[camper] = {}
                    camper_vars[camper][seatrade_slot] = pulp.value(v)
        self.assignments = pd.DataFrame(camper_vars).transpose()
        # Ensure column order matches seatrades_full
        self.assignments = self.assignments[self.seatrades_full]
        return problem
