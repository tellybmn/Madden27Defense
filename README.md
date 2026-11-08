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

**Status: controls verified from your screenshots; menu behaviour partly inferred.** The key bindings below come from
the on-screen hints. How the selection moves after an action (see "Assumptions") is inferred, so the macro has a
short test mode. Dry runs prove the plan is consistent with the model and the cheat sheet, not that the game behaves
that way. Direct file injection is not implemented (proprietary format, corruption risk, possible conflict with EA's
terms); `python cli.py inspect-saves` is a read-only listing of the Documents/Saved Games Madden folders.

### Verified controls (built-in defaults, `src/calibration.py`)
| Action | Key |
|---|---|
| Tab left / right (AUDIBLES, MY PLAYBOOK, ALL PLAYS, MY GAMEPLAN) | `Z` / `C` |
| Cycle formation group (Nickel, Dime, 3-4, 4-3 ...) | `LCTRL` |
| Open the **SELECT SET** dropdown for the group (2-4, 2-4 Dbl Mug, Over Wide ...); arrows move, `SPACE` selects | `LSHIFT` |
| Remove / activate all plays of the selected set (MY PLAYBOOK) | `E` |
| Audible slots on AUDIBLES: top / left / right / bottom | `Q` / `E` / `Z` / `C` |
| Confirm / back | `SPACE` (bottom bar: `[SPACE] SELECT`) / `BACKSPACE` (avoid `ESC`: it triggers warning prompts) |

Z, C and E repeat across tabs on purpose; duplicate checks are per screen.

### Steps (on the PC, Python 3.11+)
1. `pip install -r requirements.txt pydirectinput`
2. Build the inputs (they must agree; `inject` refuses otherwise):
   `python cli.py build --base vikings --style flores-macdonald --db data/live.db --out data/live_playbook.json`
   `python cli.py export-audibles --playbook data/live_playbook.json --format markdown --out data/AUDIBLES_CHEAT_SHEET.md`
3. `data/macro_profile.json` already ships calibrated with these verified keys. Run `python cli.py calibrate` only to
   change a key or the killswitch (default `pause`, or `f12`). A live run is refused if the profile is uncalibrated or
   has any key marked unverified.
4. `python cli.py inject --plan-out data/macro_plan.json --dry-run`
5. In Madden: add `Nickel 3-3 Swap Dbl Mug` from the Jaguars / Multiple D pool (not automated), open
   **MY PLAYBOOK** with the first formation group and its first set selected.
6. **Test the model first:** `python cli.py inject --run --prune-limit 2`. It removes only the first 2 sets. Check that
   the right two sets were emptied and the selection moved the way the plan expects (the first two removals). If the
   modal behaves differently, stop and report what it shows.
7. Full run: `python cli.py inject --run --delay-scale 1.5` (type `YES`, switch to Madden within 10 s).

### If keys are not registering
- **Run PowerShell as Administrator.** Madden and its anti-cheat run elevated; a non-elevated script cannot send input to an
  elevated window and its keys are silently dropped. `inject --run` warns when the shell is not elevated.
- **Key hold:** each key is sent as `keyDown`, a hold of 0.08 s, then `keyUp`, because the game samples input once per frame
  and drops an instantaneous tap. Raise it with `--hold 0.12` if inputs are still missed.
- **Gap between keys:** every key is followed by a pause of at least 0.15 s times `--delay-scale`; use `--delay-scale 2` for
  slow menu animations.
- Keep the game window focused (the macro aborts if it loses focus), and re-check the canary with `--prune-limit 2`.

### What the macro does
- **Prune (MY PLAYBOOK):** for each of the 23 sets: `LCTRL` to its group; `LSHIFT` opens the SELECT SET dropdown, arrow keys move down/up to
  the set and `SPACE` selects it (skipped when the set is already selected); then the removal sequence
  `E`, 150 ms, `UP`, 100 ms, `SPACE`, 600 ms (the modal needs ~500 ms to fade out and rebuild the list; sending
  keys sooner lands them in the play list). Every `LCTRL` press and the `LSHIFT` that opens the dropdown is followed by 200 ms (arrows 150 ms, the selecting
  `SPACE` 300 ms). Both are enforced minimums,
  so an older saved profile cannot shorten them. `E` opens a "REMOVE PLAY" confirmation whose cursor starts on NO, so `UP`
  moves it to YES and `SPACE` confirms. It plans against a model of the selection state (including that modal), so it
  presses the minimum number of cycles; a plan missing `UP` fails verification because the modal would cancel.
- **Audibles (AUDIBLES):** `Z` once to leave MY PLAYBOOK, then for each kept set: cycle to it, arrow to each play and
  press its slot key. About 205 key presses in total.
- **Safety:** the killswitch aborts between every key, the game must be the foreground window before each key press,
  a live run needs a calibrated profile with no unverified keys and a typed `YES`; only keyboard input is sent.

### Assumptions (printed before a live run; flags in `data/macro_profile.json` under `assume`)
- Start on MY PLAYBOOK with the first group and first set selected.
- `LCTRL` cycles to the next group (forward, wrapping); a new group starts on its first set.
- `LSHIFT` opens a SELECT SET dropdown that starts on the current set (`dropdown_starts_on_current: false` if it starts on
  the first row). Arrow keys move its cursor without wrapping and `SPACE` selects. No other key is sent while it is open.
  `LCTRL` is still assumed to be an instant cycler; if it also opens a dropdown, tell me.
- After `E`, the emptied set leaves the cycle and the selection lands on the next set (`empty_sets_remain: true` if the
  set stays in the cycle instead).
- Switching tabs resets selection to the first group/set (`tab_resets_selection: false` if it is kept).
- Group/set order matches huddle.gg. Yours may differ: list sets top to bottom (`Nickel 2-4 Dbl Mug`, one per line) in a
  text file and pass `--order-file`.
- Plays on AUDIBLES are alphabetical, the cursor starts on the first play and stays after a slot key.
- The added front sits at the end of its group (Nickel).
- With `--base`, audibles are chosen only from plays that already exist in the in-game version of each set.

Use it offline; automation can conflict with EA's terms for online play, and that risk is yours.
