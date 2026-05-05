# Tara Iti Agent-Based Model

An agent-based model (ABM) of the tara iti (New Zealand fairy tern, *Sternula nereis davisae*), one of New Zealand's rarest endemic seabirds. The model simulates population dynamics across breeding seasons, incorporating storm disturbance and predation pressure.

## Overview

The model tracks individual birds through their life stages and breeding attempts over annual cycles. It is designed to explore how storm events and predator activity interact with breeding outcomes to drive population trends in this critically endangered species.

Key processes modelled:
- **Breeding dynamics** – courtship, clutch laying (up to 3 relay attempts per season), incubation, hatching, and chick fledging
- **Storm disturbance** – stochastic storms of varying severity that cause nest abandonment, egg loss, chick mortality, and reduced bird condition
- **Predation** – avian (gulls, kahu/harrier, shorebirds) and mammalian (rats, cats, other mammals) predator incursions that remove eggs and chicks
- **Seasonal mortality** – overwinter survival rates by life stage (chick/juvenile, immature, adult)
- **Energetics** – individual condition scores that influence courtship, nest abandonment thresholds, and survival

## Repository Structure

```
tara_iti_ABM/
├── breeding_storm_predation2.nlogox   # Main NetLogo model (breeding + storm + predation)
├── TI_breeding.nlogo                  # Earlier prototype breeding-only model
├── TI_move_fish.nlogo                 # Prototype movement/foraging model
└── parameters/
    ├── model_params.R                 # R script for deriving model parameters from empirical data
    ├── parameters.Rproj               # RStudio project file
    └── raw_data/
        ├── egg_level_data_2000_2025.csv            # Per-nest egg and hatching records
        └── captures_morphometrics_data_1990_2025.csv  # Individual capture and morphometric records
```

## Model Description

### Agents (turtles)

Each bird is an individual agent with attributes including:

| Attribute | Description |
|---|---|
| `sex` | `"male"` or `"female"` |
| `age_years` / `age_day` | Continuous age |
| `life_stage` | `"chick"`, `"juvenile"`, `"immature"`, or `"adult"` |
| `condition` | Energetic condition (0–1); drives key behavioural decisions |
| `breeding?` | Whether the bird will make a breeding attempt this season |
| `clutch_state` | `"none"`, `"incubating"`, `"failed"`, `"hatched"`, or `"finished"` |
| `clutch_no` | Number of clutches attempted in the current season (max 3) |

### Environment

Patches carry a `habitat_suitability` score used to assign nesting territories. The model runs on a daily time step; one tick equals one day.

### Time

The model starts in mid-April (day 122) in the non-breeding season and advances day by day. Each year spans approximately 365 ticks; the full model run covers 50 years (18 300 ticks). Processes are gated by `season` (`"breeding"` / `"non-breeding"`).

### Key Parameters

**Breeding**

| Slider | Default | Description |
|---|---|---|
| `initial_number` | 50 | Starting number of birds |
| `courting_threshold` | 10 | Days of courtship before pairing |
| `court_success` | 0.75 | Per-day probability of successful pairing |
| `breeding_condition` | 0.80 | Minimum condition to attempt breeding |
| `mean_clutch_no` | 1.68 | Mean number of clutches attempted per season |
| `incubation_cond_loss` | 0.025 | Daily condition loss during incubation |
| `abandon_threshold` | 0.20 | Condition below which a nest is abandoned |
| `hatch_failure` | 0.20 | Per-egg probability of failing to hatch |
| `cooling_off_days` | 10 | Rest days required before a relay attempt |

**Energetics & mortality**

| Slider | Default | Description |
|---|---|---|
| `mean_foraging_gain` | 0.060 | Mean daily condition gain from foraging |
| `mean_metabolic_loss` | 0.060 | Mean daily condition loss |
| `winter_adult_mort` | 0.0004 | Daily overwinter mortality rate – adults |
| `winter_imm_mort` | 0.0003 | Daily overwinter mortality rate – immatures |
| `winter_juv_mort` | 0.0005 | Daily overwinter mortality rate – juveniles |

**Storms**

| Slider | Default | Description |
|---|---|---|
| `storm_prob` | 0.030 | Daily probability of a storm occurring |
| `nest_risk_thresh_small/large/extreme` | 0.50 / 0.60 / 0.95 | Condition loss thresholds per storm severity |
| `nest_loss_small/large/extreme` | 0.15 / 0.20 / 0.50 | Proportion of nests lost per severity level |

**Predation**

| Slider | Default | Description |
|---|---|---|
| `avian_predator_prob` | 0.016 | Daily probability of an avian predator event |
| `mam_predator_prob` | 0.018 | Daily probability of a mammalian predator event |
| `gull/kahu/shorebird_egg_take` | 1.0 / 1.5 / 2.0 | Mean eggs taken per avian predator visit |
| `rat/cat/other_egg_take` | 1.3 / 1.5 / 2.0 | Mean eggs taken per mammalian predator visit |

## Requirements

- [NetLogo](https://ccl.northwestern.edu/netlogo/) ≥ 7.0.0 (the model file targets NetLogo 7.x)
- R ≥ 4.0 with the `tidyverse` package (for `parameters/model_params.R` only)

## Running the Model

### Interactively (NetLogo GUI)

1. Open `breeding_storm_predation2.nlogox` in NetLogo.
2. Adjust sliders on the Interface tab as required.
3. Click **setup** then **go**.

### Headlessly (command line)

NetLogo can be run without a GUI using the bundled `netlogo-headless.sh` script and a BehaviorSpace experiment definition:

```bash
# Create a minimal experiment file (see .github/experiments/default.xml for an example)
netlogo-headless.sh \
  --model breeding_storm_predation2.nlogox \
  --setup-file .github/experiments/default.xml \
  --experiment default \
  --table results.csv
```

## Data

Parameter estimation is handled by `parameters/model_params.R`, which reads:

- `egg_level_data_2000_2025.csv` – nest-level egg and hatch records from the 2000–2025 breeding seasons
- `captures_morphometrics_data_1990_2025.csv` – individual band/resight records with morphometric data (1990–2025)

These datasets are used to derive breeding parameters (e.g., clutch frequencies, breeding ages, sex ratios) and survival estimates.
