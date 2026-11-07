# Custom Defensive Playbook Report

Base: **Minnesota Vikings** | Style: **flores-macdonald** | Formations: **6** | Plays: **217** | Objective: 552.773

> Data source: bundled synthetic catalog

## Test results

`77 passed in 0.39s` (exit code 0)

## Constraint checks

| Result | Constraint | Detail |
|---|---|---|
| PASS | C1 formations <= cap | 6/6 |
| PASS | C1 plays <= cap | 217/350 |
| PASS | C2 disguise entropy (nickel/dime/dollar) | all >= 0.45 |
| PASS | C3 heavy (12/21/22) -> 5-front | 3-4 Bear, 4-3 Even 6-1 |
| PASS | C3 base (11) -> Nickel 2-4 Dbl Mug + Nickel 3-3 Swap Mug | present |
| PASS | C3 spread (10/01) -> Dollar 3-2 or Dime 1-4 Dbl Mug | dollar-3-2, dime-1-4-dbl-mug |
| PASS | C4 audible completeness (4 play-types each) | all formations complete |

## Selected formations

| Formation | Set | Personnel | Plays | Disguise entropy | Source playbooks |
|---|---|---|---|---|---|
| 3-4 Bear | Base | 12/21/22 | 38 | 0.397 | Baltimore Ravens, Miami Dolphins, Multiple D, Seattle Seahawks |
| 4-3 Even 6-1 | Base | 12/21/22 | 32 | 0.395 | Miami Dolphins, Minnesota Vikings |
| Dime 1-4 Dbl Mug | Dime | 10/01 | 38 | 0.993 | Baltimore Ravens, Miami Dolphins, Minnesota Vikings |
| Dollar 3-2 | Dollar | 10/01 | 38 | 0.645 | Multiple D, Seattle Seahawks |
| Nickel 2-4 Dbl Mug | Nickel | 11 | 38 | 0.993 | Baltimore Ravens, Miami Dolphins, Minnesota Vikings, Seattle Seahawks |
| Nickel 3-3 Swap Mug | Nickel | 11 | 33 | 0.985 | Baltimore Ravens, Jacksonville Jaguars |

## Audible matrices (4 plays per formation)

### 3-4 Bear

| Slot | Button (suggested) | Audible type | Play |
|---|---|---|---|
| 1 | Y / Triangle | All-out man pressure (Cover 0 / cross-dog) | Cover 0 Blitz |
| 2 | X / Square | Creeper / sim pressure (4 rush, zone drop) | Creeper Cover 3 Sky |
| 3 | B / Circle | Disguised 2-high / invert (Tampa 2, Cover 2 Invert) | Cover 2 Hard Flat |
| 4 | A / Cross | Split-field match (Cover 4 Palms / Quarters / Cover 6) | Cover 4 Match |

### 4-3 Even 6-1

| Slot | Button (suggested) | Audible type | Play |
|---|---|---|---|
| 1 | Y / Triangle | All-out man pressure (Cover 0 / cross-dog) | Cover 0 Blitz |
| 2 | X / Square | Creeper / sim pressure (4 rush, zone drop) | Dime Dog 3 Sky |
| 3 | B / Circle | Disguised 2-high / invert (Tampa 2, Cover 2 Invert) | Cover 2 Hard Flat |
| 4 | A / Cross | Split-field match (Cover 4 Palms / Quarters / Cover 6) | Cover 4 Quarters |

### Dime 1-4 Dbl Mug

| Slot | Button (suggested) | Audible type | Play |
|---|---|---|---|
| 1 | Y / Triangle | All-out man pressure (Cover 0 / cross-dog) | Cross Dog 0 |
| 2 | X / Square | Creeper / sim pressure (4 rush, zone drop) | Creeper Cover 3 Sky |
| 3 | B / Circle | Disguised 2-high / invert (Tampa 2, Cover 2 Invert) | Cover 2 Hard Flat |
| 4 | A / Cross | Split-field match (Cover 4 Palms / Quarters / Cover 6) | Cover 4 Match |

### Dollar 3-2

| Slot | Button (suggested) | Audible type | Play |
|---|---|---|---|
| 1 | Y / Triangle | All-out man pressure (Cover 0 / cross-dog) | Cover 0 Blitz |
| 2 | X / Square | Creeper / sim pressure (4 rush, zone drop) | Creeper Cover 3 Sky |
| 3 | B / Circle | Disguised 2-high / invert (Tampa 2, Cover 2 Invert) | Cover 2 Hard Flat |
| 4 | A / Cross | Split-field match (Cover 4 Palms / Quarters / Cover 6) | Cover 4 Match |

### Nickel 2-4 Dbl Mug

| Slot | Button (suggested) | Audible type | Play |
|---|---|---|---|
| 1 | Y / Triangle | All-out man pressure (Cover 0 / cross-dog) | Cover 0 Blitz |
| 2 | X / Square | Creeper / sim pressure (4 rush, zone drop) | Creeper Cover 3 Sky |
| 3 | B / Circle | Disguised 2-high / invert (Tampa 2, Cover 2 Invert) | Cover 2 Invert |
| 4 | A / Cross | Split-field match (Cover 4 Palms / Quarters / Cover 6) | Cover 4 Match |

### Nickel 3-3 Swap Mug

| Slot | Button (suggested) | Audible type | Play |
|---|---|---|---|
| 1 | Y / Triangle | All-out man pressure (Cover 0 / cross-dog) | Cover 0 Blitz |
| 2 | X / Square | Creeper / sim pressure (4 rush, zone drop) | Creeper Cover 3 Sky |
| 3 | B / Circle | Disguised 2-high / invert (Tampa 2, Cover 2 Invert) | Cover 2 Hard Flat |
| 4 | A / Cross | Split-field match (Cover 4 Palms / Quarters / Cover 6) | Cover 4 Match |
