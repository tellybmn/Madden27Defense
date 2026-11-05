"""HTML parsing + rule-based play/formation classification (pure, no I/O)."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup

COVERAGE_FAMILIES = (
    "Cover 0", "Cover 1", "Cover 2 Man", "Tampa 2",
    "Cover 3 Sky/Buzz/Cloud", "Cover 4 Match/Palms", "Cover 6/9", "Unknown",
)

# ---------------------------------------------------------------- text utils
_DASHES = {ord(c): "-" for c in "‐‑‒–—−"}


def clean_text(s: str | None) -> str:
    """NFKC-normalise, unify dashes/nbsp, collapse whitespace."""
    s = unicodedata.normalize("NFKC", s or "").translate(_DASHES)
    return re.sub(r"\s+", " ", s).strip()


def slugify(s: str) -> str:
    s = clean_text(s).lower().replace("&", " and ")
    s = re.sub(r"['’`]", "", s)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def canonical_formation_key(name: str) -> str:
    """Alias-insensitive key: 'Nickel 2-4 Double Mug' == 'Nickel 2-4 Dbl. Mug'."""
    low = clean_text(name).lower().replace(".", "")
    low = re.sub(r"\bdouble\b", "dbl", low)
    return slugify(low)


# ------------------------------------------------------------ play classifier
_RE_C69 = re.compile(r"\b(?:cover|cov|cvr)\s*-?\s*[69]\b|\bsplit[\s-]*field\b|\bquarter[\s-]*quarter[\s-]*half\b|\bqqh\b")
_RE_COVN = re.compile(r"\b(?:cover|cov|cvr)\s*-?\s*([0-5])\b")
_RE_C2MAN = re.compile(r"\b(?:cover|cov|cvr)\s*-?\s*2\s*-?\s*man\b|\b2[\s-]*man\s*under\b")
_RE_BARE = re.compile(r"\b(?:blitz|dog|pinch|sting|storm|fire\s*zone|crash|wham|cross\s*dog)\s*([0-4])\b")
_KEYWORD_COVERAGE = (
    (re.compile(r"\bcross[\s-]*dog\b|\bzero\b|\ball[\s-]*out\b"), "Cover 0"),
    (re.compile(r"\btampa\b|\binvert\b"), "Tampa 2"),
    (re.compile(r"\bpalms?\b|\bquarters\b|\bquarter\b"), "Cover 4 Match/Palms"),
    (re.compile(r"\bsky\b|\bbuzz\b|\bcloud\b|\bcurl[\s-]*flat\b"), "Cover 3 Sky/Buzz/Cloud"),
    (re.compile(r"\bman[\s-]*free\b|\brobber\b|\bspy\b"), "Cover 1"),
)
_DIGIT_FAMILY = {
    0: "Cover 0", 1: "Cover 1", 2: "Tampa 2", 3: "Cover 3 Sky/Buzz/Cloud", 4: "Cover 4 Match/Palms",
}

_RE_RUSH_HINT = re.compile(r"(?<!cover )\b([3-8])[\s-]*(?:man|men)\b|\brush(?:ers)?\s*[:=]?\s*([3-8])\b")
_RE_DROP8 = re.compile(r"\bprevent\b|\bdrop[\s-]*8\b")
_RE_BLITZ = re.compile(
    r"\bblitz\b|\boverload\b|\bfire[\s-]*zone\b|\bdouble\s+[ab][\s-]*gap\b|\ball[\s-]*out\b|\bstorm\b")
_RE_SIM = re.compile(r"\bdog\b|\bcreeper\b|\bsim(?:ulated)?\b|\bexchange\b|\bwham\b|\bbluff\b|\bstunt\b|\btilt\b")
_RE_PLUG = re.compile(r"\bpinch\b|\bsting\b|\bshoot\b|\bplug\b|\bcrash\b|\brun[\s-]*(?:stop|stuff)\b|\bstuff\b|\bgoal[\s-]*line\b")


@dataclass(frozen=True)
class PlayInfo:
    play_name: str
    coverage_family: str
    rush_count: int          # 3 (<=3), 4, 5, 6 (6+)
    is_sim_pressure: bool
    is_blitz: bool
    is_run_plug: bool

    @property
    def play_type(self) -> str:
        return play_type(self)


def _normalise_for_rules(name: str) -> str:
    return re.sub(r"[()\[\],:/]", " ", clean_text(name).lower())


def detect_coverage(n: str) -> str:
    if _RE_C69.search(n):
        return "Cover 6/9"
    if _RE_C2MAN.search(n):
        return "Cover 2 Man"
    m = _RE_COVN.search(n)
    if m:
        return _DIGIT_FAMILY[int(m.group(1))] if int(m.group(1)) in _DIGIT_FAMILY else "Unknown"
    for rx, fam in _KEYWORD_COVERAGE:
        if rx.search(n):
            return fam
    m = _RE_BARE.search(n)
    if m:
        return _DIGIT_FAMILY[int(m.group(1))]
    return "Unknown"


def classify_play(raw_name: str) -> PlayInfo:
    """Rule-based heuristic classification of a raw play title."""
    name = clean_text(raw_name)
    n = _normalise_for_rules(name)
    family = detect_coverage(n)
    is_plug = bool(_RE_PLUG.search(n))

    hint = _RE_RUSH_HINT.search(n)
    if hint:
        rush = int(hint.group(1) or hint.group(2))
    elif family == "Cover 0":
        rush = 6
    elif _RE_BLITZ.search(n):
        rush = 5
    elif _RE_DROP8.search(n):
        rush = 3
    else:
        rush = 4
    rush = max(3, min(rush, 6))

    is_blitz = rush >= 5
    is_sim = (rush == 4 and not is_plug and bool(_RE_SIM.search(n)))
    return PlayInfo(name, family, rush, is_sim, is_blitz, is_plug)


def play_type(p: PlayInfo) -> str:
    """Collapse a play into one audible-relevant bucket."""
    if p.is_run_plug:
        return "run_plug"
    if p.is_blitz:
        return "man_pressure" if p.coverage_family == "Cover 0" else "blitz"
    if p.is_sim_pressure:
        return "sim_pressure"
    fam = p.coverage_family
    if fam in ("Cover 4 Match/Palms", "Cover 6/9"):
        return "split_match"
    if fam == "Tampa 2":
        return "two_high"
    if fam == "Cover 3 Sky/Buzz/Cloud":
        return "cover3"
    if fam in ("Cover 1", "Cover 2 Man"):
        return "man_coverage"
    return "other"


# --------------------------------------------------------------- formations
FIVE_FRONT_KEYS = frozenset({"3-4-bear", "5-2", "4-3-even-6-1"})
SUB_SETS = frozenset({"Nickel", "Dime", "Dollar", "Quarter"})


@dataclass(frozen=True)
class FormationInfo:
    formation_name: str
    key: str
    set_name: str
    front_type: str
    box_count: int
    mug_style: str | None  # 'dbl_mug' | 'swap_mug' | 'mug' | None

    @property
    def is_five_front(self) -> bool:
        return self.key in FIVE_FRONT_KEYS

    @property
    def personnel_groups(self) -> tuple[str, ...]:
        if self.set_name in ("Base", "Goal Line") or self.is_five_front:
            return ("12", "21", "22")
        if self.set_name in ("Dime", "Dollar", "Quarter"):
            return ("10", "01")
        return ("11",)

    @property
    def alignment_factor(self) -> float:
        """Pre-snap ambiguity of the alignment itself (0.4..1.0)."""
        two_high_capable = self.set_name in SUB_SETS
        return 0.4 + (0.35 if self.mug_style else 0.0) + (0.25 if two_high_capable else 0.0)


def infer_formation(name: str) -> FormationInfo:
    n = clean_text(name)
    low = n.lower().replace(".", "")
    if re.search(r"\bgoal\s*line\b", low):
        set_name = "Goal Line"
    elif re.search(r"\bdime\b", low):
        set_name = "Dime"
    elif re.search(r"\bdollar\b", low):
        set_name = "Dollar"
    elif re.search(r"\bquarter\b", low):
        set_name = "Quarter"
    elif re.search(r"\bnickel\b|\b4-2-5\b", low):
        set_name = "Nickel"
    else:
        set_name = "Base"

    mug = None
    if re.search(r"\b(?:dbl|double)\s*mug\b", low):
        mug = "dbl_mug"
    elif re.search(r"\bswap\s*mug\b", low):
        mug = "swap_mug"
    elif re.search(r"\bmug\b", low):
        mug = "mug"

    front = re.sub(r"^(?:goal\s*line|nickel|dime|dollar|quarter)\s+", "", n, flags=re.I)
    front = re.sub(r"\s*\b(?:dbl\.?|double|swap)?\s*mug\b", "", front, flags=re.I).strip() or n

    m = re.search(r"(\d)-(\d)", low)
    box = int(m.group(1)) + int(m.group(2)) if m else 6
    return FormationInfo(n, canonical_formation_key(n), set_name, front, min(box, 11), mug)


# ---------------------------------------------------------------- HTML parse
@dataclass(frozen=True)
class FormationLink:
    name: str
    slug: str
    url: str


@dataclass
class ScrapedFormation:
    info: FormationInfo
    url: str
    plays: list[PlayInfo] = field(default_factory=list)


@dataclass
class ScrapedPlaybook:
    slug: str
    name: str
    playbook_type: str
    formations: list[ScrapedFormation] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def parse_index(html: str, base_url: str = "") -> list[FormationLink]:
    """Extract formation navigation cards from a playbook index page."""
    soup = BeautifulSoup(html or "", "lxml")
    links: list[FormationLink] = []
    seen: set[str] = set()
    for a in soup.select("a.formation-card, a[data-formation]"):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        label = a.get("data-formation")
        if not label:
            el = a.select_one(".formation-name") or a
            label = el.get_text(" ")
        name = clean_text(label)
        slug = slugify(name)
        if not slug or slug in seen:
            continue
        seen.add(slug)
        links.append(FormationLink(name, slug, urljoin(base_url, href)))
    return links


def parse_formation_page(html: str) -> list[str]:
    """Extract raw play titles (deduplicated, order preserved)."""
    soup = BeautifulSoup(html or "", "lxml")
    out: list[str] = []
    seen: set[str] = set()
    for el in soup.select(".play-row .play-name, li.play .play-name, [data-play-name]"):
        title = clean_text(el.get("data-play-name") or el.get_text(" "))
        if title and title.lower() not in seen:
            seen.add(title.lower())
            out.append(title)
    return out


def playbook_display_name(slug: str) -> str:
    if slug == "multiple-d":
        return "Multiple D"
    return " ".join(w.capitalize() for w in slug.split("-"))
