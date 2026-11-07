"""Illustrative offline catalog used by `scrape --offline`.

IMPORTANT: this is NOT scraped data. It is a synthetic reconstruction of the
formations named in the project brief, filled with representative play titles
so the full parse -> classify -> DB -> optimize path runs with zero network.
Replace it with real data via `python cli.py scrape` (live) once the parser
selectors have been checked against the real sites.
"""
from __future__ import annotations

from html import escape

import re

from .parser import playbook_display_name, playbook_path, slugify

POOLS: dict[str, list[str]] = {
    "man_pressure": ["Cover 0 Blitz", "Mid Blitz 0", "Cross Dog 0", "Double A Gap Blitz 0", "Overload Blitz 0"],
    "sim": ["Nickel Dog 3 Buzz", "Creeper Cover 3 Sky", "Zone Exchange Cover 4 Palms",
            "Mug Bluff Cover 2 Invert", "Wham Cover 3 Cloud", "Dime Dog 3 Sky"],
    "two_high": ["Tampa 2", "Cover 2 Invert", "Cover 2 Sink", "Cover 2 Hard Flat"],
    "split": ["Cover 4 Palms", "Cover 4 Match", "Cover 6", "Cover 9", "Cover 4 Quarters", "Split-Field Cover 6"],
    "cover3": ["Cover 3 Sky", "Cover 3 Buzz", "Cover 3 Cloud", "Cover 3 Match", "Cover 3 Curl Flat"],
    "man": ["Cover 1 Robber", "Cover 1 Hole", "Cover 2 Man Under", "Cover 1 Spy"],
    "blitz": ["Fire Zone 3", "Safety Blitz Cover 1", "LB Blitz Cover 3 Sky", "Corner Blitz Cover 3 Cloud"],
    "plug": ["Pinch Dog 2", "Edge Sting", "Shoot Gap Cover 1", "Run Stop Cover 3 Sky"],
}


def _mk(rot: int, **counts: int) -> list[str]:
    plays: list[str] = []
    for kind, n in counts.items():
        pool = POOLS[kind]
        plays += [pool[(rot + i) % len(pool)] for i in range(min(n, len(pool)))]
    return list(dict.fromkeys(plays))


_FULL = dict(man_pressure=4, sim=4, two_high=3, split=4, cover3=3, man=2, blitz=2, plug=2)
_GOAL = dict(plug=4, man=2, cover3=1)  # deliberately lacks audible completeness

CATALOG: dict[str, dict[str, list[str]]] = {
    "minnesota-vikings": {
        "Nickel 2-4 Dbl Mug": _mk(0, **_FULL),
        "Dime 1-4 Dbl Mug": _mk(1, **_FULL),
        "4-3 Even 6-1": _mk(2, **_FULL),
    },
    "miami-dolphins": {
        "Nickel 2-4 Dbl Mug": _mk(1, **_FULL),
        "Dime 1-4 Dbl Mug": _mk(2, **_FULL),
        "3-4 Bear": _mk(1, **_FULL),
        "4-3 Even 6-1": _mk(3, **_FULL),
    },
    "seattle-seahawks": {
        "3-4 Bear": _mk(2, **dict(_FULL, sim=5, split=5)),
        "Nickel 2-4 Dbl Mug": _mk(2, **dict(_FULL, sim=5)),
        "Dollar 3-2": _mk(0, **dict(_FULL, split=5)),
    },
    "baltimore-ravens": {
        "Nickel 2-4 Dbl Mug": _mk(3, **dict(_FULL, sim=6)),
        "Dime 1-4 Dbl Mug": _mk(0, **dict(_FULL, sim=5)),
        "3-4 Bear": _mk(3, **_FULL),
        "Nickel 3-3 Swap Mug": _mk(1, **dict(_FULL, sim=5)),
    },
    "jacksonville-jaguars": {
        "Nickel 3-3 Dbl Mug": _mk(0, **_FULL),
        "Nickel 3-3 Swap Mug": _mk(0, **_FULL),
        "4-2-5 Over G": _mk(2, **_FULL),
        "Goal Line 5-3": _mk(0, **_GOAL),
    },
    "multiple-d": {
        "5-2": _mk(0, **_FULL),
        "3-4 Bear": _mk(0, **_FULL),
        "Dollar 3-2": _mk(2, **_FULL),
    },
}


# ---- synthetic renderer that mirrors the real huddle.gg DOM (verified against live pages)
HOST = "https://huddle.gg"


def _huddle_slug(text: str) -> str:
    """huddle.gg slugs keep a double dash between digits: '3-4 Bear' -> '3--4-bear'."""
    return re.sub(r"(?<=\d)-(?=\d)", "--", slugify(text))


def _split_heading(name: str) -> tuple[str, str]:
    m = re.match(r"^(nickel|dime|dollar|quarter|goal line)\s+(.*)$", name, re.I)
    if m:
        return m.group(1).title(), m.group(2)
    m = re.match(r"^(\d(?:-\d)+)\s*(.*)$", name)
    return (m.group(1), m.group(2) or m.group(1)) if m else (name, name)


def render_index(playbook_name: str, playbook_slug: str, formation_names: list[str]) -> str:
    groups: dict[str, list[tuple[str, str]]] = {}
    for f in formation_names:
        head, rest = _split_heading(f)
        groups.setdefault(head, []).append((rest, f))
    hs = playbook_path(playbook_slug).strip("/").split("/")[-1]
    blocks = []
    for head, items in groups.items():
        lis = "\n".join(
            f'<li class="playbooks-list__item"><a class="playbooks-list__link" '
            f'href="/27/playbooks/{hs}/{_huddle_slug(full)}/">\n  {escape(rest)}\n</a></li>'
            for rest, full in items)
        blocks.append(f'<div class="wrapper pb-5"><h3 class="heading">{escape(head)}</h3>\n'
                      f'<ul class="playbooks-list">\n{lis}\n</ul></div>')
    return (f'<!doctype html><html><head><title>{escape(playbook_name)} Defense Playbook</title></head><body>'
            f'<h1>{escape(playbook_name)}</h1>\n' + "\n".join(blocks) + '</body></html>')


def render_formation(formation_name: str, plays: list[str]) -> str:
    tiles = "\n".join(
        f'<a class="play-tile2" href="#"><img alt="{escape(p)}" src="x.jpg"/>'
        f'<div class="play-tile2__info"><span>{escape(p.upper())}</span></div></a>' for p in plays)
    return (f'<!doctype html><html><body><h1>{escape(formation_name)}</h1>'
            f'<div class="l-sidebar__main"><h2 class="heading">{escape(formation_name)}</h2>\n'
            f'<div class="play-tile2-list">\n{tiles}\n</div></div></body></html>')


def build_site(catalog: dict[str, dict[str, list[str]]], host: str = HOST) -> dict[str, str]:
    """catalog: {playbook_slug: {formation_name: [play titles]}} -> {url: html}."""
    pages: dict[str, str] = {}
    for slug, formations in catalog.items():
        pages[f"{host}{playbook_path(slug)}"] = render_index(playbook_display_name(slug), slug, list(formations))
        hs = playbook_path(slug).strip("/").split("/")[-1]
        for fname, plays in formations.items():
            pages[f"{host}/27/playbooks/{hs}/{_huddle_slug(fname)}/"] = render_formation(fname, plays)
    return pages
