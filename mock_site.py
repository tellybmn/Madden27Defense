"""Synthetic huddle.gg-style DOM renderer used for offline scraping and tests.

NOTE: the DOM here is a *model* of the sites (formation cards + play table); the
live sites' real markup was not verifiable from the build environment, so parser
selectors live in one place (parser.parse_index / parse_formation_page) for easy
adjustment once real pages are captured as fixtures.
"""
from __future__ import annotations

from html import escape

from parser import slugify

HOST = "https://huddle.gg"


def render_index(playbook_name: str, playbook_slug: str, formation_names: list[str]) -> str:
    cards = "\n".join(
        f'    <a class="formation-card" href="/playbooks/{playbook_slug}/{slugify(f)}" data-formation="{escape(f)}">'
        f'<h3 class="formation-name">{escape(f)}</h3></a>' for f in formation_names)
    return (f'<!doctype html><html><head><title>{escape(playbook_name)} Defensive Playbook</title></head><body>\n'
            f'<main><h1 class="playbook-title">{escape(playbook_name)}</h1>\n'
            f'  <nav class="formation-grid" data-role="formation-nav">\n{cards}\n  </nav></main></body></html>')


def render_formation(formation_name: str, plays: list[str]) -> str:
    rows = "\n".join(
        f'    <tr class="play-row"><td class="play-name">{escape(p)}</td><td class="play-meta">DEF</td></tr>'
        for p in plays)
    return (f'<!doctype html><html><body><h1 class="formation-title">{escape(formation_name)}</h1>\n'
            f'<table class="play-table"><tbody>\n{rows}\n</tbody></table></body></html>')


def build_site(catalog: dict[str, dict[str, list[str]]], host: str = HOST) -> dict[str, str]:
    """catalog: {playbook_slug: {formation_name: [play titles]}} -> {url: html}."""
    from parser import playbook_display_name
    pages: dict[str, str] = {}
    for slug, formations in catalog.items():
        pages[f"{host}/playbooks/{slug}"] = render_index(playbook_display_name(slug), slug, list(formations))
        for fname, plays in formations.items():
            pages[f"{host}/playbooks/{slug}/{slugify(fname)}"] = render_formation(fname, plays)
    return pages
