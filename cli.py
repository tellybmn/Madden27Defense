#!/usr/bin/env python3
"""Madden defensive playbook pipeline CLI."""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

import db
import optimizer
import scraper
from mock_site import build_site
from seed_catalog import CATALOG

console = Console()
DEFAULT_OUT = "custom_playbook.json"

# Quick-audible slots. Button mapping is a suggested default; remap to your controller layout.
SLOTS = {
    "man_pressure": ("1", "Y / Triangle", "All-out man pressure (Cover 0 / cross-dog)",
                     "Hold the common pre-snap look (mug / 2-high); call after last motion"),
    "sim_pressure": ("2", "X / Square", "Creeper / sim pressure (4 rush, zone drop)",
                     "Same look; slot/LB fires, DE drops to hook; no safety rotation"),
    "two_high": ("3", "B / Circle", "Disguised 2-high / invert (Tampa 2, Cover 2 Invert)",
                 "Keep safeties deep; walk a safety down late only if audible is Invert"),
    "split_match": ("4", "A / Cross", "Split-field match (Cover 4 Palms / Quarters / Cover 6)",
                    "Shell stays 2-high; match rules decide field/boundary reads post-snap"),
}


def cmd_test(args) -> int:
    return subprocess.call([sys.executable, "-m", "pytest", "tests", "-q", *args.pytest_args],
                           cwd=Path(__file__).parent)


def cmd_scrape(args) -> int:
    slugs = scraper.resolve_slugs(args.teams)

    async def run():
        if args.offline:
            loader, fallback = scraper.MockLoader(build_site({s: CATALOG[s] for s in slugs if s in CATALOG})), None
            console.print("[yellow]OFFLINE mode: using bundled synthetic catalog (not live data).[/]")
        else:
            loader = scraper.HttpxLoader(min_interval=args.rate_limit)
            fallback = scraper.PlaywrightLoader() if args.playwright else None
        try:
            return await scraper.Scraper(loader, fallback_loader=fallback).scrape_many(slugs)
        finally:
            if hasattr(loader, "aclose"):
                await loader.aclose()

    results = asyncio.run(run())
    conn = db.connect(args.db)
    t = Table(title="Scrape results")
    for c in ("Playbook", "Formations", "Plays", "Errors"):
        t.add_column(c)
    total_f = 0
    for sp in results:
        st = db.ingest_playbook(conn, sp)
        total_f += st["formations"]
        t.add_row(sp.name, str(st["formations"]), str(st["plays"]), str(len(sp.errors)))
        for e in sp.errors:
            console.print(f"[red]  {e}[/]")
    console.print(t)
    console.print(f"DB totals: {db.counts(conn)}")
    return 0 if total_f else 1


def cmd_build(args) -> int:
    conn = db.connect(args.db)
    if db.counts(conn)["plays"] == 0:
        console.print("[red]Database is empty. Run `python cli.py scrape ...` first (add --offline for the bundled catalog).[/]")
        return 1
    try:
        base = optimizer.resolve_playbook_name(conn, args.base)
        res = optimizer.solve(optimizer.load_clusters(conn), base=base, style=args.style,
                              max_formations=args.max_formations, max_plays=args.max_plays)
    except optimizer.InfeasibleError as e:
        console.print(f"[red]Infeasible: {e}[/]")
        return 2
    Path(args.out).write_text(json.dumps(res.to_dict(), indent=2))

    t = Table(title=f"Custom playbook  (base={base or 'none'}, style={res.style})")
    for c in ("Formation", "Set", "Personnel", "Plays", "Entropy", "Sources"):
        t.add_column(c)
    for f in res.formations:
        t.add_row(f.name, f.set_name, "/".join(f.personnel), str(len(f.plays)), f"{f.entropy:.2f}", ", ".join(f.sources))
    console.print(t)
    for name, ok, detail in res.constraints:
        console.print(f"  {'[green]PASS[/]' if ok else '[red]FAIL[/]'} {name} -- {detail}")
    console.print(f"Total: {len(res.formations)} formations, {res.total_plays} plays. Saved to {args.out}")
    return 0 if all(ok for _, ok, _ in res.constraints) else 3


def cmd_export(args) -> int:
    p = Path(args.playbook)
    if not p.exists():
        console.print(f"[red]{p} not found. Run `python cli.py build` first.[/]")
        return 1
    data = json.loads(p.read_text())
    t = Table(title="Quick-audible setup (suggested button layout -- remap as needed)")
    for c in ("Formation", "Slot", "Button", "Audible type", "Play", "Pre-snap note"):
        t.add_column(c)
    for f in data["formations"]:
        for typ, play in f["audibles"].items():
            slot, btn, label, note = SLOTS[typ]
            t.add_row(f["name"], slot, btn, label, play, note)
        t.add_section()
    console.print(t)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="cli.py", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("test", help="run pytest offline")
    s.add_argument("pytest_args", nargs="*")
    s.set_defaults(fn=cmd_test)

    s = sub.add_parser("scrape", help="scrape playbooks into SQLite")
    s.add_argument("--teams", default="vikings,seahawks,jaguars,ravens", help="comma list (aliases or full slugs)")
    s.add_argument("--offline", action="store_true", help="use bundled synthetic mock site, no network")
    s.add_argument("--playwright", action="store_true", help="fallback to headless browser for JS pages")
    s.add_argument("--rate-limit", type=float, default=1.5, help="min seconds between requests")
    s.add_argument("--db", default=db.DEFAULT_DB)
    s.set_defaults(fn=cmd_scrape)

    s = sub.add_parser("build", help="synthesize optimal custom playbook")
    s.add_argument("--base", default="vikings")
    s.add_argument("--style", default="flores-macdonald", choices=sorted(optimizer.STYLES))
    s.add_argument("--max-formations", type=int, default=6)
    s.add_argument("--max-plays", type=int, default=350)
    s.add_argument("--db", default=db.DEFAULT_DB)
    s.add_argument("--out", default=DEFAULT_OUT)
    s.set_defaults(fn=cmd_build)

    s = sub.add_parser("export-audibles", help="print controller audible table")
    s.add_argument("--playbook", default=DEFAULT_OUT)
    s.set_defaults(fn=cmd_export)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except ValueError as e:
        console.print(f"[red]{e}[/]")
        return 2


if __name__ == "__main__":
    sys.exit(main())
