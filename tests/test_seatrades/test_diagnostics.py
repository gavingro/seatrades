"""Unit tests for the pure infeasibility-diagnosis module.

Crafted domain inputs in, findings out — no solver, no Streamlit, no session
state. Each proven cause has a fixture that trips it and a healthy baseline that
does not. The reality fixtures that confirm the *solver* agrees live in the slow
solver tests; here we assert the structural check's behaviour directly and fast.
"""

from itertools import combinations

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

    5 campers, 4 seatrades seating 2 → 2·8 = 16 seats, and the demand-2 matching
    fits comfortably, so nothing fires uncapped. But capping a fleet to its single
    busiest seatrade leaves 2·2 = 4 seats < 5 campers → P1's capacity bound fires.
    """
    seatrades = ["Archery", "Crafts", "Climbing", "Sailing"]
    campers = _campers_all_preferring(seatrades, n=5)
    seatrade_setup = pd.DataFrame({"seatrade": seatrades, "campers_min": 0, "campers_max": 2})

    assert diagnose(campers, seatrade_setup) == [], "uncapped, the seats are ample"
    assert diagnose(campers, seatrade_setup, max_seatrades_per_fleet=1), "the fleet cap starves it"


def _roster(rows: list[dict]) -> pd.DataFrame:
    """Joined-campers frame from explicit (cabin, camper, prefs) rows."""
    return pd.DataFrame(
        [
            {
                "cabin": row["cabin"],
                "camper": row["camper"],
                "seatrade_1": row["prefs"][0],
                "seatrade_2": row["prefs"][1],
                "seatrade_3": row["prefs"][2],
                "seatrade_4": row["prefs"][3],
            }
            for row in rows
        ]
    )


# A crowd all wanting the same four popular seatrades — those stay well above any
# campers_min, so they are "live". Reused as healthy filler around a crafted victim.
_POPULAR = ["Sailing", "Kayaking", "Rowing", "Canoeing"]


def _crowd(cabin: str, n: int) -> list[dict]:
    return [{"cabin": cabin, "camper": f"Crowd {i}", "prefs": _POPULAR} for i in range(n)]


def test_starved_seatrade_fires_when_a_campers_only_live_pick_is_one():
    """M1: a camper whose picks are three solo-ranked niche seatrades + one popular.

    The three niche seatrades are ranked by that camper alone (popularity 1 <
    campers_min 2), so they can never run — the camper has a single live pick and
    cannot fill two sessions. A necessary condition is violated → PROVEN.
    """
    victim = {"cabin": "Tillikum", "camper": "Robin", "prefs": ["Whittling", "Birding", "Poetry", "Sailing"]}
    campers = _roster(_crowd("Spindrift", 6) + [victim])
    all_seatrades = _POPULAR + ["Whittling", "Birding", "Poetry"]
    seatrade_setup = pd.DataFrame({"seatrade": all_seatrades, "campers_min": 2, "campers_max": 10})

    findings = diagnose(campers, seatrade_setup)

    assert findings, "expected a starved-seatrade finding"
    assert findings[0].tier is Tier.PROVEN
    assert "Robin" in findings[0].cause and "Tillikum" in findings[0].cause
    assert "Whittling" in findings[0].cause


def test_starved_seatrade_quiet_when_every_pick_can_run():
    """Same roster, but the victim ranks four popular (live) seatrades → no starve."""
    victim = {"cabin": "Tillikum", "camper": "Robin", "prefs": _POPULAR}
    campers = _roster(_crowd("Spindrift", 6) + [victim])
    seatrade_setup = pd.DataFrame({"seatrade": _POPULAR, "campers_min": 2, "campers_max": 10})

    assert diagnose(campers, seatrade_setup) == []


def test_top2_both_starved_fires_when_both_top_picks_cannot_run():
    """M2: victim's top two picks are dead, but picks 3–4 are live.

    Two live picks means the camper *can* be placed (M1 stays quiet), yet the top-2
    guarantee — one of their first two choices — cannot hold. A distinct PROVEN cause.
    """
    victim = {"cabin": "Tillikum", "camper": "Robin", "prefs": ["Birding", "Poetry", "Sailing", "Kayaking"]}
    campers = _roster(_crowd("Spindrift", 6) + [victim])
    all_seatrades = _POPULAR + ["Birding", "Poetry"]
    seatrade_setup = pd.DataFrame({"seatrade": all_seatrades, "campers_min": 2, "campers_max": 10})

    findings = diagnose(campers, seatrade_setup)

    assert findings, "expected a top-2-starved finding"
    top2 = [f for f in findings if "top two" in f.cause.lower() or "top-2" in f.cause.lower()]
    assert top2, f"expected a top-2 finding, got {[f.cause for f in findings]}"
    assert top2[0].tier is Tier.PROVEN
    assert "Robin" in top2[0].cause


def test_top2_starved_quiet_when_top_picks_can_run():
    """A placeable camper whose top two picks are both live must not trip M2."""
    victim = {"cabin": "Tillikum", "camper": "Robin", "prefs": _POPULAR}
    campers = _roster(_crowd("Spindrift", 6) + [victim])
    seatrade_setup = pd.DataFrame({"seatrade": _POPULAR, "campers_min": 2, "campers_max": 10})

    assert diagnose(campers, seatrade_setup) == []


def test_top2_starved_not_double_reported_when_camper_fully_starved():
    """A fully-starved camper (M1) is the stronger statement — no duplicate M2."""
    victim = {"cabin": "Tillikum", "camper": "Robin", "prefs": ["Birding", "Poetry", "Whittling", "Sailing"]}
    campers = _roster(_crowd("Spindrift", 6) + [victim])
    all_seatrades = _POPULAR + ["Birding", "Poetry", "Whittling"]
    seatrade_setup = pd.DataFrame({"seatrade": all_seatrades, "campers_min": 2, "campers_max": 10})

    findings = [f for f in diagnose(campers, seatrade_setup) if "Robin" in f.cause]

    assert len(findings) == 1, f"expected one finding for Robin, got {[f.cause for f in findings]}"


def _relationships(pairs: list[tuple]) -> pd.DataFrame:
    """Relationships frame from (cabin_1, camper_1, cabin_2, camper_2, type) tuples."""
    return pd.DataFrame(pairs, columns=["cabin_1", "camper_1", "cabin_2", "camper_2", "relationship"])


def _all_seatrades_setup(rows: list[dict]) -> pd.DataFrame:
    """Setup where every ranked seatrade is live (campers_min 0) with ample capacity."""
    seatrades = sorted({s for row in rows for s in row["prefs"]})
    return pd.DataFrame({"seatrade": seatrades, "campers_min": 0, "campers_max": 10})


def test_besties_chain_no_common_ground_fires_on_a_transitive_chain():
    """B1: A–B–C besties chain, each pair sharing 2 seatrades, but no common pair.

    Pairwise validation passes (A∩B and B∩C each ≥ 2); the whole group's
    intersection is a single seatrade, so no identical two-session schedule exists
    for all three — a PROVEN cause validation cannot see.
    """
    rows = [
        {"cabin": "Otter", "camper": "Ash", "prefs": ["Sailing", "Kayaking", "Rowing", "Canoeing"]},
        {"cabin": "Otter", "camper": "Bo", "prefs": ["Sailing", "Kayaking", "Archery", "Crafts"]},
        {"cabin": "Otter", "camper": "Cy", "prefs": ["Kayaking", "Archery", "Climbing", "Dance"]},
    ]
    rels = _relationships(
        [
            ("Otter", "Ash", "Otter", "Bo", "besties"),
            ("Otter", "Bo", "Otter", "Cy", "besties"),
        ]
    )

    findings = diagnose(_roster(rows), _all_seatrades_setup(rows), relationships=rels)

    assert findings, "expected a besties-chain finding"
    assert findings[0].tier is Tier.PROVEN
    for name in ("Ash", "Bo", "Cy"):
        assert name in findings[0].cause


def test_besties_chain_quiet_when_group_shares_two_seatrades():
    """A chain whose members all share two seatrades has a valid identical schedule."""
    rows = [
        {"cabin": "Otter", "camper": "Ash", "prefs": ["Sailing", "Kayaking", "Rowing", "Canoeing"]},
        {"cabin": "Otter", "camper": "Bo", "prefs": ["Sailing", "Kayaking", "Archery", "Crafts"]},
        {"cabin": "Otter", "camper": "Cy", "prefs": ["Sailing", "Kayaking", "Climbing", "Dance"]},
    ]
    rels = _relationships(
        [
            ("Otter", "Ash", "Otter", "Bo", "besties"),
            ("Otter", "Bo", "Otter", "Cy", "besties"),
        ]
    )

    assert diagnose(_roster(rows), _all_seatrades_setup(rows), relationships=rels) == []


_TRIO_SHARING_TWO = [
    {"cabin": "Otter", "camper": "Ash", "prefs": ["Sailing", "Kayaking", "Rowing", "Canoeing"]},
    {"cabin": "Otter", "camper": "Bo", "prefs": ["Sailing", "Kayaking", "Archery", "Crafts"]},
    {"cabin": "Otter", "camper": "Cy", "prefs": ["Sailing", "Kayaking", "Climbing", "Dance"]},
]
_TRIO_BESTIES = [
    ("Otter", "Ash", "Otter", "Bo", "besties"),
    ("Otter", "Bo", "Otter", "Cy", "besties"),
]


def test_besties_group_too_big_for_seatrade_fires_when_shared_seatrades_cannot_hold_them():
    """B3: a besties trio shares exactly two seatrades, both seating only two.

    B1 stays quiet (they share two), but neither shared seatrade can hold all three
    who must attend as one — a PROVEN capacity cause naming the group and seatrade.
    """
    setup = pd.DataFrame(
        {
            "seatrade": ["Sailing", "Kayaking", "Rowing", "Canoeing", "Archery", "Crafts", "Climbing", "Dance"],
            "campers_min": 0,
            "campers_max": [2, 2, 10, 10, 10, 10, 10, 10],
        }
    )

    findings = diagnose(_roster(_TRIO_SHARING_TWO), setup, relationships=_relationships(_TRIO_BESTIES))

    hits = [f for f in findings if "Ash" in f.cause and "Sailing" in f.cause]
    assert hits, f"expected a besties-capacity finding, got {[f.cause for f in findings]}"
    assert hits[0].tier is Tier.PROVEN


def test_besties_group_too_big_quiet_when_shared_seatrade_has_room():
    """The same trio and shared seatrades, seating ten — they fit together."""
    setup = _all_seatrades_setup(_TRIO_SHARING_TWO)  # campers_max 10 everywhere

    assert diagnose(_roster(_TRIO_SHARING_TWO), setup, relationships=_relationships(_TRIO_BESTIES)) == []


def test_besties_group_too_big_for_cabin_fires_only_when_the_share_cap_is_on():
    """B2: a same-cabin besties trio whose shared seatrades seat ten (B3 quiet).

    With the opt-in cabin-share cap off (default 1.0) nothing fires. Slide it to
    25%: each cabin is capped at round(0.25·10)=2 per seatrade, below the trio of 3
    who must share a session — a PROVEN cause that exists only because the cap is set.
    """
    roster = _roster(_TRIO_SHARING_TWO)
    setup = _all_seatrades_setup(_TRIO_SHARING_TWO)  # campers_max 10 — the session itself fits
    rels = _relationships(_TRIO_BESTIES)

    assert diagnose(roster, setup, relationships=rels) == [], "cap off by default → no B2"

    findings = diagnose(roster, setup, relationships=rels, max_cabin_share_per_seatrade=0.25)
    hits = [f for f in findings if "Ash" in f.cause and "cabin" in f.cause.lower()]
    assert hits, f"expected a cabin-cap finding, got {[f.cause for f in findings]}"
    assert hits[0].tier is Tier.PROVEN


def test_besties_frenemies_contradiction_fires_when_a_frenemies_pair_is_in_a_besties_group():
    """R1: a frenemies pair sits inside a besties chain — identical AND disjoint.

    Ash–Bo–Cy are a besties chain (one group), but Ash and Cy are also frenemies.
    Besties force identical schedules; frenemies force zero overlap — a flat
    contradiction, so no schedule exists. PROVEN, naming the contradictory pair.
    """
    rels = _relationships(
        [
            ("Otter", "Ash", "Otter", "Bo", "besties"),
            ("Otter", "Bo", "Otter", "Cy", "besties"),
            ("Otter", "Ash", "Otter", "Cy", "frenemies"),
        ]
    )

    findings = diagnose(_roster(_TRIO_SHARING_TWO), _all_seatrades_setup(_TRIO_SHARING_TWO), relationships=rels)

    hits = [f for f in findings if "Ash" in f.cause and "Cy" in f.cause and "frenem" in f.cause.lower()]
    assert hits, f"expected a besties/frenemies contradiction, got {[f.cause for f in findings]}"
    assert hits[0].tier is Tier.PROVEN


def test_besties_frenemies_contradiction_quiet_when_frenemies_pair_is_outside_the_group():
    """A frenemies pair with a camper outside the besties group is no contradiction."""
    rows = _TRIO_SHARING_TWO + [{"cabin": "Seal", "camper": "Di", "prefs": ["Rowing", "Dance", "Archery", "Crafts"]}]
    rels = _relationships(
        [
            ("Otter", "Ash", "Otter", "Bo", "besties"),
            ("Otter", "Bo", "Otter", "Cy", "besties"),
            ("Otter", "Ash", "Seal", "Di", "frenemies"),
        ]
    )

    findings = diagnose(_roster(rows), _all_seatrades_setup(rows), relationships=rels)

    assert not [f for f in findings if "refuse to share" in f.cause]


_HUB = {"cabin": "Otter", "camper": "Hub", "prefs": ["Sailing", "Kayaking", "Rowing", "Canoeing"]}
# Four friends, each sharing exactly one distinct seatrade with the hub.
_PINNED_FRIENDS = [
    {"cabin": "Otter", "camper": "F1", "prefs": ["Sailing", "Archery", "Crafts", "Dance"]},
    {"cabin": "Otter", "camper": "F2", "prefs": ["Kayaking", "Archery", "Crafts", "Dance"]},
    {"cabin": "Otter", "camper": "F3", "prefs": ["Rowing", "Archery", "Crafts", "Dance"]},
    {"cabin": "Otter", "camper": "F4", "prefs": ["Canoeing", "Archery", "Crafts", "Dance"]},
]


def _friends_of_hub(friends: list[dict]) -> pd.DataFrame:
    return _relationships([("Otter", "Hub", f["cabin"], f["camper"], "friends") for f in friends])


def test_friends_hub_fires_when_friends_need_more_than_two_seatrades():
    """FH: the hub attends two seatrades, but four friends each want a different one.

    No two of the hub's seatrades can share a session with all four friends, so at
    least one friendship must break — a PROVEN 2-cover deficiency, naming hub + friends.
    """
    rows = [_HUB] + _PINNED_FRIENDS
    findings = diagnose(_roster(rows), _all_seatrades_setup(rows), relationships=_friends_of_hub(_PINNED_FRIENDS))

    hits = [f for f in findings if "Hub" in f.cause and "F4" in f.cause]
    assert hits, f"expected a friends-hub finding, got {[f.cause for f in findings]}"
    assert hits[0].tier is Tier.PROVEN


def test_friends_hub_quiet_when_two_seatrades_cover_every_friend():
    """Two friends pinned to two of the hub's seatrades are coverable → no hub."""
    rows = [_HUB] + _PINNED_FRIENDS[:2]
    findings = diagnose(_roster(rows), _all_seatrades_setup(rows), relationships=_friends_of_hub(_PINNED_FRIENDS[:2]))

    assert not [f for f in findings if "Hub" in f.cause]


def _frenemies_clique(cabin: str, names: list[str]) -> pd.DataFrame:
    """Every camper in `names` marked mutual frenemies with every other (a clique)."""
    return _relationships([(cabin, a, cabin, b, "frenemies") for a, b in combinations(names, 2)])


def test_frenemies_clash_fires_when_a_same_cabin_clique_outnumbers_their_seatrades():
    """FC: five same-cabin mutual frenemies who all rank the same four seatrades.

    The cabin shares a block, and frenemies can't share a session, so five need five
    distinct seatrades — but they rank only four. A pigeonhole PROVEN cause.
    """
    shared = ["Sailing", "Kayaking", "Rowing", "Canoeing"]
    names = [f"Fr{i}" for i in range(5)]
    rows = [{"cabin": "Otter", "camper": n, "prefs": shared} for n in names]

    findings = diagnose(_roster(rows), _all_seatrades_setup(rows), relationships=_frenemies_clique("Otter", names))

    hits = [f for f in findings if "Otter" in f.cause and "refuse to share" in f.cause]
    assert hits, f"expected a frenemies-clash finding, got {[f.cause for f in findings]}"
    assert hits[0].tier is Tier.PROVEN


def test_frenemies_clash_quiet_when_clique_fits_their_seatrades():
    """Four mutual frenemies over four shared seatrades can each take a distinct one."""
    shared = ["Sailing", "Kayaking", "Rowing", "Canoeing"]
    names = [f"Fr{i}" for i in range(4)]
    rows = [{"cabin": "Otter", "camper": n, "prefs": shared} for n in names]

    findings = diagnose(_roster(rows), _all_seatrades_setup(rows), relationships=_frenemies_clique("Otter", names))

    assert not [f for f in findings if "refuse to share" in f.cause]


# A complete bipartite set of frenemies edges between two cabins' campers — one
# connected cross-cabin group with no same-cabin edge (so the proven clash stays quiet).
def _cross_cabin_frenemies(cabin_a: str, a_names: list[str], cabin_b: str, b_names: list[str]) -> pd.DataFrame:
    return _relationships([(cabin_a, a, cabin_b, b, "frenemies") for a in a_names for b in b_names])


def test_cross_cabin_frenemies_overlap_flags_a_tight_multi_cabin_group():
    """S2: four mutual frenemies split across two cabins, all ranking the same four.

    Keeping every cross-cabin pair out of a shared session is tight against only four
    ranked seatrades — but whether it actually breaks depends on block/fleet placement
    (they may land in different blocks anyway), so it surfaces as an advisory hint, not
    a proof. No same-cabin edge exists, so the proven same-cabin clash stays silent.
    """
    shared = ["Sailing", "Kayaking", "Rowing", "Canoeing"]
    rows = [
        {"cabin": "Otter", "camper": "A1", "prefs": shared},
        {"cabin": "Otter", "camper": "A2", "prefs": shared},
        {"cabin": "Seal", "camper": "B1", "prefs": shared},
        {"cabin": "Seal", "camper": "B2", "prefs": shared},
    ]
    rels = _cross_cabin_frenemies("Otter", ["A1", "A2"], "Seal", ["B1", "B2"])

    suspected = _suspected(diagnose(_roster(rows), _all_seatrades_setup(rows), relationships=rels))

    assert suspected, "expected a cross-cabin frenemies pressure hint"
    assert any("frenem" in f.cause.lower() for f in suspected)


def test_cross_cabin_frenemies_overlap_quiet_when_they_rank_many_seatrades():
    """Same four cross-cabin frenemies, but their picks span eight seatrades → slack."""
    rows = [
        {"cabin": "Otter", "camper": "A1", "prefs": ["Sailing", "Kayaking", "Rowing", "Canoeing"]},
        {"cabin": "Otter", "camper": "A2", "prefs": ["Archery", "Crafts", "Climbing", "Dance"]},
        {"cabin": "Seal", "camper": "B1", "prefs": ["Sailing", "Archery", "Rowing", "Dance"]},
        {"cabin": "Seal", "camper": "B2", "prefs": ["Kayaking", "Crafts", "Climbing", "Canoeing"]},
    ]
    rels = _cross_cabin_frenemies("Otter", ["A1", "A2"], "Seal", ["B1", "B2"])

    assert diagnose(_roster(rows), _all_seatrades_setup(rows), relationships=rels) == []


def _gendered_cabins(cabin_genders: dict[str, str], per_cabin: int = 2) -> pd.DataFrame:
    """Roster of small cabins, each all-one-gender, all ranking the same four seatrades.

    Small cabins ranking roomy seatrades keep every capacity/cohesion signal quiet, so
    only the gender-balance signal can speak. Carries the ``gender`` column production
    data always has (the plain ``_roster`` helper omits it).
    """
    rows = []
    for cabin, gender in cabin_genders.items():
        for i in range(per_cabin):
            rows.append(
                {
                    "cabin": cabin,
                    "camper": f"{cabin} {i}",
                    "gender": gender,
                    "seatrade_1": "Sailing",
                    "seatrade_2": "Kayaking",
                    "seatrade_3": "Rowing",
                    "seatrade_4": "Canoeing",
                }
            )
    return pd.DataFrame(rows)


_ROOMY_SETUP = pd.DataFrame(
    {"seatrade": ["Sailing", "Kayaking", "Rowing", "Canoeing"], "campers_min": 0, "campers_max": 10}
)


def test_gender_balance_vs_same_fleet_flags_a_dominant_gender_when_locked():
    """S3: seven of eight cabins are boys and the same-fleet-all-week lock is ON.

    Gender balance wants each gender's cabins split evenly across the blocks, but the
    lock pins every cabin's fleet across both halves — so a gender holding most cabins
    strains that split. It's a pressure, not a proof (the split may still work out), so
    it's advisory, and only when the opt-in lock is engaged.
    """
    genders = {f"Cabin{i}": "male" for i in range(7)}
    genders["Cabin7"] = "female"

    suspected = _suspected(diagnose(_gendered_cabins(genders), _ROOMY_SETUP, force_same_fleet_all_week=True))

    assert suspected, "expected a gender-balance-vs-fleet hint"
    assert any("fleet" in f.cause.lower() for f in suspected)


def test_gender_balance_vs_same_fleet_quiet_without_the_lock():
    """The same lopsided roster is fine when the fleet lock is off — balance has slack."""
    genders = {f"Cabin{i}": "male" for i in range(7)}
    genders["Cabin7"] = "female"

    assert diagnose(_gendered_cabins(genders), _ROOMY_SETUP) == []


def test_gender_balance_vs_same_fleet_quiet_when_genders_are_balanced():
    """Locked, but an even boy/girl cabin split balances comfortably → no hint."""
    genders = {f"Cabin{i}": ("male" if i % 2 else "female") for i in range(8)}

    assert diagnose(_gendered_cabins(genders), _ROOMY_SETUP, force_same_fleet_all_week=True) == []


def test_balance_vs_minimum_flags_a_seatrade_whose_demand_barely_clears_its_floor():
    """S5: Sailing needs 5 to run but only 6 campers rank it.

    Gender balance splits a cabin's campers across the two blocks, so a seatrade's demand
    lands split roughly in half — and a seatrade whose whole following (6) barely clears its
    floor (5) can drop below it in a block once split, so it may not run there. A pressure,
    not a proof (the split may fall its way), and Sailing is *live* — its 6 fans clear the
    floor overall — so this is distinct from a starved (dead) seatrade. Advisory.
    """
    seatrades = ["Sailing", "Kayaking", "Rowing", "Canoeing"]
    campers = _campers_all_preferring(seatrades, n=6)
    setup = pd.DataFrame({"seatrade": seatrades, "campers_min": [5, 0, 0, 0], "campers_max": 10})

    suspected = _suspected(diagnose(campers, setup))

    assert suspected, "expected a balance-vs-minimum hint"
    assert any("Sailing" in f.cause for f in suspected)


def test_balance_vs_minimum_quiet_when_demand_comfortably_clears_the_floor():
    """Twelve campers rank Sailing against a floor of five → 12 ≥ 2·5, room to split."""
    seatrades = ["Sailing", "Kayaking", "Rowing", "Canoeing"]
    campers = _campers_all_preferring(seatrades, n=12)
    setup = pd.DataFrame({"seatrade": seatrades, "campers_min": [5, 0, 0, 0], "campers_max": 10})

    assert diagnose(campers, setup) == []


def test_matching_backstop_fires_on_a_subset_deficiency_the_named_checks_miss():
    """Backstop: 5 campers all ranking the same 4 seatrades that each seat one.

    Each camper needs two distinct sessions; the four seatrades run in both blocks,
    offering 2·4 = 8 seats, but five campers demand 2·5 = 10. No named check sees it —
    P1 compares 5 campers to 8 seats (demand-1) and stays quiet, the picks are all live
    (M1/M2 quiet), and there are no relationships. The matching backstop catches the
    demand-2 shortfall and names the deficient campers. PROVEN (a necessary condition).
    """
    seatrades = ["Sailing", "Kayaking", "Rowing", "Canoeing"]
    campers = _campers_all_preferring(seatrades, n=5)
    seatrade_setup = pd.DataFrame({"seatrade": seatrades, "campers_min": 0, "campers_max": 1})

    findings = diagnose(campers, seatrade_setup)

    assert findings, "expected a matching-deficiency finding"
    assert findings[0].tier is Tier.PROVEN
    assert "Camper 0" in findings[0].cause and "Camper 4" in findings[0].cause


def test_matching_backstop_quiet_on_a_healthy_baseline():
    """The same five campers, but every picked seatrade seats ten → 2·40 seats each.

    The demand-2 matching fits with room to spare, so a necessary condition holds and
    the backstop stays silent — it must never false-positive on a feasible roster.
    """
    seatrades = ["Sailing", "Kayaking", "Rowing", "Canoeing"]
    campers = _campers_all_preferring(seatrades, n=5)
    seatrade_setup = pd.DataFrame({"seatrade": seatrades, "campers_min": 0, "campers_max": 10})

    assert diagnose(campers, seatrade_setup) == []


def test_matching_backstop_does_not_run_when_a_named_check_already_fired():
    """Gating: 12 campers, 4 seatrades seating one — both P1 and the backstop apply.

    P1 (capacity shortfall) fires on the demand-1 count, and the demand-2 backstop
    would too, but the backstop runs *only* when the named checks come up empty. So
    exactly one *proven* finding returns — the named P1 cause — never a duplicate
    backstop line. (Advisory suspected hints may sit below it; they aren't proven.)
    """
    seatrades = ["Archery", "Crafts", "Climbing", "Sailing"]
    campers = _campers_all_preferring(seatrades, n=12)
    seatrade_setup = pd.DataFrame({"seatrade": seatrades, "campers_min": 0, "campers_max": 1})

    proven = [f for f in diagnose(campers, seatrade_setup) if f.tier is Tier.PROVEN]

    assert len(proven) == 1, f"expected only the named P1 finding, got {[f.cause for f in proven]}"
    assert "Too many campers" in proven[0].cause
    assert "can't all be placed" not in proven[0].cause


# --- Suspected tier: advisory pressure hints (issue #114) --------------------
# Each signal fires an advisory SUSPECTED hint on pressure and stays silent on a
# comfortably-feasible baseline (no coupling to a solve outcome — that would flake).


def _suspected(findings):
    """Just the advisory (suspected-tier) findings."""
    return [f for f in findings if f.tier is Tier.SUSPECTED]


def test_top2_oversubscription_flags_a_seatrade_far_more_want_than_it_seats():
    """S4: 20 campers all rank Sailing first; Sailing seats only 2·5 across the half.

    20 top-1 fans against 10 seats clears the conservative oversubscription factor,
    while every other seatrade is roomy — so no proven shortfall or starvation fires
    and the pressure surfaces only as an advisory SUSPECTED hint, never a certainty.
    """
    seatrades = ["Sailing", "Kayaking", "Rowing", "Canoeing"]
    campers = _campers_all_preferring(seatrades, n=20)
    caps = pd.DataFrame({"seatrade": seatrades, "campers_min": 0, "campers_max": [5, 20, 20, 20]})

    suspected = _suspected(diagnose(campers, caps))

    assert suspected, "expected a suspected top-2 oversubscription hint"
    assert any("Sailing" in f.cause for f in suspected)


def test_top2_oversubscription_quiet_when_seats_meet_demand():
    """Same 20 campers, but Sailing now seats 2·20 — demand sits well under the factor."""
    seatrades = ["Sailing", "Kayaking", "Rowing", "Canoeing"]
    campers = _campers_all_preferring(seatrades, n=20)
    caps = pd.DataFrame({"seatrade": seatrades, "campers_min": 0, "campers_max": 20})

    assert diagnose(campers, caps) == []


def _one_cabin(cabin: str, prefs: list[str], n: int) -> pd.DataFrame:
    """n campers of one cabin who all rank the same four seatrades in the same order."""
    return _roster([{"cabin": cabin, "camper": f"{cabin} {i}", "prefs": prefs} for i in range(n)])


def test_cabin_clustering_flags_a_cabin_funnelling_into_one_small_seatrade():
    """S1: 10 campers of one cabin all rank Sailing first, which seats only 4.

    2·4 = 8 seats can't hold the cohesive cabin across both its blocks, so keeping them
    together fights the capacity — a per-cabin cohesion pressure. Sailing's 10 first-choice
    fans stay under the global top-2 factor (1.5·8 = 12), so *only* the cabin hint fires.
    Their other three picks are roomy, so no proven shortfall — it stays advisory.
    """
    campers = _one_cabin("Spindrift", ["Sailing", "Kayaking", "Rowing", "Canoeing"], n=10)
    caps = pd.DataFrame(
        {"seatrade": ["Sailing", "Kayaking", "Rowing", "Canoeing"], "campers_min": 0, "campers_max": [4, 20, 20, 20]}
    )

    suspected = _suspected(diagnose(campers, caps))

    assert suspected, "expected a suspected cabin-clustering hint"
    assert any("Spindrift" in f.cause and "Sailing" in f.cause for f in suspected)


def test_cabin_clustering_quiet_when_the_shared_seatrade_can_hold_the_cabin():
    """Same cabin, but Sailing now seats 6 → 2·6 = 12 ≥ 10, so they fit together."""
    campers = _one_cabin("Spindrift", ["Sailing", "Kayaking", "Rowing", "Canoeing"], n=10)
    caps = pd.DataFrame(
        {"seatrade": ["Sailing", "Kayaking", "Rowing", "Canoeing"], "campers_min": 0, "campers_max": [6, 20, 20, 20]}
    )

    assert diagnose(campers, caps) == []


def test_cabin_clustering_quiet_when_the_top_pick_is_absent_from_the_setup():
    """A cabin funnelling into a seatrade not in the catalog sizes against nothing → silent.

    Prefs are validated against the catalog in production, so this can't arise there; the
    seats==0 guard just keeps the hint from firing a nonsense "seats only 0" if that ever
    loosens (err toward silence). The three real picks are roomy, so no proven check fires.
    """
    campers = _one_cabin("Spindrift", ["Ghost", "Kayaking", "Rowing", "Canoeing"], n=10)
    caps = pd.DataFrame({"seatrade": ["Kayaking", "Rowing", "Canoeing"], "campers_min": 0, "campers_max": 20})

    assert diagnose(campers, caps) == []
