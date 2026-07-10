"""Unit tests for the pure infeasibility-diagnosis module.

Crafted domain inputs in, findings out — no solver, no Streamlit, no session
state. Each proven cause has a fixture that trips it and a healthy baseline that
does not. The reality fixtures that confirm the *solver* agrees live in the slow
solver tests; here we assert the structural check's behaviour directly and fast.
"""

import pandas as pd

from seatrades.diagnostics import Tier, diagnose


def _campers_all_preferring(seatrades: list[str], n: int) -> pd.DataFrame:
    """n campers who all rank the same four seatrades (a shared preferred union)."""
    return pd.DataFrame(
        [
            {
                "cabin": "Cabin1",
                "camper": f"Camper {i}",
                "seatrade_1": seatrades[0],
                "seatrade_2": seatrades[1],
                "seatrade_3": seatrades[2],
                "seatrade_4": seatrades[3],
            }
            for i in range(n)
        ]
    )


def test_capacity_shortfall_fires_when_campers_exceed_preferred_seats():
    """P1: 12 campers, 4 preferred seatrades each seating 1 → 2·4 = 8 seats < 12.

    A necessary feasibility condition is violated, so this is a PROVEN finding.
    """
    seatrades = ["Archery", "Crafts", "Climbing", "Sailing"]
    campers = _campers_all_preferring(seatrades, n=12)
    seatrade_setup = pd.DataFrame({"seatrade": seatrades, "campers_min": 0, "campers_max": 1})

    findings = diagnose(campers, seatrade_setup)

    assert findings, "expected a capacity-shortfall finding"
    assert findings[0].tier is Tier.PROVEN


def test_capacity_shortfall_quiet_on_a_healthy_baseline():
    """Same 12 campers, but every seatrade seats 10 → 2·40 = 80 seats ≫ 12.

    A comfortably-feasible input must not trip the check (no false positives).
    """
    seatrades = ["Archery", "Crafts", "Climbing", "Sailing"]
    campers = _campers_all_preferring(seatrades, n=12)
    seatrade_setup = pd.DataFrame({"seatrade": seatrades, "campers_min": 0, "campers_max": 10})

    assert diagnose(campers, seatrade_setup) == []


def test_max_seatrades_per_fleet_tightens_the_capacity_bound():
    """A fleet cap shrinks the usable seats: only its k busiest seatrades run.

    10 campers, 4 seatrades seating 2 → 2·8 = 16 seats is roomy. But capping a
    fleet to its 2 largest seatrades leaves 2·(2+2) = 8 seats < 10 → now infeasible.
    """
    seatrades = ["Archery", "Crafts", "Climbing", "Sailing"]
    campers = _campers_all_preferring(seatrades, n=10)
    seatrade_setup = pd.DataFrame({"seatrade": seatrades, "campers_min": 0, "campers_max": 2})

    assert diagnose(campers, seatrade_setup) == [], "uncapped, the seats are ample"
    assert diagnose(campers, seatrade_setup, max_seatrades_per_fleet=2), "the fleet cap starves it"
