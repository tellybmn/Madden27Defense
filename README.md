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
