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

**Status: the macro is dry-run verified only.** It was built in a Linux container with no game and no Windows, so the
menu key sequences and list positions could not be checked. The live run therefore refuses to start until you
calibrate `data/macro_profile.json` (`"calibrated": true`).

**Direct file injection is not implemented.** Madden's profile/playbook format is proprietary and undocumented, a bad
write can corrupt a profile, and modifying game data may conflict with EA's terms and anti-cheat.
`python cli.py inspect-saves` is a read-only listing of `Documents\Madden NFL 27` if you want that route investigated.

### Steps (on the PC, Python 3.11+)
1. `pip install -r requirements.txt pydirectinput`
2. Rebuild so the inputs agree: `python cli.py build --base vikings --style flores-macdonald --db data/live.db --out data/live_playbook.json`
   then `python cli.py export-audibles --playbook data/live_playbook.json --format markdown --out data/AUDIBLES_CHEAT_SHEET.md`.
   (`inject` refuses to run if the cheat sheet and JSON disagree.)
3. Calibrate `data/macro_profile.json` (set once for your build/controls):
   `keys`/`button_keys` (the key bound to each in-game button), `sequences` (key lists for opening the editor, deleting a
   formation, adding a formation, binding an audible; items are key names or `wait:SECONDS`), and optionally
   `formation_index` / `play_index` (list positions) for fully automatic navigation.
   Anything without a position becomes an **assist prompt**: you put the cursor on the item, press ENTER in the console,
   and the macro does the repetitive part.
4. Dry run (sends nothing): `python cli.py inject --plan-out data/macro_plan.json` and review the plan.
5. Live: start Madden in borderless/windowed mode, open the Creation Center playbook editor, then
   `python cli.py inject --run --start-delay 10` and click into the game. Slow PC? add `--delay-scale 1.5`.

Safety: **ESC aborts** between every step (set `killswitch` in the profile), focus on the game window is asserted
before every key press, and only keyboard input is sent (no game memory or files are touched). Use it offline;
automation tools can conflict with EA's terms for online play, and that risk is yours.
