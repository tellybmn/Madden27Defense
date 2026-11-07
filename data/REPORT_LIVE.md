# Custom Defensive Playbook Report

Base: **Minnesota Vikings** | Style: **flores-macdonald** | Formations: **6** | Plays: **153** | Objective: 396.662

> Data source: database contents

## Test results

`91 passed in 0.61s` (exit code 0)

## Constraint checks

| Result | Constraint | Detail |
|---|---|---|
| PASS | T-active formations <= cap | 6/6 |
| PASS | T-active rotation plays <= cap | 153/350 |
| PASS | G-engine plays per front <= 75 | largest: Nickel 2-4 (42) |
| PASS | G-engine total personnel <= 15 | 9 base + 0 added = 9 |
| PASS | G-engine total fronts <= 73 | 41 base + 1 added = 42 |
| PASS | G-engine total plays <= 750 | 475 base + 24 added = 499 |
| PASS | C2 disguise entropy (nickel/dime/dollar) | all >= 0.45 |
| PASS | C3 heavy (12/21/22) -> 5-front | 3-4 Under |
| PASS | C3 base (11) -> Nickel 2-4 Dbl Mug + Nickel 3-3 Swap Mug | present |
| PASS | C3 spread (10/01) -> Dollar 3-2 / Dime 3-2 variant / Dime 1-4 Dbl Mug | dime-3-2-rush |
| PASS | C4 audible completeness (4 distinct slot plays each) | all formations complete |

## Constraint hierarchy

Two tiers are enforced. **Tier 1 (Madden engine caps)** bounds the whole custom playbook; **Tier 2 (tactical active set)** is the small in-game menu this optimizer selects.

| Tier | Limit | Value | Result |
|---|---|---|---|
| 1 Engine | Personnel | <= 15 | 9 (base 9 + 0) |
| 1 Engine | Fronts | <= 73 | 42 (base 41 + 1; 32 slots available) |
| 1 Engine | Total plays | <= 750 | 499 (base 475 + 24; 275 available) |
| 1 Engine | Plays per front | <= 75 | largest 42 |
| 2 Tactical | Active formations | <= 6 | 6 |
| 2 Tactical | Active rotation plays | <= 350 | 153 |
| 2 Tactical | Plays per formation | <= 75 | all pass |

Totals assume the **entire** Minnesota Vikings base playbook is kept and the hybrid additions are layered on (worst case). Base counts (9 personnel / 41 fronts / 475 plays) are user-supplied in-game numbers; the huddle.gg scrape lists 28 Minnesota Vikings fronts, so retained/pruned below are relative to those.

### Base playbook mapping (Minnesota Vikings)

| Status | Front | Plays | Source |
|---|---|---|---|
| Retained (active) | 3-4 Under | 19 | Minnesota Vikings base |
| Retained (active) | Dime 2-3 | 37 | Minnesota Vikings base |
| Retained (active) | Dime 3-2 Rush | 21 | Minnesota Vikings base |
| Retained (active) | Nickel 2-4 | 42 | Minnesota Vikings base |
| Retained (active) | Nickel 2-4 Dbl Mug | 16 | Minnesota Vikings base |
| Added (hybrid) | Nickel 3-3 Swap Dbl Mug | 18 | Jacksonville Jaguars, Multiple D |

**Pruned from the active set (23 scraped base fronts, still within the engine cap if kept):** 2-4-5 Over Wide, 3-3-5 3 High Penny, 3-4 Even, 3-4 Over, 3-4 Over Ed, 3-4 Over Solid, 3-4 Tite 5 Tech, 4-2-5 3 High, 4-3 Even 6-1, 4-3 Odd Leo, Dime 1-4, Dime 1-4 Dbl Mug, Dime 2-3 Single Mug, Goal Line 5-3, Goal Line 6-2, Goal Line Pinch, Nickel 2-4 Load Dbl Mug, Nickel 2-4 Load Mug, Nickel 2-4 Single Mug, Nickel 2-4 Swap Dbl Mug, Nickel 2-4 Wide, Nickel 3-3 Odd, Prevent 3 Deep

Hybrid additions use 1 of the 32 remaining front slots and 24 of the 275 remaining play slots.

## Selected formations

| Formation | Set | Personnel | Plays | Disguise entropy | Source playbooks |
|---|---|---|---|---|---|
| 3-4 Under | Base | 12/21/22 | 19 | 0.303 | Baltimore Ravens, Jacksonville Jaguars, Miami Dolphins, Minnesota Vikings, Seattle Seahawks |
| Dime 2-3 | Dime | 10/01 | 37 | 0.588 | Baltimore Ravens, Minnesota Vikings, Seattle Seahawks |
| Dime 3-2 Rush | Dime | 10/01 | 21 | 0.527 | Minnesota Vikings, Seattle Seahawks |
| Nickel 2-4 | Nickel | 11 | 42 | 0.613 | Baltimore Ravens, Minnesota Vikings, Seattle Seahawks |
| Nickel 2-4 Dbl Mug | Nickel | 11 | 16 | 0.802 | Baltimore Ravens, Minnesota Vikings, Seattle Seahawks |
| Nickel 3-3 Swap Dbl Mug | Nickel | 11 | 18 | 0.818 | Jacksonville Jaguars, Multiple D |

## Audible matrices (4 plays per formation)

### 3-4 Under

| Slot | Button (suggested) | Audible type | Play | Fills as |
|---|---|---|---|---|
| 1 | Y / Triangle | Man / all-out pressure (Cover 0 blitz or Cover 1 Hole / man blitz) | SAW BLITZ 1 | Cover 1 man blitz |
| 2 | X / Square | Creeper / sim pressure (4-man sim, Fire 3, Coffee House 3) | FS FIRE 3 | creeper alias (Fire N / Coffee House) |
| 3 | B / Circle | 2-high / disguise zone (Tampa 2, Cover 2 Invert, Cover 3 Cloud) | 2 INVERT HARD FLAT | Tampa 2 / Cover 2 family |
| 4 | A / Cross | Match / base check (Cover 4/6/9, Cover 3 Match, 2 Invert fallback) | COVER 4 QUARTERS | Cover 4 / Cover 6 / Cover 9 match |

### Dime 2-3

| Slot | Button (suggested) | Audible type | Play | Fills as |
|---|---|---|---|---|
| 1 | Y / Triangle | Man / all-out pressure (Cover 0 blitz or Cover 1 Hole / man blitz) | EDGE BLITZ 0 | Cover 0 blitz |
| 2 | X / Square | Creeper / sim pressure (4-man sim, Fire 3, Coffee House 3) | FIELD SIM 3 | 4-man sim pressure |
| 3 | B / Circle | 2-high / disguise zone (Tampa 2, Cover 2 Invert, Cover 3 Cloud) | COVER 2 INVERT | Tampa 2 / Cover 2 family |
| 4 | A / Cross | Match / base check (Cover 4/6/9, Cover 3 Match, 2 Invert fallback) | COVER 4 PALMS | Cover 4 / Cover 6 / Cover 9 match |

### Dime 3-2 Rush

| Slot | Button (suggested) | Audible type | Play | Fills as |
|---|---|---|---|---|
| 1 | Y / Triangle | Man / all-out pressure (Cover 0 blitz or Cover 1 Hole / man blitz) | COVER 1 CONTAIN SPY | Cover 1 man (no added rusher) |
| 2 | X / Square | Creeper / sim pressure (4-man sim, Fire 3, Coffee House 3) | MUG SIM PRESSURE | 4-man sim pressure |
| 3 | B / Circle | 2-high / disguise zone (Tampa 2, Cover 2 Invert, Cover 3 Cloud) | COVER 2 HARD FLAT | Tampa 2 / Cover 2 family |
| 4 | A / Cross | Match / base check (Cover 4/6/9, Cover 3 Match, 2 Invert fallback) | COVER 4 PALMS | Cover 4 / Cover 6 / Cover 9 match |

### Nickel 2-4

| Slot | Button (suggested) | Audible type | Play | Fills as |
|---|---|---|---|---|
| 1 | Y / Triangle | Man / all-out pressure (Cover 0 blitz or Cover 1 Hole / man blitz) | EDGE BLITZ 0 | Cover 0 blitz |
| 2 | X / Square | Creeper / sim pressure (4-man sim, Fire 3, Coffee House 3) | CROSS SIM 2 | 4-man sim pressure |
| 3 | B / Circle | 2-high / disguise zone (Tampa 2, Cover 2 Invert, Cover 3 Cloud) | 2 INVERT LURK | Tampa 2 / Cover 2 family |
| 4 | A / Cross | Match / base check (Cover 4/6/9, Cover 3 Match, 2 Invert fallback) | COVER 4 DROP FIELD | Cover 4 / Cover 6 / Cover 9 match |

### Nickel 2-4 Dbl Mug

| Slot | Button (suggested) | Audible type | Play | Fills as |
|---|---|---|---|---|
| 1 | Y / Triangle | Man / all-out pressure (Cover 0 blitz or Cover 1 Hole / man blitz) | MID BLITZ 0 | Cover 0 blitz |
| 2 | X / Square | Creeper / sim pressure (4-man sim, Fire 3, Coffee House 3) | FIELD SIM 3 | 4-man sim pressure |
| 3 | B / Circle | 2-high / disguise zone (Tampa 2, Cover 2 Invert, Cover 3 Cloud) | NICKEL 2 TRAP | Tampa 2 / Cover 2 family |
| 4 | A / Cross | Match / base check (Cover 4/6/9, Cover 3 Match, 2 Invert fallback) | COVER 2 INVERT | fallback: 2 Invert |

### Nickel 3-3 Swap Dbl Mug

| Slot | Button (suggested) | Audible type | Play | Fills as |
|---|---|---|---|---|
| 1 | Y / Triangle | Man / all-out pressure (Cover 0 blitz or Cover 1 Hole / man blitz) | BLITZ LOOP 0 | Cover 0 blitz |
| 2 | X / Square | Creeper / sim pressure (4-man sim, Fire 3, Coffee House 3) | CB BENCH SIM 2 | 4-man sim pressure |
| 3 | B / Circle | 2-high / disguise zone (Tampa 2, Cover 2 Invert, Cover 3 Cloud) | NICKEL 2 TRAP | Tampa 2 / Cover 2 family |
| 4 | A / Cross | Match / base check (Cover 4/6/9, Cover 3 Match, 2 Invert fallback) | COVER 3 MATCH | Cover 3 Match |
