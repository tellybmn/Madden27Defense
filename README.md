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
