"""Playbook synthesizer: isomorphism clustering + constrained knapsack / set-cover selection.

Two constraint tiers (do not confuse them)
  GLOBAL engine limits - what the Madden custom-playbook editor allows in total:
     <=15 personnel, <=73 fronts, <=750 plays, <=75 plays per front. Usage is measured on the
     worst case "keep the whole base playbook and add the hybrid fronts/plays" (see FOUNDATIONS).
  TACTICAL active set - the in-game menu filter this optimizer selects:
     <=6 formations, <=350 rotation plays, each formation <=75 plays.

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
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations, product

from .parser import SUB_SETS, FormationInfo, PlayInfo, infer_formation, play_type, slugify

AUDIBLE_TYPES = ("man_pressure", "sim_pressure", "two_high", "split_match")
ALL_TYPES = ("man_pressure", "blitz", "sim_pressure", "two_high", "split_match",
             "cover3", "man_coverage", "run_plug")

BASE_REQUIRED = ("nickel-2-4-dbl-mug", "nickel-3-3-swap-mug")      # 11 personnel
SPREAD_OPTIONS = ("dollar-3-2", "dime-1-4-dbl-mug")                # 10 / 01 personnel (exact slots)

# Live huddle.gg nomenclature -> architectural slot keys (applied when clustering).
FORMATION_ALIASES = {
    "nickel-3-3-swap-dbl-mug": "nickel-3-3-swap-mug",
}


def is_spread_slot(key: str) -> bool:
    """Spread/empty (10, 01) slot: Dollar 3-2, any 'Dime 3-2 ...' variant, or Dime 1-4 Dbl Mug."""
    return key in SPREAD_OPTIONS or key.startswith("dime-3-2")

# ---- Tier 1: Madden global custom-playbook engine hard caps
MAX_TOTAL_PERSONNEL = 15
MAX_TOTAL_FRONTS = 73
MAX_TOTAL_PLAYS = 750
MAX_PLAYS_PER_FRONT = 75

# ---- Tier 2: tactical active-set defaults (in-game menu filter)
ACTIVE_MAX_FORMATIONS = 6
ACTIVE_MAX_PLAYS = 350


@dataclass(frozen=True)
class Foundation:
    """In-game usage of the base playbook. User-supplied counts (not derived from the scrape)."""
    playbook: str
    personnel: int
    fronts: int
    plays: int


FOUNDATIONS = {"Minnesota Vikings": Foundation("Minnesota Vikings", personnel=9, fronts=41, plays=475)}

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
    rank: dict[str, int] = field(default_factory=dict)   # playbook -> scrape order (== on-site list order)

    @property
    def types(self) -> set[str]:
        return {p.ptype for p in self.plays.values()}

    @property
    def has_all_audibles(self) -> bool:
        return audible_assignment(self.plays.values()) is not None

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


# ------------------------------------------------------- audible slot rules
# Each slot accepts plays in preference tiers (0 = purest form of the slot). A formation is
# audible-complete when four DISTINCT plays can fill the four slots.
_RE_CREEPER_ALIAS = re.compile(r"\bfire\s*\d\b|\bcoffee\s*house\b")
TIER_NOTES: dict[str, dict[int, str]] = {
    "man_pressure": {0: "Cover 0 blitz", 1: "Cover 1 man blitz", 2: "Cover 1 man (no added rusher)"},
    "sim_pressure": {0: "4-man sim pressure", 1: "creeper alias (Fire N / Coffee House)"},
    "two_high": {0: "Tampa 2 / Cover 2 family", 1: "Cover 3 Cloud"},
    "split_match": {0: "Cover 4 / Cover 6 / Cover 9 match", 1: "Cover 3 Match", 2: "fallback: 2 Invert"},
}


def slot_tier(slot: str, p: PlayRec) -> int | None:
    """Preference tier of play `p` for audible `slot`, or None if it cannot fill the slot."""
    i, n = p.info, p.name.lower()
    if i.is_run_plug:
        return None
    cover3 = i.coverage_family == "Cover 3 Sky/Buzz/Cloud"
    if slot == "man_pressure":
        if p.ptype == "man_pressure":
            return 0
        if i.coverage_family == "Cover 1":
            return 1 if i.is_blitz else 2
    elif slot == "sim_pressure":
        if i.is_sim_pressure:
            return 0
        if _RE_CREEPER_ALIAS.search(n):
            return 1
    elif slot == "two_high":
        if p.ptype == "two_high":
            return 0
        if cover3 and not i.is_blitz and "cloud" in n:
            return 1
    elif slot == "split_match":
        if p.ptype == "split_match":
            return 0
        if cover3 and not i.is_blitz and not i.is_sim_pressure and "match" in n:
            return 1
        if p.ptype == "two_high" and "invert" in n:
            return 2
    return None


def audible_assignment(plays) -> dict[str, tuple[PlayRec, int]] | None:
    """Best distinct-play assignment to the four audible slots (min total tier, then max value)."""
    plays = list(plays)
    cands: list[list[tuple[int, PlayRec]]] = []
    for s in AUDIBLE_TYPES:
        lst = sorted(((t, p) for p in plays if (t := slot_tier(s, p)) is not None),
                     key=lambda x: (x[0], -x[1].value, x[1].name))[:6]
        if not lst:
            return None
        cands.append(lst)
    best, best_key = None, None
    for combo in product(*cands):
        names = [p.name for _, p in combo]
        if len(set(names)) < len(names):
            continue
        key = (sum(t for t, _ in combo), -sum(p.value for _, p in combo), tuple(names))
        if best_key is None or key < best_key:
            best, best_key = combo, key
    if best is None:
        return None
    return {s: (p, t) for s, (t, p) in zip(AUDIBLE_TYPES, best)}


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
        "SELECT p.name AS pb, f.formation_id AS fid, f.formation_name, pl.play_name, pl.coverage_family, pl.rush_count, "
        "pl.is_sim_pressure, pl.is_blitz, pl.is_run_plug FROM formations f "
        "JOIN playbooks p USING(playbook_id) LEFT JOIN plays pl USING(formation_id) "
        "ORDER BY p.name, f.formation_name, pl.play_name").fetchall()
    clusters: dict[str, Cluster] = {}
    for r in rows:
        info = infer_formation(r["formation_name"])
        key = FORMATION_ALIASES.get(info.key, info.key)
        c = clusters.setdefault(key, Cluster(key, info))
        c.sources.add(r["pb"])
        c.rank[r["pb"]] = min(r["fid"], c.rank.get(r["pb"], r["fid"]))
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


def trim_plays(c: Cluster, cap: int, must_keep=()) -> list[PlayRec]:
    """Top-`cap` plays by value, always keeping the plays assigned to audible slots."""
    ranked = sorted(c.plays.values(), key=lambda p: (-p.value, p.name))
    keep = {p.name: p for p in must_keep}
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
    audibles: dict[str, tuple[PlayRec, int]] | None = None


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
    audible_tiers: dict[str, int] = field(default_factory=dict)
    in_game_source: str = ""                                 # playbook whose version of this front is in-game
    in_game_plays: list[str] = field(default_factory=list)   # that front's plays, alphabetical (menu order)


@dataclass
class PlaybookResult:
    base: str | None
    style: str
    objective: float
    formations: list[SelectedFormation]
    constraints: list[tuple[str, bool, str]]
    budget: dict | None = None

    @property
    def total_plays(self) -> int:
        return sum(len(f.plays) for f in self.formations)

    def to_dict(self) -> dict:
        return {
            "base": self.base, "style": self.style, "objective": round(self.objective, 3),
            "total_formations": len(self.formations), "total_plays": self.total_plays,
            "constraint_active": {"formations": ACTIVE_MAX_FORMATIONS, "plays": ACTIVE_MAX_PLAYS},
            "constraints": [{"name": n, "ok": ok, "detail": d} for n, ok, d in self.constraints],
            "global_budget": self.budget,
            "formations": [{
                "name": f.name, "key": f.key, "set": f.set_name, "front": f.front_type,
                "personnel": list(f.personnel), "disguise_entropy": round(f.entropy, 3),
                "source_playbooks": f.sources,
                "in_game_source": f.in_game_source, "in_game_plays": f.in_game_plays,
                "audibles": {t: p.name for t, p in f.audibles.items()},
                "audible_notes": {t: TIER_NOTES[t][f.audible_tiers[t]] for t in f.audibles},
                "plays": [{"name": p.name, "type": p.ptype, "coverage": p.info.coverage_family,
                           "rush": p.info.rush_count} for p in f.plays],
            } for f in self.formations],
        }


def _candidates(clusters, weights, base, cap) -> list[Candidate]:
    out = []
    for c in clusters:
        value_plays(c, weights, base)
        # With a base playbook, audibles must be plays that exist in the in-game version of that front
        # (the base's, or the donor's for an added front) so they are selectable without adding plays.
        donor = (base if base in c.sources else sorted(c.sources)[0]) if base else None
        aud = audible_assignment(p for p in c.plays.values() if donor is None or donor in p.sources)
        plays = trim_plays(c, cap, [p for p, _ in aud.values()] if aud else ())
        ent = disguise_entropy(c.info, plays)
        out.append(Candidate(c, plays, sum(p.value for p in plays) + ENTROPY_WEIGHT * ent, aud))
    return out


def _score(combo: list[Candidate]) -> float:
    fam = set().union(*(c.cluster.families for c in combo))
    return sum(c.value for c in combo) + FAMILY_BONUS * len(fam)


def solve(clusters: list[Cluster], *, base: str | None = None, style: str = "flores-macdonald",
          max_formations: int = ACTIVE_MAX_FORMATIONS, max_plays: int = ACTIVE_MAX_PLAYS,
          entropy_min: float = ENTROPY_MIN) -> PlaybookResult:
    if style not in STYLES:
        raise InfeasibleError(f"unknown style {style!r}; choose from {', '.join(STYLES)}")
    weights = STYLES[style]
    cap = min(MAX_PLAYS_PER_FRONT, max(len(AUDIBLE_TYPES), max_plays // max_formations))

    cands = {c.cluster.key: c for c in _candidates(clusters, weights, base, cap)}
    # C4 (audible completeness) + C2 (disguise entropy for sub-package sets)
    elig = {k: c for k, c in cands.items()
            if c.audibles is not None
            and (c.cluster.info.set_name not in SUB_SETS or disguise_entropy(c.cluster.info, c.plays) >= entropy_min)}

    missing = [k for k in BASE_REQUIRED if k not in elig]
    if missing:
        raise InfeasibleError(f"11-personnel requirement unmet; missing/ineligible: {', '.join(missing)}")
    heavy = [c for c in elig.values() if c.cluster.info.is_five_front]
    spread = [c for k, c in elig.items() if is_spread_slot(k)]
    if not heavy:
        raise InfeasibleError("heavy-set requirement unmet: no eligible 5-front (3-4 Bear / 5-2 / 4-3 Even 6-1)")
    if not spread:
        raise InfeasibleError("spread-set requirement unmet: need Dollar 3-2, a Dime 3-2 variant or Dime 1-4 Dbl Mug")

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
    by_key = {c.cluster.key: c.cluster for c in cands.values()}
    for f in sel:
        cl = by_key[f.key]
        f.in_game_source = base if base and base in cl.sources else sorted(cl.sources)[0]
        f.in_game_plays = sorted((p.name for p in cl.plays.values() if f.in_game_source in p.sources), key=str.lower)
    res = PlaybookResult(base, style, best[0], sel, [])
    res.budget = global_budget(base, clusters, sel)
    res.constraints = verify(res, max_formations, max_plays, entropy_min)
    return res


def global_budget(base: str | None, clusters: list[Cluster], sel: list[SelectedFormation]) -> dict | None:
    """Tier-1 accounting: base foundation + hybrid additions vs the engine caps; retained/added/pruned fronts."""
    found = FOUNDATIONS.get(base) if base else None
    if found is None:
        return None
    base_clusters = {c.key: c for c in clusters if base in c.sources}
    sel_keys = {f.key for f in sel}
    retained = [f for f in sel if f.key in base_clusters]
    added = [f for f in sel if f.key not in base_clusters]
    # a play is new to the base playbook when the base playbook does not have it in that front
    sel_clusters = {c.key: c for c in clusters if c.key in sel_keys}
    added_plays = 0
    for f in sel:
        for p in f.plays:
            if f.key not in base_clusters or base not in sel_clusters[f.key].plays[slugify(p.name)].sources:
                added_plays += 1
    base_sets = {c.info.set_name for c in base_clusters.values()}
    new_personnel = len({f.set_name for f in added} - base_sets)
    pruned = sorted(c.info.formation_name for k, c in base_clusters.items() if k not in sel_keys)
    return {
        "base": base, "foundation": {"personnel": found.personnel, "fronts": found.fronts, "plays": found.plays},
        "caps": {"personnel": MAX_TOTAL_PERSONNEL, "fronts": MAX_TOTAL_FRONTS, "plays": MAX_TOTAL_PLAYS,
                 "plays_per_front": MAX_PLAYS_PER_FRONT},
        "remaining": {"personnel": MAX_TOTAL_PERSONNEL - found.personnel, "fronts": MAX_TOTAL_FRONTS - found.fronts,
                      "plays": MAX_TOTAL_PLAYS - found.plays},
        "added": {"personnel": new_personnel, "fronts": len(added), "plays": added_plays},
        "totals_if_base_kept": {"personnel": found.personnel + new_personnel, "fronts": found.fronts + len(added),
                                "plays": found.plays + added_plays},
        "scraped_base_fronts": len(base_clusters),
        "base_order": [c.info.formation_name for c in sorted(base_clusters.values(), key=lambda c: c.rank[base])],
        "retained": [{"name": f.name, "plays": len(f.plays)} for f in retained],
        "added_fronts": [{"name": f.name, "plays": len(f.plays), "from": f.sources} for f in added],
        "pruned": pruned,
    }


def _to_selected(c: Candidate) -> SelectedFormation:
    i = c.cluster.info
    return SelectedFormation(c.cluster.key, i.formation_name, i.set_name, i.front_type, i.personnel_groups,
                             disguise_entropy(i, c.plays), sorted(c.cluster.sources), c.plays,
                             {s: p for s, (p, _) in c.audibles.items()},
                             {s: t for s, (_, t) in c.audibles.items()})


def verify(res: PlaybookResult, max_formations=6, max_plays=350, entropy_min=ENTROPY_MIN) -> list[tuple[str, bool, str]]:
    keys = {f.key for f in res.formations}
    checks = [
        ("T-active formations <= cap", len(res.formations) <= max_formations, f"{len(res.formations)}/{max_formations}"),
        ("T-active rotation plays <= cap", res.total_plays <= max_plays, f"{res.total_plays}/{max_plays}"),
    ]
    biggest = max(res.formations, key=lambda f: len(f.plays))
    checks.append(("G-engine plays per front <= %d" % MAX_PLAYS_PER_FRONT, len(biggest.plays) <= MAX_PLAYS_PER_FRONT,
                   f"largest: {biggest.name} ({len(biggest.plays)})"))
    b = res.budget
    if b:
        t = b["totals_if_base_kept"]
        for label, key, cap in (("personnel", "personnel", MAX_TOTAL_PERSONNEL), ("fronts", "fronts", MAX_TOTAL_FRONTS),
                                ("plays", "plays", MAX_TOTAL_PLAYS)):
            checks.append((f"G-engine total {label} <= {cap}", t[key] <= cap,
                           f"{b['foundation'][key]} base + {b['added'][key]} added = {t[key]}"))
    sub = [f for f in res.formations if f.set_name in SUB_SETS]  # tactical disguise rule
    low = [f.name for f in sub if f.entropy < entropy_min]
    checks.append(("C2 disguise entropy (nickel/dime/dollar)", not low,
                   "all >= %.2f" % entropy_min if not low else "below threshold: " + ", ".join(low)))
    five = [f.name for f in res.formations if infer_formation(f.name).is_five_front]
    checks.append(("C3 heavy (12/21/22) -> 5-front", bool(five), ", ".join(five) or "none"))
    checks.append(("C3 base (11) -> Nickel 2-4 Dbl Mug + Nickel 3-3 Swap Mug",
                   all(k in keys for k in BASE_REQUIRED), "present" if all(k in keys for k in BASE_REQUIRED) else "missing"))
    sp = sorted(k for k in keys if is_spread_slot(k))
    checks.append(("C3 spread (10/01) -> Dollar 3-2 / Dime 3-2 variant / Dime 1-4 Dbl Mug", bool(sp), ", ".join(sp) or "none"))
    bad = [f.name for f in res.formations if audible_assignment(f.plays) is None]
    if res.base:   # only meaningful when applying onto a base playbook
        checks.append(("G-macro audible plays exist in the in-game front",
                       all(p.name in f.in_game_plays for f in res.formations for p in f.audibles.values()),
                       "all 4 per front selectable"))
    checks.append(("C4 audible completeness (4 distinct slot plays each)", not bad, "all formations complete" if not bad else ", ".join(bad)))
    return checks
