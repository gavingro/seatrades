"""Pure infeasibility diagnosis — why a solve produced no schedule.

Post-mortem only: functions over the joined domain data (campers, seatrade
setup) plus the config knobs they need — never Streamlit, the solver, or session
state. The service layer runs this only on an ``INFEASIBLE`` result and prepends
the findings above the retained generic failure copy.

A finding is a proven or suspected *cause* in the Captain's language plus a named
fix. Each proven cause is a necessary feasibility condition confirmed against the
real model; if the check fires, no schedule exists. This module ships the proven
tier — capacity shortfall, the two starvation checks, the besties/friends/frenemies
relationship checks — plus a general matching-deficiency backstop that runs only when
those come up empty. It also ships the suspected tier: advisory *pressure* hints (top-2
oversubscription, cabin clustering, cross-cabin frenemies overlap, gender-balance vs. the
same-fleet lock, balance vs. minimum) appended below the proven findings, behind the
conservative placeholder thresholds in ``config`` (research spike #115 tunes the numbers).
The bounded relaxation re-solve (the other as-needed fallback) needs the solver, so it
lives at the service-layer call site, not here.
"""

from collections import defaultdict, deque
from dataclasses import dataclass
from enum import Enum
from itertools import combinations
from typing import Optional

import pandas as pd

from seatrades.config import (
    BESTIES_MIN_SHARED_SEATRADES,
    PREF_COLS,
    SUSPECTED_BALANCE_MIN_POPULARITY_FACTOR,
    SUSPECTED_CABIN_CLUSTERING_MIN_CAMPERS,
    SUSPECTED_CABIN_CLUSTERING_SHARE,
    SUSPECTED_FRENEMIES_CLUSTERING_RATIO,
    SUSPECTED_GENDER_DOMINANCE_SHARE,
    SUSPECTED_TOP2_OVERSUBSCRIPTION_FACTOR,
    cabin_seat_cap,
)

# A camper keyed by their (cabin, name) composite key.
CamperKey = tuple[str, str]

# A node in the matching-backstop flow network: the source/sink and seatrades are
# plain strings, campers are their (cabin, name) key. Campers (tuples) never collide
# with seatrades (strings); the source/sink sentinels assume no seatrade is literally
# named ``__source__``/``__sink__``.
FlowNode = tuple[str, str] | str

# Within a half-week every seatrade runs in both fleet blocks, so each seatrade's
# per-session ``campers_max`` seats are offered twice per half.
_FLEET_BLOCKS_PER_HALF = 2


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
    relationships: Optional[pd.DataFrame] = None,
    max_seatrades_per_fleet: Optional[int] = None,
    max_cabin_share_per_seatrade: float = 1.0,
    force_same_fleet_all_week: bool = False,
) -> list[Finding]:
    """Rank the causes of an infeasible solve, most-certain first.

    Runs the cheap named checks over the inputs + config knobs, then appends the
    advisory suspected-tier pressure hints *below* them (proven before suspected, so
    the certain causes always lead). An empty list means nothing fired — the UI shows
    the honest "couldn't identify" fallback.
    """
    proven = _proven_findings(
        joined_campers, seatrade_setup, relationships, max_seatrades_per_fleet, max_cabin_share_per_seatrade
    )
    suspected = _suspected_findings(joined_campers, seatrade_setup, relationships, force_same_fleet_all_week)
    return proven + suspected


def _proven_findings(
    joined_campers: pd.DataFrame,
    seatrade_setup: pd.DataFrame,
    relationships: Optional[pd.DataFrame],
    max_seatrades_per_fleet: Optional[int],
    max_cabin_share_per_seatrade: float,
) -> list[Finding]:
    """The certain causes: named necessary-condition checks, else the matching backstop."""
    findings: list[Finding] = []
    capacity_finding = _capacity_shortfall(joined_campers, seatrade_setup, max_seatrades_per_fleet)
    if capacity_finding is not None:
        findings.append(capacity_finding)
    findings.extend(_starved_campers(joined_campers, seatrade_setup))
    findings.extend(_top2_starved(joined_campers, seatrade_setup))
    findings.extend(_besties_no_common_ground(joined_campers, relationships))
    findings.extend(
        _besties_too_big_for_cabin(joined_campers, seatrade_setup, relationships, max_cabin_share_per_seatrade)
    )
    findings.extend(_besties_too_big_for_seatrade(joined_campers, seatrade_setup, relationships))
    findings.extend(_besties_frenemies_contradiction(relationships))
    findings.extend(_friends_hub(joined_campers, relationships))
    findings.extend(_frenemies_clash(joined_campers, relationships))
    if findings:
        return findings
    # Only when every cheap named check comes up empty: a general matching-deficiency
    # backstop that catches shortfalls the individual checks miss and names its own culprits.
    return _matching_deficiency_backstop(joined_campers, seatrade_setup)


def _suspected_findings(
    joined_campers: pd.DataFrame,
    seatrade_setup: pd.DataFrame,
    relationships: Optional[pd.DataFrame],
    force_same_fleet_all_week: bool,
) -> list[Finding]:
    """Advisory pressure hints, in a fixed advisory order.

    Each signal is a *pressure* — tight but not provably impossible, needing global
    reasoning to confirm — so it stays advisory, never a certainty. The real ranking is
    proven-before-suspected (the certain causes lead); a within-tier ordering by
    likelihood needs comparable, calibrated cutoffs, so it lands with research spike #115.
    Cutoffs are the conservative placeholders in ``config`` (#115 replaces the numbers).
    """
    findings: list[Finding] = []
    findings.extend(_top2_oversubscription(joined_campers, seatrade_setup))
    findings.extend(_cabin_clustering(joined_campers, seatrade_setup))
    findings.extend(_cross_cabin_frenemies_overlap(joined_campers, relationships))
    findings.extend(_gender_balance_vs_same_fleet(joined_campers, force_same_fleet_all_week))
    findings.extend(_balance_vs_minimum(joined_campers, seatrade_setup))
    return findings


def _top2_oversubscription(joined_campers: pd.DataFrame, seatrade_setup: pd.DataFrame) -> list[Finding]:
    """S4: seatrades far more campers rank in their top two than the seatrade can seat.

    Everyone is promised a top-2 pick, but a seatrade offers only ``2·campers_max``
    seats across the half. When the campers ranking it first or second outnumber that
    by the placeholder factor, the promise is under real pressure — advisory, since
    whether it actually breaks depends on how the rest of the schedule shakes out.
    """
    top1, top2 = PREF_COLS[0], PREF_COLS[1]
    top_demand = pd.concat([joined_campers[top1], joined_campers[top2]]).value_counts()
    seats_by_seatrade = _seats_by_seatrade(seatrade_setup)
    findings: list[Finding] = []
    for seatrade, demand in top_demand.items():
        seats = int(seats_by_seatrade.get(seatrade, 0))
        if seats == 0 or demand < SUSPECTED_TOP2_OVERSUBSCRIPTION_FACTOR * seats:
            continue
        findings.append(
            Finding(
                tier=Tier.SUSPECTED,
                cause=(
                    f"{seatrade} is a top-two pick for {int(demand)} campers but seats only {seats} "
                    "across the week — far more campers want it early than can get it, so the top-2 "
                    "promise is under pressure here."
                ),
                fix=f"Raise *max campers* on {seatrade}, or add a similar seatrade to draw off demand.",
            )
        )
    return findings


def _cabin_clustering(joined_campers: pd.DataFrame, seatrade_setup: pd.DataFrame) -> list[Finding]:
    """S1: a cabin most of whose campers funnel their first choice into one small seatrade.

    A cabin attends together in the one block it occupies each half, so keeping a cohesive
    cabin together in a seatrade needs that seatrade to hold them across its two blocks
    (``2·campers_max`` seats). When at least the placeholder share of a cabin ranks the same
    seatrade *first* yet those seats can't hold the cabin, cohesion fights capacity — a
    pressure, not a proof: they can still be split off their first pick, so it's advisory.
    """
    seats_by_seatrade = _seats_by_seatrade(seatrade_setup)
    top1 = PREF_COLS[0]
    findings: list[Finding] = []
    for cabin, group in joined_campers.groupby("cabin"):
        cabin_size = len(group)
        top_counts = group[top1].value_counts()
        top_seatrade, top_count = top_counts.idxmax(), int(top_counts.max())
        if top_count < SUSPECTED_CABIN_CLUSTERING_MIN_CAMPERS:
            continue  # too small a group to be worth flagging — err toward silence
        seats = int(seats_by_seatrade.get(top_seatrade, 0))
        if seats == 0:
            continue  # top pick isn't in the setup catalog — nothing to size against
        if top_count < SUSPECTED_CABIN_CLUSTERING_SHARE * cabin_size or top_count <= seats:
            continue
        findings.append(
            Finding(
                tier=Tier.SUSPECTED,
                cause=(
                    f"Cabin {cabin} clusters on {top_seatrade}: {int(top_count)} of its {cabin_size} "
                    f"campers rank it first, but it seats only {seats} across the week — the cabin can't "
                    "stay together there, so keeping them together strains against the capacity."
                ),
                fix=(
                    f"Raise *max campers* on {top_seatrade}, add a similar seatrade to spread the cabin, "
                    "or accept some of the cabin will be split off their first choice."
                ),
            )
        )
    return findings


def _cross_cabin_frenemies_overlap(
    joined_campers: pd.DataFrame, relationships: Optional[pd.DataFrame]
) -> list[Finding]:
    """S2: a frenemies group spanning cabins that rank too few seatrades to spread over.

    The proven clash only fires on a *same-cabin* clique (guaranteed to share a block);
    a group spread across cabins may land in different blocks and satisfy itself, so it
    can't be proven — but when the group has as many members as the distinct seatrades
    they collectively rank, keeping every pair apart is under real pressure. Advisory.
    Since each camper ranks four distinct seatrades, the union is always ≥ 4, so this
    only fires on genuinely large, tightly-clustered groups — conservative by construction.
    """
    prefs = _prefs_by_camper(joined_campers)
    findings: list[Finding] = []
    for group in _components(_pairs(relationships, "frenemies")):
        cabins = {cabin for cabin, _ in group}
        if len(cabins) < 2:
            continue  # single-cabin groups are the proven clash's territory
        union = set().union(*(set(prefs[member]) for member in group))
        if len(group) < SUSPECTED_FRENEMIES_CLUSTERING_RATIO * len(union):
            continue
        labels = _join_names([_key_label(member) for member in sorted(group)])
        findings.append(
            Finding(
                tier=Tier.SUSPECTED,
                cause=(
                    f"{labels} are {len(group)} frenemies across {len(cabins)} cabins who between them "
                    f"rank only {len(union)} seatrades — keeping every pair out of a shared session leaves "
                    "little room, so this may be part of why no schedule fits."
                ),
                fix="Drop a frenemies link, or add seatrades for them to rank so they can spread apart.",
            )
        )
    return findings


def _gender_balance_vs_same_fleet(joined_campers: pd.DataFrame, force_same_fleet_all_week: bool) -> list[Finding]:
    """S3: one gender dominating the cabins while the same-fleet-all-week lock is on.

    Gender balance spreads each gender's cabins evenly across the blocks; the opt-in lock
    pins every cabin to one fleet for the whole week, cutting the freedom to balance. When
    one gender holds most cabins, that even split is strained. Only meaningful with the lock
    engaged, and only a pressure — the split may still resolve — so it stays advisory.
    """
    if not force_same_fleet_all_week or "gender" not in joined_campers.columns:
        return []
    cabin_genders = joined_campers.groupby("cabin")["gender"].agg(lambda genders: genders.mode()[0])
    n_cabins = len(cabin_genders)
    gender_counts = cabin_genders.value_counts()
    dominant_gender, dominant = str(gender_counts.idxmax()), int(gender_counts.max())
    if dominant < SUSPECTED_GENDER_DOMINANCE_SHARE * n_cabins:
        return []
    return [
        Finding(
            tier=Tier.SUSPECTED,
            cause=(
                f"{dominant} of your {n_cabins} cabins are {dominant_gender}, and *keep each cabin in the "
                "same fleet all week* is switched on — that lock leaves little room to balance one "
                "dominant gender evenly across the blocks, which may be adding to the pressure."
            ),
            fix=(
                "Switch off *Keep each cabin in the same fleet all week* under Advanced settings, or "
                "even out the gender mix across cabins."
            ),
        )
    ]


def _balance_vs_minimum(joined_campers: pd.DataFrame, seatrade_setup: pd.DataFrame) -> list[Finding]:
    """S5: a live seatrade whose following barely clears its floor, which balance may split.

    Gender balance spreads a cabin's campers across the two blocks, so a seatrade's demand
    lands split roughly in half. A seatrade whose whole following only just clears its
    ``campers_min`` (under the placeholder factor of it) can fall below the floor in a block
    once split, so it may fail to run there. Restricted to *live* seatrades (a following that
    can't even clear the floor overall is the proven starvation case), so this stays a
    distinct advisory pressure, not a certainty.
    """
    popularity = _popularity(joined_campers)
    mins = seatrade_setup.set_index("seatrade")["campers_min"]
    findings: list[Finding] = []
    for seatrade, campers_min in mins.items():
        floor = int(campers_min)
        fans = int(popularity.get(seatrade, 0))
        if floor <= 0 or fans < floor:
            continue  # no floor, or dead already (the proven starvation case)
        if fans >= SUSPECTED_BALANCE_MIN_POPULARITY_FACTOR * floor:
            continue
        findings.append(
            Finding(
                tier=Tier.SUSPECTED,
                cause=(
                    f"Only {fans} campers rank {seatrade}, which needs {floor} to run — balancing cabins "
                    "across the blocks splits that demand, so it can drop below its minimum in a block and "
                    "not run there, which may be contributing to the failure."
                ),
                fix=f"Lower *min campers* on {seatrade}, or draw more campers to it, so it can run once split.",
            )
        )
    return findings


def _matching_deficiency_backstop(joined_campers: pd.DataFrame, seatrade_setup: pd.DataFrame) -> list[Finding]:
    """The catch-all: a set of campers that needs more distinct seats than exist.

    Ignoring all besties/frenemies/balance coupling, each camper still needs two
    distinct *live* preferred seatrades, and a seatrade offers ``2 · campers_max``
    seats across the half (it runs in both fleet blocks). If no assignment can seat
    every camper twice, no schedule exists — a necessary condition (Hall's), so it
    never false-positives. Names the deficient campers (the source side of the min cut).
    """
    dead = _dead_seatrades(joined_campers, seatrade_setup)
    seats_by_seatrade = _seats_by_seatrade(seatrade_setup)
    prefs = _prefs_by_camper(joined_campers)
    live_prefs = {camper: [s for s in picks if s not in dead] for camper, picks in prefs.items()}
    seats = {s: int(seats_by_seatrade.get(s, 0)) for s in {s for ps in live_prefs.values() for s in ps}}

    deficient = _unmatchable_campers(live_prefs, seats)
    if not deficient:
        return []
    labels = _join_names([_key_label(camper) for camper in sorted(deficient)])
    return [
        Finding(
            tier=Tier.PROVEN,
            cause=(
                f"These {len(deficient)} campers can't all be placed: {labels} need two seatrades "
                "each, but the seatrades they picked don't offer enough seats between them to seat "
                "them all twice — no schedule can fit them."
            ),
            fix=(
                "Raise *max campers* on the seatrades this group picked, add seatrades they'd want, "
                "or lower those seatrades' *min campers* so more of their picks can run."
            ),
        )
    ]


def _unmatchable_campers(live_prefs: dict[CamperKey, list[str]], seats: dict[str, int]) -> set[CamperKey]:
    """Campers that can't all get two distinct seats, via max-flow / Hall's condition.

    Flow network: source → each camper (cap 2) → each live preferred seatrade (cap 1)
    → sink (cap ``seats[s]``). A matching seats everyone iff the max flow saturates
    ``2 · n_campers``. When it can't, the deficient set is the campers still reachable
    from the source in the residual graph (the source side of the min cut). Empty set
    means everyone fits — no finding.
    """
    source, sink = "__source__", "__sink__"
    capacity: dict[FlowNode, dict[FlowNode, int]] = defaultdict(lambda: defaultdict(int))
    for camper, picks in live_prefs.items():
        capacity[source][camper] += 2
        for s in picks:
            capacity[camper][s] = 1
    for s, cap in seats.items():
        capacity[s][sink] = cap

    _max_flow(capacity, source, sink)
    if sum(capacity[source][camper] for camper in live_prefs) == 0:
        return set()  # residual source→camper edges all used up ⇒ everyone matched
    reachable = _residual_reachable(capacity, source)
    return {camper for camper in live_prefs if camper in reachable}


def _max_flow(capacity: dict[FlowNode, dict[FlowNode, int]], source: FlowNode, sink: FlowNode) -> None:
    """Edmonds-Karp max flow, mutating ``capacity`` in place to leave residuals.

    Repeatedly finds a shortest augmenting path (BFS) and pushes flow along it,
    decrementing forward residuals and incrementing reverse ones. On return,
    ``capacity`` holds the residual graph the deficient-set extraction reads.
    """
    while True:
        parent = {source: source}
        queue = deque([source])
        while queue and sink not in parent:
            node = queue.popleft()
            for nxt, cap in capacity[node].items():
                if cap > 0 and nxt not in parent:
                    parent[nxt] = node
                    queue.append(nxt)
        if sink not in parent:
            return
        path = _path_nodes(parent, sink)
        bottleneck = min(capacity[parent[n]][n] for n in path)
        for n in path:
            capacity[parent[n]][n] -= bottleneck
            capacity[n][parent[n]] += bottleneck


def _path_nodes(parent: dict[FlowNode, FlowNode], sink: FlowNode) -> list[FlowNode]:
    """The nodes of the augmenting path from just-after-source to sink."""
    nodes: list[FlowNode] = []
    node = sink
    while parent[node] != node:
        nodes.append(node)
        node = parent[node]
    return nodes


def _residual_reachable(capacity: dict[FlowNode, dict[FlowNode, int]], source: FlowNode) -> set[FlowNode]:
    """Nodes reachable from the source along edges with residual capacity left."""
    seen, queue = {source}, deque([source])
    while queue:
        node = queue.popleft()
        for nxt, cap in capacity[node].items():
            if cap > 0 and nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


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
    seats = _FLEET_BLOCKS_PER_HALF * sum(caps)
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


def _starved_campers(joined_campers: pd.DataFrame, seatrade_setup: pd.DataFrame) -> list[Finding]:
    """M1: campers whose picks can't supply two runnable sessions.

    A seatrade is *dead* when fewer campers rank it than its ``campers_min`` — even
    if all of them attend it can't reach the floor, so it never runs. A camper needs
    two distinct running seatrades (one per block); fewer than two *live* picks makes
    that impossible (a necessary condition). Names the camper and the dead picks.
    """
    dead = _dead_seatrades(joined_campers, seatrade_setup)
    findings: list[Finding] = []
    for row in joined_campers.itertuples(index=False):
        prefs = [getattr(row, col) for col in PREF_COLS]
        live = [s for s in prefs if s not in dead]
        if len(live) >= 2:
            continue
        dead_picks = [s for s in prefs if s in dead]
        label = _camper_label(row)
        findings.append(
            Finding(
                tier=Tier.PROVEN,
                cause=(
                    f"{label} has too few seatrades that can actually run: their picks "
                    f"{_join_names(dead_picks)} are so niche that fewer campers want them than "
                    "their minimum, so they can never open — leaving no two runnable seatrades to "
                    "fill both blocks."
                ),
                fix=(
                    "Lower *min campers* on those seatrades so they can run, or accept they won't "
                    "and steer the camper toward busier seatrades."
                ),
            )
        )
    return findings


def _top2_starved(joined_campers: pd.DataFrame, seatrade_setup: pd.DataFrame) -> list[Finding]:
    """M2: campers whose two top picks are both dead, yet who *are* placeable.

    The top-2 guarantee hands each camper one of their first two choices. If both
    are dead (can never run) the guarantee cannot hold. Restricted to campers with
    two or more live picks — a fully-starved camper is the stronger M1 statement, so
    reporting M2 too would be noise.
    """
    dead = _dead_seatrades(joined_campers, seatrade_setup)
    top1, top2 = PREF_COLS[0], PREF_COLS[1]
    findings: list[Finding] = []
    for row in joined_campers.itertuples(index=False):
        prefs = [getattr(row, col) for col in PREF_COLS]
        live = [s for s in prefs if s not in dead]
        top_picks = [getattr(row, top1), getattr(row, top2)]
        if len(live) < 2 or not all(s in dead for s in top_picks):
            continue
        label = _camper_label(row)
        findings.append(
            Finding(
                tier=Tier.PROVEN,
                cause=(
                    f"{label}'s top two picks {_join_names(top_picks)} both can never run (fewer "
                    "campers want them than their minimum), so the top-2 guarantee cannot give "
                    "them a first- or second-choice seatrade."
                ),
                fix=f"Lower *min campers* on {_join_names(top_picks)} so at least one can run.",
            )
        )
    return findings


def _besties_no_common_ground(joined_campers: pd.DataFrame, relationships: Optional[pd.DataFrame]) -> list[Finding]:
    """B1: a besties group whose members share fewer than two seatrades in common.

    Besties keep an *identical* two-session schedule, so the whole connected group
    must share at least two seatrades they all rank. Validation only checks this
    pairwise, so a transitive chain (every pair fine, no common pair for all) slips
    through and fails at solve — named here. A necessary condition → PROVEN.
    """
    prefs = _prefs_by_camper(joined_campers)
    findings: list[Finding] = []
    for group in _components(_pairs(relationships, "besties")):
        common = set.intersection(*(set(prefs[member]) for member in group))
        if len(common) >= BESTIES_MIN_SHARED_SEATRADES:
            continue
        labels = _join_names([_key_label(member) for member in sorted(group)])
        shared = _join_names(sorted(common)) if common else "no seatrade"
        findings.append(
            Finding(
                tier=Tier.PROVEN,
                cause=(
                    f"The besties group {labels} can't all keep the same schedule: they rank only "
                    f"{shared} in common, but besties need two shared seatrades to match across both "
                    "blocks — their tastes diverge too much."
                ),
                fix="Drop a besties link in the chain, or align their preferences onto two shared seatrades.",
            )
        )
    return findings


def _besties_too_big_for_seatrade(
    joined_campers: pd.DataFrame, seatrade_setup: pd.DataFrame, relationships: Optional[pd.DataFrame]
) -> list[Finding]:
    """B3: a besties group larger than the capacity of the seatrades it shares.

    The group attends two seatrades *as one*, so it needs two shared seatrades whose
    ``campers_max`` is at least the group size. Fewer than two roomy shared seatrades
    means they can't be seated together (a necessary condition). Groups that share
    fewer than two seatrades are B1's territory, so they're skipped here.
    """
    prefs = _prefs_by_camper(joined_campers)
    session_caps = seatrade_setup.set_index("seatrade")["campers_max"]
    findings: list[Finding] = []
    for group in _components(_pairs(relationships, "besties")):
        size = len(group)
        common = set.intersection(*(set(prefs[member]) for member in group))
        if len(common) < BESTIES_MIN_SHARED_SEATRADES:
            continue  # no common pair at all — reported by B1
        roomy = [s for s in common if session_caps.get(s, 0) >= size]
        if len(roomy) >= BESTIES_MIN_SHARED_SEATRADES:
            continue
        labels = _join_names([_key_label(member) for member in sorted(group)])
        cramped = sorted(s for s in common if session_caps.get(s, 0) < size)
        findings.append(
            Finding(
                tier=Tier.PROVEN,
                cause=(
                    f"The besties group {labels} ({size} campers) must attend the same seatrade "
                    f"together, but the seatrades they share ({_join_names(cramped)}) seat fewer than "
                    f"{size} — leaving too few big-enough seatrades to hold them across both blocks."
                ),
                fix="Raise *max campers* on those seatrades, or split the group / drop a besties link.",
            )
        )
    return findings


def _besties_too_big_for_cabin(
    joined_campers: pd.DataFrame,
    seatrade_setup: pd.DataFrame,
    relationships: Optional[pd.DataFrame],
    max_cabin_share_per_seatrade: float,
) -> list[Finding]:
    """B2: a same-cabin besties group larger than the opt-in per-cabin share cap.

    Only meaningful when the ``max_cabin_share_per_seatrade`` hard cap is switched on
    (below 1.0); by default no per-cabin limit exists, so this can't cause
    infeasibility. When on, a single cabin may place only ``round(share·campers_max)``
    campers in a seatrade — so a same-cabin besties group exceeding that (yet fitting
    the session itself, else it's B3) can't be seated together across both blocks.
    """
    if max_cabin_share_per_seatrade >= 1.0:
        return []
    prefs = _prefs_by_camper(joined_campers)
    session_caps = seatrade_setup.set_index("seatrade")["campers_max"]
    findings: list[Finding] = []
    for group in _components(_pairs(relationships, "besties")):
        cabins = {cabin for cabin, _ in group}
        if len(cabins) != 1:
            continue  # a per-cabin cap only binds a group concentrated in one cabin
        size = len(group)
        common = set.intersection(*(set(prefs[member]) for member in group))
        roomy_session = [s for s in common if session_caps.get(s, 0) >= size]
        if len(roomy_session) < BESTIES_MIN_SHARED_SEATRADES:
            continue  # the session itself is too small — that's B3, not the cabin cap
        caps = {s: cabin_seat_cap(max_cabin_share_per_seatrade, session_caps.get(s, 0)) for s in roomy_session}
        if sum(cap >= size for cap in caps.values()) >= BESTIES_MIN_SHARED_SEATRADES:
            continue
        (cabin,) = cabins
        labels = _join_names([_key_label(member) for member in sorted(group)])
        cap_value = caps[roomy_session[0]]
        findings.append(
            Finding(
                tier=Tier.PROVEN,
                cause=(
                    f"The besties group {labels} is {size} campers from one cabin ({cabin}) who must "
                    f"share a session, but your cabin-share cap lets only {cap_value} from a cabin into "
                    "each seatrade — too few to seat them together."
                ),
                fix=(
                    "Split the group / drop a besties link, or raise *Max cabin share per seatrade* "
                    "under Advanced settings."
                ),
            )
        )
    return findings


def _besties_frenemies_contradiction(relationships: Optional[pd.DataFrame]) -> list[Finding]:
    """R1: a frenemies pair that lies inside a single besties group.

    Besties (directly or through a chain) must share an identical schedule; frenemies
    must share none. A frenemies pair inside one besties component demands both at once
    — impossible. PROVEN, naming the two contradictory campers.
    """
    components = _components(_pairs(relationships, "besties"))
    findings: list[Finding] = []
    for a, b in _pairs(relationships, "frenemies"):
        if any(a in group and b in group for group in components):
            findings.append(
                Finding(
                    tier=Tier.PROVEN,
                    cause=(
                        f"{_key_label(a)} and {_key_label(b)} are marked frenemies but are tied into the "
                        "same besties group — besties must share every session and frenemies none, which "
                        "cannot both hold."
                    ),
                    fix=(
                        "Remove the contradictory relationship — drop either the frenemies link or a "
                        "besties link between them."
                    ),
                )
            )
    return findings


def _friends_hub(joined_campers: pd.DataFrame, relationships: Optional[pd.DataFrame]) -> list[Finding]:
    """FH: a camper with more friends than their two seatrades can share with.

    A camper occupies exactly two seatrades. Each friend must share at least one
    session, so both must rank one of those two. If no two of the hub's ranked
    seatrades between them touch every friend's overlap, some friendship is unkeepable
    — a PROVEN 2-cover deficiency. (Refinement deferred: run on the besties-merged
    entity, since merged besties occupy their two seatrades jointly.)
    """
    prefs = _prefs_by_camper(joined_campers)
    adjacency: dict[CamperKey, set[CamperKey]] = defaultdict(set)
    for a, b in _pairs(relationships, "friends"):
        adjacency[a].add(b)
        adjacency[b].add(a)
    findings: list[Finding] = []
    for hub, friends in adjacency.items():
        hub_seatrades = set(prefs[hub])
        overlaps = [hub_seatrades & set(prefs[friend]) for friend in friends]
        if _two_seatrades_cover(hub_seatrades, overlaps):
            continue
        friend_labels = _join_names([_key_label(friend) for friend in sorted(friends)])
        findings.append(
            Finding(
                tier=Tier.PROVEN,
                cause=(
                    f"{_key_label(hub)} is friends with {friend_labels}, who want more different seatrades "
                    "than the two sessions the hub attends can cover — no two of the hub's seatrades can "
                    "sit with all of them."
                ),
                fix="Trim some of the hub's friend links so the remaining friends fit within two shared seatrades.",
            )
        )
    return findings


def _frenemies_clash(joined_campers: pd.DataFrame, relationships: Optional[pd.DataFrame]) -> list[Finding]:
    """FC: a same-cabin clique of mutual frenemies that outnumbers their seatrades.

    A cabin sits in one block per half, so same-cabin campers share a block. Frenemies
    can't share a session, so a clique of ``k`` mutual same-cabin frenemies needs ``k``
    distinct seatrades in that block; if their combined ranked seatrades number fewer
    than ``k``, pigeonhole makes it infeasible. Restricted to a *clique* (all pairs
    frenemies) so it stays a necessary condition; looser groups fall to the suspected tier.
    """
    prefs = _prefs_by_camper(joined_campers)
    same_cabin_edges = [(a, b) for a, b in _pairs(relationships, "frenemies") if a[0] == b[0]]
    edges = {frozenset(edge) for edge in same_cabin_edges}
    findings: list[Finding] = []
    for group in _components(same_cabin_edges):
        size = len(group)
        if sum(frozenset(pair) in edges for pair in combinations(group, 2)) != size * (size - 1) // 2:
            continue  # not a clique — a distinct-session shortfall isn't guaranteed
        union = set().union(*(set(prefs[member]) for member in group))
        if len(union) >= size:
            continue
        cabin = next(iter(group))[0]
        labels = _join_names([_key_label(member) for member in sorted(group)])
        findings.append(
            Finding(
                tier=Tier.PROVEN,
                cause=(
                    f"{labels} are {size} campers in one cabin ({cabin}) who all refuse to share a "
                    f"seatrade, but between them they rank only {len(union)} ({_join_names(sorted(union))}) "
                    "— too few distinct seatrades to keep them all apart in the block they share."
                ),
                fix="Drop a frenemies link, or add more seatrades for them to rank so they can spread out.",
            )
        )
    return findings


def _two_seatrades_cover(hub_seatrades: set[str], overlaps: list[set[str]]) -> bool:
    """Whether some two of the hub's seatrades together touch every friend's overlap set."""
    for pair in combinations(hub_seatrades, 2):
        chosen = set(pair)
        if all(chosen & overlap for overlap in overlaps):
            return True
    return not overlaps  # a hub with no friends is trivially covered


def _pairs(relationships: Optional[pd.DataFrame], relationship: str) -> list[tuple[CamperKey, CamperKey]]:
    """The (cabin, name) camper pairs of a given relationship type."""
    if relationships is None or relationships.empty:
        return []
    rows = relationships[relationships["relationship"] == relationship]
    return [
        ((str(row.cabin_1), str(row.camper_1)), (str(row.cabin_2), str(row.camper_2)))
        for row in rows.itertuples(index=False)
    ]


def _components(pairs: list[tuple[CamperKey, CamperKey]]) -> list[set[CamperKey]]:
    """Connected components of an undirected graph given as edges."""
    adjacency: dict[CamperKey, set[CamperKey]] = defaultdict(set)
    for a, b in pairs:
        adjacency[a].add(b)
        adjacency[b].add(a)
    seen: set[CamperKey] = set()
    components: list[set[CamperKey]] = []
    for start in adjacency:
        if start in seen:
            continue
        stack, component = [start], set()
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            component.add(node)
            stack.extend(adjacency[node] - seen)
        components.append(component)
    return components


def _prefs_by_camper(joined_campers: pd.DataFrame) -> dict[CamperKey, list[str]]:
    """Each camper's ranked seatrades, keyed by (cabin, name)."""
    return {
        (str(row.cabin), str(row.camper)): [getattr(row, col) for col in PREF_COLS]
        for row in joined_campers.itertuples(index=False)
    }


def _dead_seatrades(joined_campers: pd.DataFrame, seatrade_setup: pd.DataFrame) -> set[str]:
    """Seatrades that can never run: fewer campers rank them than their ``campers_min``."""
    popularity = _popularity(joined_campers)
    mins = seatrade_setup.set_index("seatrade")["campers_min"]
    return {str(s) for s, floor in mins.items() if popularity.get(s, 0) < floor}


def _popularity(joined_campers: pd.DataFrame) -> pd.Series:
    """How many campers rank each seatrade."""
    picks = joined_campers[PREF_COLS].to_numpy().ravel()
    return pd.Series(picks).value_counts()


def _seats_by_seatrade(seatrade_setup: pd.DataFrame) -> pd.Series:
    """Each seatrade's total half-week seats, keyed by seatrade.

    A seatrade runs in both fleet blocks each half, so it offers its per-session
    ``campers_max`` twice. The one place this ``2 · campers_max`` decision lives —
    read via ``.get(seatrade, 0)`` (0 for a seatrade absent from the setup catalog).
    """
    return _FLEET_BLOCKS_PER_HALF * seatrade_setup.set_index("seatrade")["campers_max"].astype(int)


def _camper_label(row) -> str:
    """A camper named by their ``(cabin, name)`` composite key."""
    return _key_label((row.cabin, row.camper))


def _key_label(key: CamperKey) -> str:
    """A ``(cabin, name)`` composite key as user-facing prose."""
    cabin, name = key
    return f"({cabin}, {name})"


def _join_names(names: list[str]) -> str:
    """Comma-join names for readable prose (single name unchanged)."""
    return ", ".join(names)


def _preferred_seatrades(joined_campers: pd.DataFrame) -> set[str]:
    """The union of every seatrade any camper ranked."""
    return set(pd.unique(joined_campers[PREF_COLS].to_numpy().ravel()))
