"""Pure infeasibility diagnosis — why a solve produced no schedule.

Post-mortem only: functions over the joined domain data (campers, seatrade
setup) plus the config knobs they need — never Streamlit, the solver, or session
state. The service layer runs this only on an ``INFEASIBLE`` result and prepends
the findings above the retained generic failure copy.

A finding is a proven or suspected *cause* in the Captain's language plus a named
fix. Each proven cause is a necessary feasibility condition confirmed against the
real model; if the check fires, no schedule exists. This module ships one proven
cause — capacity shortfall (P1) — with later causes purely additive.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd

from seatrades.config import PREF_COLS


class Tier(Enum):
    """How certain a finding is. PROVEN = a necessary condition is violated, so
    infeasibility follows; SUSPECTED = a pressure signal, advisory only."""

    PROVEN = "proven"
    SUSPECTED = "suspected"


@dataclass
class Finding:
    """One diagnosed cause: its tier, a plain-language cause, and a named fix."""

    tier: Tier
    cause: str
    fix: str


def diagnose(
    joined_campers: pd.DataFrame,
    seatrade_setup: pd.DataFrame,
    *,
    max_seatrades_per_fleet: Optional[int] = None,
) -> list[Finding]:
    """Rank the causes of an infeasible solve, most-certain first.

    Runs the cheap named checks over the inputs + config knobs and returns their
    findings (proven before suspected). An empty list means no cause fired — the
    UI shows the honest "couldn't identify" fallback.
    """
    findings: list[Finding] = []
    capacity = _capacity_shortfall(joined_campers, seatrade_setup, max_seatrades_per_fleet)
    if capacity is not None:
        findings.append(capacity)
    return findings


def _capacity_shortfall(
    joined_campers: pd.DataFrame,
    seatrade_setup: pd.DataFrame,
    max_seatrades_per_fleet: Optional[int],
) -> Optional[Finding]:
    """P1: too many campers for the seats their preferred seatrades offer.

    Each camper fills one session per half-week, and within a half every seatrade
    runs in both fleet blocks — so the preferred-seatrade union offers
    ``2 · Σ campers_max`` seats. If more campers than that must be seated, no
    schedule fits them (a necessary condition). ``max_seatrades_per_fleet=k`` caps
    a fleet to its k busiest seatrades, so only the k largest caps count.
    """
    n_campers = len(joined_campers)
    preferred = _preferred_seatrades(joined_campers)
    caps = seatrade_setup.loc[seatrade_setup["seatrade"].isin(preferred), "campers_max"].tolist()
    if max_seatrades_per_fleet is not None:
        caps = sorted(caps, reverse=True)[:max_seatrades_per_fleet]
    seats = 2 * sum(caps)
    if n_campers <= seats:
        return None
    return Finding(
        tier=Tier.PROVEN,
        cause=(
            f"Too many campers for the seats they picked: {n_campers} campers need a spot each "
            f"half-week, but the seatrades they ranked seat only {seats} per half — so some "
            "campers can never be placed."
        ),
        fix=(
            "Raise *max campers* on the popular seatrades, add more seatrades, or (if set) "
            "raise or remove *Max seatrades per fleet* under Advanced settings."
        ),
    )


def _preferred_seatrades(joined_campers: pd.DataFrame) -> set[str]:
    """The union of every seatrade any camper ranked."""
    return set(pd.unique(joined_campers[PREF_COLS].to_numpy().ravel()))
