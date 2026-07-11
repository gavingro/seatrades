"""Pure infeasibility diagnosis — why a solve produced no schedule.

Post-mortem only: functions over the joined domain data (campers, seatrade
setup) plus the config knobs they need — never Streamlit, the solver, or session
state. The service layer runs this only on an ``INFEASIBLE`` result and prepends
the findings above the retained generic failure copy.

A finding is a proven or suspected *cause* in the Captain's language plus a named
fix. Each proven cause is a necessary feasibility condition confirmed against the
real model; if the check fires, no schedule exists. This module ships the proven
tier — capacity shortfall, the two starvation checks, the besties/friends/frenemies
relationship checks; the suspected tier and the matching-deficiency backstop are a
later slice of the parent PRD.
"""

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from itertools import combinations
from typing import Optional

import pandas as pd

from seatrades.config import BESTIES_MIN_SHARED_SEATRADES, PREF_COLS

# A camper keyed by their (cabin, name) composite key.
CamperKey = tuple[str, str]

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
) -> list[Finding]:
    """Rank the causes of an infeasible solve, most-certain first.

    Runs the cheap named checks over the inputs + config knobs and returns their
    findings (proven before suspected). An empty list means no cause fired — the
    UI shows the honest "couldn't identify" fallback.
    """
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
    caps = seatrade_setup.set_index("seatrade")["campers_max"]
    findings: list[Finding] = []
    for group in _components(_pairs(relationships, "besties")):
        size = len(group)
        common = set.intersection(*(set(prefs[member]) for member in group))
        if len(common) < BESTIES_MIN_SHARED_SEATRADES:
            continue  # no common pair at all — reported by B1
        roomy = [s for s in common if caps.get(s, 0) >= size]
        if len(roomy) >= BESTIES_MIN_SHARED_SEATRADES:
            continue
        labels = _join_names([_key_label(member) for member in sorted(group)])
        cramped = sorted(s for s in common if caps.get(s, 0) < size)
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
        caps = {s: _cabin_cap(max_cabin_share_per_seatrade, session_caps.get(s, 0)) for s in roomy_session}
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


def _cabin_cap(share: float, campers_max: int) -> int:
    """One cabin's per-seatrade seat cap under the opt-in share limit — mirrors the solver.

    Floored at 1 so a tiny-capacity seatrade never rounds to an unfillable 0 (matches
    ``_add_cabin_share_cap_constraints`` in problem.py).
    """
    return max(1, round(share * campers_max))


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
