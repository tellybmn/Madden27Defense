"""Playbook synthesizer: isomorphism clustering + constrained knapsack / set-cover selection.

Pipeline
  1. Cluster formations across playbooks by pre-snap alignment isomorphism
     (canonical formation key: aliases like 'Double'/'Dbl.' collapse).
  2. Score each cluster: sum of style-weighted play values + disguise entropy bonus.
  3. Exact search (small candidate pool) for the best subset under:
       C1 <=6 formations, <=350 plays
       C2 sub-package sets need disguise entropy >= threshold
       C3 personnel coverage (heavy / base / spread)
       C4 each formation supports all four quick-audible play types
     Objective adds a set-cover bonus for distinct coverage families covered.
"""
from __future__ import annotations

import math
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations

from .parser import SUB_SETS, FormationInfo, PlayInfo, infer_formation, play_type, slugify

AUDIBLE_TYPES = ("man_pressure", "sim_pressure", "two_high", "split_match")
ALL_TYPES = ("man_pressure", "blitz", "sim_pressure", "two_high", "split_match",
             "cover3", "man_coverage", "run_plug")

BASE_REQUIRED = ("nickel-2-4-dbl-mug", "nickel-3-3-swap-mug")      # 11 personnel
SPREAD_OPTIONS = ("dollar-3-2", "dime-1-4-dbl-mug")                # 10 / 01 personnel
ENTROPY_MIN = 0.45
FAMILY_BONUS = 3.0
ENTROPY_WEIGHT = 12.0
BASE_AFFINITY = 1.25
POOL_CAP = 18

STYLES: dict[str, dict[str, float]] = {
    "flores-macdonald": dict(man_pressure=3.0, blitz=2.0, sim_pressure=3.0, two_high=2.0, split_match=2.0,
                             cover3=1.5, man_coverage=1.0, run_plug=1.0, other=0.2),
    "campanile": dict(man_pressure=1.5, blitz=1.2, sim_pressure=2.0, two_high=2.5, split_match=3.0,
                      cover3=2.0, man_coverage=1.0, run_plug=1.0, other=0.2),
    "hybrid": dict(man_pressure=2.5, blitz=1.8, sim_pressure=2.8, two_high=2.4, split_match=2.6,
                   cover3=1.7, man_coverage=1.0, run_plug=1.0, other=0.2),
}


class InfeasibleError(Exception):
    pass


@dataclass
class PlayRec:
    name: str
    info: PlayInfo
    sources: set[str] = field(default_factory=set)
    value: float = 0.0

    @property
    def ptype(self) -> str:
        return play_type(self.info)


@dataclass
class Cluster:
    key: str
    info: FormationInfo
    plays: dict[str, PlayRec] = field(default_factory=dict)
    sources: set[str] = field(default_factory=set)

    @property
    def types(self) -> set[str]:
        return {p.ptype for p in self.plays.values()}

    @property
    def has_all_audibles(self) -> bool:
        return set(AUDIBLE_TYPES) <= self.types

    @property
    def entropy(self) -> float:
        return disguise_entropy(self.info, self.plays.values())

    @property
    def families(self) -> set[str]:
        return {p.info.coverage_family for p in self.plays.values() if p.info.coverage_family != "Unknown"}


def disguise_entropy(info: FormationInfo, plays) -> float:
    """Normalised Shannon entropy of play-type outcomes from one look, scaled by how
    ambiguous the pre-snap alignment is (mugged A-gaps, 2-high-capable shells). 0..1."""
    cnt = Counter(t for t in (play_type(p.info) if hasattr(p, "info") else play_type(p) for p in plays)
                  if t in ALL_TYPES)
    total = sum(cnt.values())
    if total == 0:
        return 0.0
    h = -sum(c / total * math.log2(c / total) for c in cnt.values())
    return (h / math.log2(len(ALL_TYPES))) * info.alignment_factor


# ----------------------------------------------------------------- loading
def resolve_playbook_name(conn: sqlite3.Connection, base: str | None) -> str | None:
    if not base:
        return None
    b = slugify(base)
    for (name,) in conn.execute("SELECT name FROM playbooks"):
        s = slugify(name)
        if b == s or b == s.split("-")[-1]:
            return name
    raise InfeasibleError(f"base playbook {base!r} not found in database")


def load_clusters(conn: sqlite3.Connection) -> list[Cluster]:
    rows = conn.execute(
        "SELECT p.name AS pb, f.formation_name, pl.play_name, pl.coverage_family, pl.rush_count, "
        "pl.is_sim_pressure, pl.is_blitz, pl.is_run_plug FROM formations f "
        "JOIN playbooks p USING(playbook_id) LEFT JOIN plays pl USING(formation_id) "
        "ORDER BY p.name, f.formation_name, pl.play_name").fetchall()
    clusters: dict[str, Cluster] = {}
    for r in rows:
        info = infer_formation(r["formation_name"])
        c = clusters.setdefault(info.key, Cluster(info.key, info))
        c.sources.add(r["pb"])
        if r["play_name"] is None:
            continue
        pi = PlayInfo(r["play_name"], r["coverage_family"], r["rush_count"],
                      bool(r["is_sim_pressure"]), bool(r["is_blitz"]), bool(r["is_run_plug"]))
        rec = c.plays.setdefault(slugify(r["play_name"]), PlayRec(r["play_name"], pi))
        rec.sources.add(r["pb"])
    return sorted(clusters.values(), key=lambda c: c.key)


# ----------------------------------------------------------------- scoring
def value_plays(c: Cluster, weights: dict[str, float], base: str | None) -> None:
    for p in c.plays.values():
        v = weights.get(p.ptype, weights["other"])
        p.value = v * (BASE_AFFINITY if base and base in p.sources else 1.0)


def trim_plays(c: Cluster, cap: int) -> list[PlayRec]:
    """Top-`cap` plays by value, always keeping the best play of each audible type."""
    ranked = sorted(c.plays.values(), key=lambda p: (-p.value, p.name))
    keep = {}
    for t in AUDIBLE_TYPES:
        best = next((p for p in ranked if p.ptype == t), None)
        if best:
            keep[best.name] = best
    for p in ranked:
        if len(keep) >= cap:
            break
        keep.setdefault(p.name, p)
    return sorted(keep.values(), key=lambda p: (-p.value, p.name))


@dataclass
class Candidate:
    cluster: Cluster
    plays: list[PlayRec]
    value: float


@dataclass
class SelectedFormation:
    key: str
    name: str
    set_name: str
    front_type: str
    personnel: tuple[str, ...]
    entropy: float
    sources: list[str]
    plays: list[PlayRec]
    audibles: dict[str, PlayRec]


@dataclass
class PlaybookResult:
    base: str | None
    style: str
    objective: float
    formations: list[SelectedFormation]
    constraints: list[tuple[str, bool, str]]

    @property
    def total_plays(self) -> int:
        return sum(len(f.plays) for f in self.formations)

    def to_dict(self) -> dict:
        return {
            "base": self.base, "style": self.style, "objective": round(self.objective, 3),
            "total_formations": len(self.formations), "total_plays": self.total_plays,
            "constraints": [{"name": n, "ok": ok, "detail": d} for n, ok, d in self.constraints],
            "formations": [{
                "name": f.name, "key": f.key, "set": f.set_name, "front": f.front_type,
                "personnel": list(f.personnel), "disguise_entropy": round(f.entropy, 3),
                "source_playbooks": f.sources,
                "audibles": {t: p.name for t, p in f.audibles.items()},
                "plays": [{"name": p.name, "type": p.ptype, "coverage": p.info.coverage_family,
                           "rush": p.info.rush_count} for p in f.plays],
            } for f in self.formations],
        }


def _candidates(clusters, weights, base, cap) -> list[Candidate]:
    out = []
    for c in clusters:
        value_plays(c, weights, base)
        plays = trim_plays(c, cap)
        ent = disguise_entropy(c.info, plays)
        out.append(Candidate(c, plays, sum(p.value for p in plays) + ENTROPY_WEIGHT * ent))
    return out


def _score(combo: list[Candidate]) -> float:
    fam = set().union(*(c.cluster.families for c in combo))
    return sum(c.value for c in combo) + FAMILY_BONUS * len(fam)


def solve(clusters: list[Cluster], *, base: str | None = None, style: str = "flores-macdonald",
          max_formations: int = 6, max_plays: int = 350, entropy_min: float = ENTROPY_MIN) -> PlaybookResult:
    if style not in STYLES:
        raise InfeasibleError(f"unknown style {style!r}; choose from {', '.join(STYLES)}")
    weights = STYLES[style]
    cap = max(len(AUDIBLE_TYPES), max_plays // max_formations)

    cands = {c.cluster.key: c for c in _candidates(clusters, weights, base, cap)}
    # C4 (audible completeness) + C2 (disguise entropy for sub-package sets)
    elig = {k: c for k, c in cands.items()
            if c.cluster.has_all_audibles
            and (c.cluster.info.set_name not in SUB_SETS or disguise_entropy(c.cluster.info, c.plays) >= entropy_min)}

    missing = [k for k in BASE_REQUIRED if k not in elig]
    if missing:
        raise InfeasibleError(f"11-personnel requirement unmet; missing/ineligible: {', '.join(missing)}")
    heavy = [c for c in elig.values() if c.cluster.info.is_five_front]
    spread = [elig[k] for k in SPREAD_OPTIONS if k in elig]
    if not heavy:
        raise InfeasibleError("heavy-set requirement unmet: no eligible 5-front (3-4 Bear / 5-2 / 4-3 Even 6-1)")
    if not spread:
        raise InfeasibleError("spread-set requirement unmet: need Dollar 3-2 or Dime 1-4 Dbl Mug")

    best: tuple[float, int, list[str]] | None = None
    best_combo: list[Candidate] = []
    for h in heavy:
        for s in spread:
            forced = {k: elig[k] for k in BASE_REQUIRED}
            forced[h.cluster.key] = h
            forced[s.cluster.key] = s
            slots = max_formations - len(forced)
            plays_forced = sum(len(c.plays) for c in forced.values())
            if slots < 0 or plays_forced > max_plays:
                continue
            pool = sorted((c for k, c in elig.items() if k not in forced), key=lambda c: (-c.value, c.cluster.key))[:POOL_CAP]
            for r in range(slots + 1):
                for extra in combinations(pool, r):
                    combo = list(forced.values()) + list(extra)
                    n = sum(len(c.plays) for c in combo)
                    if n > max_plays:
                        continue
                    sc = _score(combo)
                    tie = sorted(c.cluster.key for c in combo)
                    if best is None or (sc, -n) > (best[0], -best[1]) or (sc == best[0] and n == best[1] and tie < best[2]):
                        best, best_combo = (sc, n, tie), combo
    if best is None:
        raise InfeasibleError(f"no selection fits within {max_formations} formations / {max_plays} plays")

    sel = [_to_selected(c) for c in sorted(best_combo, key=lambda c: (c.cluster.info.set_name, c.cluster.key))]
    res = PlaybookResult(base, style, best[0], sel, [])
    res.constraints = verify(res, max_formations, max_plays, entropy_min)
    return res


def _to_selected(c: Candidate) -> SelectedFormation:
    aud = {}
    for t in AUDIBLE_TYPES:
        aud[t] = next(p for p in c.plays if p.ptype == t)  # first = highest value
    i = c.cluster.info
    return SelectedFormation(c.cluster.key, i.formation_name, i.set_name, i.front_type, i.personnel_groups,
                             disguise_entropy(i, c.plays), sorted(c.cluster.sources), c.plays, aud)


def verify(res: PlaybookResult, max_formations=6, max_plays=350, entropy_min=ENTROPY_MIN) -> list[tuple[str, bool, str]]:
    keys = {f.key for f in res.formations}
    checks = [
        ("C1 formations <= cap", len(res.formations) <= max_formations, f"{len(res.formations)}/{max_formations}"),
        ("C1 plays <= cap", res.total_plays <= max_plays, f"{res.total_plays}/{max_plays}"),
    ]
    sub = [f for f in res.formations if f.set_name in SUB_SETS]
    low = [f.name for f in sub if f.entropy < entropy_min]
    checks.append(("C2 disguise entropy (nickel/dime/dollar)", not low,
                   "all >= %.2f" % entropy_min if not low else "below threshold: " + ", ".join(low)))
    five = [f.name for f in res.formations if infer_formation(f.name).is_five_front]
    checks.append(("C3 heavy (12/21/22) -> 5-front", bool(five), ", ".join(five) or "none"))
    checks.append(("C3 base (11) -> Nickel 2-4 Dbl Mug + Nickel 3-3 Swap Mug",
                   all(k in keys for k in BASE_REQUIRED), "present" if all(k in keys for k in BASE_REQUIRED) else "missing"))
    sp = [k for k in SPREAD_OPTIONS if k in keys]
    checks.append(("C3 spread (10/01) -> Dollar 3-2 or Dime 1-4 Dbl Mug", bool(sp), ", ".join(sp) or "none"))
    bad = [f.name for f in res.formations if not set(AUDIBLE_TYPES) <= {p.ptype for p in f.plays}]
    checks.append(("C4 audible completeness (4 play-types each)", not bad, "all formations complete" if not bad else ", ".join(bad)))
    return checks
