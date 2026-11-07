# Custom Defensive Playbook Report

Base: **Minnesota Vikings** | Style: **flores-macdonald** | Formations: **6** | Plays: **153** | Objective: 396.662

> Data source: database contents

## Test results

`89 passed in 0.55s` (exit code 0)

## Constraint checks

| Result | Constraint | Detail |
|---|---|---|
| PASS | C1 formations <= cap | 6/6 |
| PASS | C1 plays <= cap | 153/350 |
| PASS | C2 disguise entropy (nickel/dime/dollar) | all >= 0.45 |
| PASS | C3 heavy (12/21/22) -> 5-front | 3-4 Under |
| PASS | C3 base (11) -> Nickel 2-4 Dbl Mug + Nickel 3-3 Swap Mug | present |
| PASS | C3 spread (10/01) -> Dollar 3-2 / Dime 3-2 variant / Dime 1-4 Dbl Mug | dime-3-2-rush |
| PASS | C4 audible completeness (4 distinct slot plays each) | all formations complete |

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
