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

from . import database as db
from . import optimizer
from . import scraper
from .offline_data import CATALOG, build_site

console = Console()
DEFAULT_OUT = str(Path(__file__).resolve().parents[1] / "data" / "custom_playbook.json")

# Quick-audible slots. Button mapping is a suggested default; remap to your controller layout.
SLOTS = {
    "man_pressure": ("1", "Y / Triangle", "Man / all-out pressure (Cover 0 blitz or Cover 1 Hole / man blitz)",
                     "Hold the common pre-snap look (mug / 2-high); call after last motion"),
    "sim_pressure": ("2", "X / Square", "Creeper / sim pressure (4-man sim, Fire 3, Coffee House 3)",
                     "Same look; slot/LB fires, DE drops to hook; no safety rotation"),
    "two_high": ("3", "B / Circle", "2-high / disguise zone (Tampa 2, Cover 2 Invert, Cover 3 Cloud)",
                 "Keep safeties deep; walk a safety down late only if audible is Invert"),
    "split_match": ("4", "A / Cross", "Match / base check (Cover 4/6/9, Cover 3 Match, 2 Invert fallback)",
                    "Shell stays 2-high; match rules decide field/boundary reads post-snap"),
}


def cmd_test(args) -> int:
    return subprocess.call([sys.executable, "-m", "pytest", "tests", "-q", *args.pytest_args],
                           cwd=Path(__file__).resolve().parents[1])


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


def audibles_markdown(data: dict) -> str:
    """Compact markdown cheat sheet: one 4-slot table per formation."""
    md = ["# Defensive Audible Cheat Sheet", "",
          f"Base: **{data['base'] or 'none'}** | Style: **{data['style']}** | "
          f"{data['total_formations']} formations, {data['total_plays']} plays", "",
          "Button layout is a suggested default; remap to your controller.", ""]
    for f in data["formations"]:
        md += [f"## {f['name']}  ({'/'.join(f['personnel'])} pers)", "",
               "| Slot | Button | Call | Play | Fills as |", "|---|---|---|---|---|"]
        for typ, play in f["audibles"].items():
            slot, btn, label, _ = SLOTS[typ]
            md.append(f"| {slot} | {btn} | {label} | **{play}** | {f.get('audible_notes', {}).get(typ, '')} |")
        md.append("")
    return "\n".join(md)


def cmd_export(args) -> int:
    p = Path(args.playbook)
    if not p.exists():
        console.print(f"[red]{p} not found. Run `python cli.py build` first.[/]")
        return 1
    data = json.loads(p.read_text())
    if args.format == "markdown":
        text = audibles_markdown(data)
        if args.out:
            Path(args.out).write_text(text)
            console.print(f"Cheat sheet written to {args.out}")
        else:
            print(text)
        return 0
    t = Table(title="Quick-audible setup (suggested button layout -- remap as needed)")
    for c in ("Formation", "Slot", "Button", "Audible type", "Play", "Fills as", "Pre-snap note"):
        t.add_column(c)
    for f in data["formations"]:
        for typ, play in f["audibles"].items():
            slot, btn, label, note = SLOTS[typ]
            t.add_row(f["name"], slot, btn, label, play, f.get("audible_notes", {}).get(typ, ""), note)
        t.add_section()
    console.print(t)
    return 0


def cmd_inject(args) -> int:
    from . import macro_builder as mb
    try:
        data = mb.load_inputs(Path(args.playbook), Path(args.cheat_sheet))
        profile = mb.load_profile(Path(args.profile))
        plan = mb.build_plan(data, profile)
    except (mb.MacroError, OSError, KeyError) as e:
        console.print(f"[red]{e}[/]")
        return 2
    if args.plan_out:
        Path(args.plan_out).write_text(plan.to_json())
    n = plan.counts()
    console.print(f"Plan: {n.get('key', 0)} key presses, {n.get('prompt', 0)} assist prompts, "
                  f"{n.get('wait', 0)} waits across {n.get('section', 0)} sections")
    if not args.run:
        backend = mb.DryRunBackend(profile["window_title"])
        mb.run_plan(plan, profile, backend, sleep=lambda s: None)
        console.print("[green]Dry run OK[/] (no input sent). Use --run on the PC after calibrating the profile.")
        return 0
    import time
    try:
        backend = mb.DirectInputBackend(profile.get("killswitch", "esc"))
    except mb.MacroError as e:
        console.print(f"[red]{e}[/]")
        return 3
    console.print(f"Starting in {args.start_delay}s: click into Madden now. Press {profile.get('killswitch', 'esc').upper()} to abort.")
    time.sleep(args.start_delay)
    try:
        sent = mb.run_plan(plan, profile, backend, delay_scale=args.delay_scale, live=True)
    except mb.MacroError as e:
        console.print(f"[red]Stopped: {e}[/]")
        return 3
    console.print(f"[green]Done[/]: {sent} key presses sent.")
    return 0


def cmd_inspect_saves(args) -> int:
    from . import save_inspector
    rows = save_inspector.inspect()
    if not rows:
        console.print("No Madden NFL 27 folders found under Documents (run this on the PC).")
        return 1
    for r in rows:
        console.print(f"{r['bytes']:>10}  {r['magic']}  {r['sha256_16']}  {r['path']}")
    return 0


def cmd_report(args) -> int:
    """Write a markdown report: test results, selected formations, audible matrices."""
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run([sys.executable, "-m", "pytest", "tests", "-q"], cwd=root,
                          capture_output=True, text=True)
    summary = (proc.stdout.strip().splitlines() or ["(no output)"])[-1]
    data = json.loads(Path(args.playbook).read_text())
    md = [f"# Custom Defensive Playbook Report", "",
          f"Base: **{data['base'] or 'none'}** | Style: **{data['style']}** | "
          f"Formations: **{data['total_formations']}** | Plays: **{data['total_plays']}** | "
          f"Objective: {data['objective']}", "",
          "> Data source: " + ("bundled synthetic catalog" if args.offline_note else "database contents"), "",
          "## Test results", "", f"`{summary}` (exit code {proc.returncode})", "",
          "## Constraint checks", "", "| Result | Constraint | Detail |", "|---|---|---|"]
    md += [f"| {'PASS' if c['ok'] else 'FAIL'} | {c['name']} | {c['detail']} |" for c in data["constraints"]]
    gb = data.get("global_budget")
    if gb:
        t, r, a, cp = gb["totals_if_base_kept"], gb["remaining"], gb["added"], gb["caps"]
        md += ["", "## Constraint hierarchy", "",
               "Two tiers are enforced. **Tier 1 (Madden engine caps)** bounds the whole custom playbook; "
               "**Tier 2 (tactical active set)** is the small in-game menu this optimizer selects.", "",
               "| Tier | Limit | Value | Result |", "|---|---|---|---|",
               f"| 1 Engine | Personnel | <= {cp['personnel']} | {t['personnel']} (base {gb['foundation']['personnel']} + {a['personnel']}) |",
               f"| 1 Engine | Fronts | <= {cp['fronts']} | {t['fronts']} (base {gb['foundation']['fronts']} + {a['fronts']}; {r['fronts']} slots available) |",
               f"| 1 Engine | Total plays | <= {cp['plays']} | {t['plays']} (base {gb['foundation']['plays']} + {a['plays']}; {r['plays']} available) |",
               f"| 1 Engine | Plays per front | <= {cp['plays_per_front']} | largest {max(len(f['plays']) for f in data['formations'])} |",
               f"| 2 Tactical | Active formations | <= {data['constraint_active']['formations']} | {data['total_formations']} |",
               f"| 2 Tactical | Active rotation plays | <= {data['constraint_active']['plays']} | {data['total_plays']} |",
               f"| 2 Tactical | Plays per formation | <= {cp['plays_per_front']} | all pass |", "",
               f"Totals assume the **entire** {gb['base']} base playbook is kept and the hybrid additions are layered on "
               f"(worst case). Base counts ({gb['foundation']['personnel']} personnel / {gb['foundation']['fronts']} fronts / "
               f"{gb['foundation']['plays']} plays) are user-supplied in-game numbers; the huddle.gg scrape lists "
               f"{gb['scraped_base_fronts']} {gb['base']} fronts, so retained/pruned below are relative to those.", "",
               f"### Base playbook mapping ({gb['base']})", "",
               "| Status | Front | Plays | Source |", "|---|---|---|---|"]
        md += [f"| Retained (active) | {x['name']} | {x['plays']} | {gb['base']} base |" for x in gb["retained"]]
        md += [f"| Added (hybrid) | {x['name']} | {x['plays']} | {', '.join(x['from'])} |" for x in gb["added_fronts"]]
        md += ["", f"**Pruned from the active set ({len(gb['pruned'])} scraped base fronts, still within the engine cap if kept):** "
               + ", ".join(gb["pruned"]), "",
               f"Hybrid additions use {a['fronts']} of the {r['fronts']} remaining front slots and {a['plays']} of the "
               f"{r['plays']} remaining play slots."]
    md += ["", "## Selected formations", "",
           "| Formation | Set | Personnel | Plays | Disguise entropy | Source playbooks |", "|---|---|---|---|---|---|"]
    md += [f"| {f['name']} | {f['set']} | {'/'.join(f['personnel'])} | {len(f['plays'])} | "
           f"{f['disguise_entropy']} | {', '.join(f['source_playbooks'])} |" for f in data["formations"]]
    md += ["", "## Audible matrices (4 plays per formation)", ""]
    for f in data["formations"]:
        md += [f"### {f['name']}", "", "| Slot | Button (suggested) | Audible type | Play | Fills as |", "|---|---|---|---|---|"]
        for typ, play in f["audibles"].items():
            slot, btn, label, _ = SLOTS[typ]
            md.append(f"| {slot} | {btn} | {label} | {play} | {f.get('audible_notes', {}).get(typ, '')} |")
        md.append("")
    Path(args.out).write_text("\n".join(md))
    console.print(f"Report written to {args.out}")
    return proc.returncode


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
    s.add_argument("--format", choices=("table", "markdown"), default="table")
    s.add_argument("--out", help="write the output to this file (markdown format)")
    s.set_defaults(fn=cmd_export)

    s = sub.add_parser("inject", help="apply the playbook via a keyboard macro (dry-run by default)")
    root = Path(__file__).resolve().parents[1] / "data"
    s.add_argument("--playbook", default=str(root / "live_playbook.json"))
    s.add_argument("--cheat-sheet", default=str(root / "AUDIBLES_CHEAT_SHEET.md"))
    s.add_argument("--profile", default=str(root / "macro_profile.json"))
    s.add_argument("--plan-out", help="write the compiled plan as JSON")
    s.add_argument("--run", action="store_true", help="send real input (Windows, calibrated profile required)")
    s.add_argument("--start-delay", type=float, default=10.0)
    s.add_argument("--delay-scale", type=float, default=1.0, help="multiply all delays (e.g. 1.5 for a slow PC)")
    s.set_defaults(fn=cmd_inject)

    s = sub.add_parser("inspect-saves", help="read-only listing of Madden 27 profile/save files")
    s.set_defaults(fn=cmd_inspect_saves)

    s = sub.add_parser("report", help="write markdown summary report")
    s.add_argument("--playbook", default=DEFAULT_OUT)
    s.add_argument("--out", default=str(Path(DEFAULT_OUT).with_name("REPORT.md")))
    s.add_argument("--offline-note", action="store_true", help="label data as the synthetic offline catalog")
    s.set_defaults(fn=cmd_report)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except ValueError as e:
        console.print(f"[red]{e}[/]")
        return 2


if __name__ == "__main__":
    sys.exit(main())
