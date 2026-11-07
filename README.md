# Madden27Defense

ETL + optimizer that builds a custom "Flores / Macdonald / Campanile" hybrid defensive playbook.

```
pip install -r requirements.txt
python cli.py test                                   # offline tests, network blocked by conftest
python cli.py scrape --offline --teams vikings,seahawks,jaguars,ravens,dolphins,multiple-d
python cli.py build --base vikings --style flores-macdonald   # styles: flores-macdonald | campanile | hybrid
python cli.py export-audibles
python cli.py report --offline-note                  # writes data/REPORT.md
python cli.py scrape --teams vikings,seahawks,jaguars,ravens  # live (rate limited); --playwright for JS pages
```

| File | Role |
|---|---|
| `schema.sql`, `src/database.py` | normalized SQLite (WAL, FKs, UNIQUE keys -> idempotent upserts) |
| `src/parser.py` | HTML extraction, slugify, rule-based play/formation classifier |
| `src/scraper.py` | httpx loader (rate limit, exp. backoff + jitter, UA rotation), mock loader, Playwright fallback |
| `src/optimizer.py` | isomorphism clustering + exact constrained knapsack / set-cover search |
| `src/offline_data.py` | synthetic DOM + **synthetic** play catalog for `--offline` |
| `src/cli.py` (root `cli.py` is a shim) | `test`, `scrape`, `build`, `export-audibles` |

Caveats: live-site selectors are modeled, not verified against huddle.gg / madden.tools; the offline
catalog is illustrative, not real playbook data; the audible button layout is a suggested default.

## Constraint hierarchy

| Tier | Meaning | Limits (`src/optimizer.py`) |
|---|---|---|
| 1. Engine caps | What Madden's custom-playbook editor allows in total | `MAX_TOTAL_PERSONNEL=15`, `MAX_TOTAL_FRONTS=73`, `MAX_TOTAL_PLAYS=750`, `MAX_PLAYS_PER_FRONT=75` |
| 2. Tactical active set | The small in-game menu the optimizer selects | `ACTIVE_MAX_FORMATIONS=6`, `ACTIVE_MAX_PLAYS=350`, each formation <= 75 plays |

The base-playbook foundation (`FOUNDATIONS`; Vikings = 9 personnel / 41 fronts / 475 plays, leaving 6 / 32 / 275)
consists of user-supplied in-game counts, not scraped values. Tier 1 is checked on the worst case where the whole
base playbook is kept and the hybrid fronts and plays are layered on. `data/REPORT_LIVE.md` shows which base fronts are
retained, which hybrid fronts are added and which are pruned from the active set. The scrape lists 28 Vikings fronts
and 436 plays, which differs from the 41/475 foundation.

## Applying the playbook to Madden 27 on PC

**Status: the plan generator is verified; the in-game behaviour is not.** The macro was built in a Linux container
with no game, so the menu model below could not be checked against the real Creation Center. Dry runs prove the plan is
internally consistent (it is replayed against the model and must reproduce `AUDIBLES_CHEAT_SHEET.md` exactly), not that
Madden behaves that way. Test on a copy of your playbook first.

**Direct file injection is not implemented** (proprietary format, corruption risk, possible conflict with EA's terms and
anti-cheat). `python cli.py inspect-saves` is a read-only listing of `Documents\Madden NFL 27\settings`,
`Saved Games\Madden NFL 27` (and OneDrive-redirected Documents) with extension, size and a plaintext/JSON/binary guess.

### Steps (on the PC, Python 3.11+)
1. `pip install -r requirements.txt pydirectinput`
2. Build the inputs (they must agree; `inject` refuses otherwise):
   `python cli.py build --base vikings --style flores-macdonald --db data/live.db --out data/live_playbook.json`
   `python cli.py export-audibles --playbook data/live_playbook.json --format markdown --out data/AUDIBLES_CHEAT_SHEET.md`
3. `python cli.py calibrate`: press each requested key (confirm, back, 4 directions, tab left/right, delete, assign
   audible, the 4 audible-slot face-button keys), then pick a killswitch (default `pause`; avoid ESC if the game uses it
   to back out). This writes `data/macro_profile.json` with `calibrated: true`.
4. `python cli.py inject --plan-out data/macro_plan.json --dry-run`: builds the zero-prompt plan and checks it against the cheat sheet.
5. In Madden (borderless windowed): add `Nickel 3-3 Swap Dbl Mug` from the Jaguars / Multiple D pool (the one step not
   automated), open the defensive formation list with the cursor on the **first** row, then
   `python cli.py inject --run` (type `YES`, click into the game within 10 s; `--delay-scale 1.5` for a slow PC).

### What the macro does (the model it assumes)
- Prune: formations are walked top to bottom; moving to a row = N x NAV_DOWN; each delete is `DELETE, wait 200ms, CONFIRM, wait 300ms`
  and the cursor rests on the row that slid up. Positions come from the huddle.gg list order; if your in-game list
  differs (you reported 41 fronts vs 28 scraped), write the names top-to-bottom in a text file and pass `--order-file`.
- Audibles: per kept formation, CONFIRM to enter, then for each slot scroll the alphabetical play list by relative
  index, press ASSIGN_AUDIBLE, then the slot key (1 top/Y, 2 left/X, 3 right/B, 4 bottom/A), then BACK.
- Safety: the killswitch aborts between every step, the game must be the foreground window before every key press, a live
  run needs a calibrated profile and a typed YES, and only keyboard input is sent.
- Optimizer note: with `--base`, audibles are chosen only from plays that exist in the in-game version of each front, so
  the macro never has to add plays.

Use it offline; automation can conflict with EA's terms for online play, and that risk is yours.
