# Tara Iti Agent-Based Model

[![Run NetLogo model](https://github.com/UoA-eResearch/tara_iti_ABM/actions/workflows/run-model.yml/badge.svg)](https://github.com/UoA-eResearch/tara_iti_ABM/actions/workflows/run-model.yml)

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
├── parameters/
│   ├── model_params.R                 # R script for deriving model parameters from empirical data
│   ├── parameters.Rproj               # RStudio project file
│   └── raw_data/
│       ├── egg_level_data_2000_2025.csv            # Per-nest egg and hatching records
│       └── captures_morphometrics_data_1990_2025.csv  # Individual capture and morphometric records
└── .github/
    ├── workflows/
    │   └── run-model.yml              # CI workflow: headless run + ABC calibration
    ├── experiments/
    │   └── default.xml                # Reference BehaviorSpace experiment (NetLogo 7 format)
    └── abc/
        └── abc_runner.py              # ABC rejection-sampling calibration script
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
- Python ≥ 3.9 (for `abc_runner.py`; uses only the standard library)

## Running the Model

### Interactively (NetLogo GUI)

1. Open `breeding_storm_predation2.nlogox` in NetLogo.
2. Adjust sliders on the Interface tab as required.
3. Click **setup** then **go**.

### Headlessly (command line)

NetLogo can be run without a GUI using the bundled `netlogo-headless.sh` script. The `default` BehaviorSpace experiment is embedded directly in the model file (NetLogo 7 reads experiments from the model, not from a separate setup file):

```bash
/path/to/NetLogo-7.0.4-64/netlogo-headless.sh \
  --model breeding_storm_predation2.nlogox \
  --experiment default \
  --table results.csv
```

`results.csv` will contain one row per run (final metrics only, since `runMetricsEveryStep="false"`) with columns `total_birds`, `fledged`, and `total_eggs`.

## Continuous Integration

Every push and pull request triggers the `.github/workflows/run-model.yml` workflow, which:

1. **Installs Java 21** (Temurin) and **downloads NetLogo 7.0.4** (cached between runs).
2. **Runs a 365-tick headless simulation** using the embedded `default` BehaviorSpace experiment and uploads `results.csv` as the `simulation-results` artifact.
3. **Runs ABC calibration** (see below) and uploads `abc_all.csv` and `abc_accepted.csv` as the `abc-results` artifact.

## ABC Parameter Calibration

`abc_runner.py` uses **ABC rejection sampling** with **Latin Hypercube Sampling (LHS)** to calibrate the model against field-observed breeding outcomes.

### What it does

1. Draws 300 parameter sets from uniform priors using LHS. LHS divides each parameter's range into 300 equal strata and samples one point per stratum, giving much better prior coverage than pure random sampling across 49 parameters.
2. For each parameter set (run in parallel across all available CPU cores):
   - Injects a BehaviorSpace experiment into a temporary copy of the model.
   - Runs NetLogo headlessly for 365 ticks.
   - Computes a normalised Euclidean distance between the simulated summary statistics and field-observed targets:

     | Summary statistic | Field target | Normalisation SD |
     |---|---|---|
     | `fledge_rate` (fledglings ÷ eggs) | 0.307 | 0.15 |
     | `eggs_per_50` (eggs ÷ initial birds) | 0.458 | 0.20 |

     Both targets are derived from `parameters/raw_data/egg_level_data_2000_2025.csv` (seasons 2000–2025, n = 25).

3. Accepts the top 20% of runs (lowest distance) as the approximate posterior.

### Parameters calibrated

All 49 modifiable sliders are varied (only `initial_number` is fixed at 50):

| Group | Parameters |
|---|---|
| Breeding | `patch_threshold`, `courting_threshold`, `court_success`, `breeding_condition`, `mean_clutch_no`, `incubation_cond_loss`, `abandon_threshold`, `hatch_failure`, `with_chick_cond_loss`, `cooling_off_days`, `courting_condition`, `candle_success` |
| Energetics | `mean_foraging_gain`, `sd_foraging_gain`, `mean_metabolic_loss`, `sd_metabolic_loss`, `mean_breeding_prep`, `sd_breeding_prep`, `chick_health`, `juv_cond_loss` |
| Mortality | `winter_adult_mort`, `winter_imm_mort`, `winter_juv_mort`, `winter_elder_mort` |
| Storms | `storm_prob`, `nest_risk_thresh_small/large/extreme`, `nest_loss_small/large/extreme`, `small/large/extreme_cond_loss` |
| Predation | `avian_predator_prob`, `mam_predator_prob`, `sibling_attack`, `gull/kahu/shorebird_egg_take`, `gull/kahu/shorebird_chick_take`, `rat/cat/other_egg_take`, `rat/cat/other_chick_take` |

### Running ABC manually

```bash
# Default: 300 LHS samples, 20% acceptance, 4 workers, seed 42
python3 .github/abc/abc_runner.py

# Custom settings via environment variables
NETLOGO_SCRIPT=/path/to/netlogo-headless.sh \
MODEL_FILE=breeding_storm_predation2.nlogox \
ABC_N_SAMPLES=100 \
ABC_N_WORKERS=8 \
ABC_ACCEPT_FRACTION=0.10 \
ABC_SEED=123 \
  python3 .github/abc/abc_runner.py
```

| Variable | Default | Description |
|---|---|---|
| `NETLOGO_SCRIPT` | `./NetLogo-7.0.4-64/netlogo-headless.sh` | Path to NetLogo headless launcher |
| `MODEL_FILE` | `breeding_storm_predation2.nlogox` | Path to model file |
| `ABC_N_SAMPLES` | `300` | Number of LHS samples to draw |
| `ABC_N_WORKERS` | CPU count | Parallel worker threads |
| `ABC_ACCEPT_FRACTION` | `0.20` | Top fraction accepted as posterior |
| `ABC_SEED` | `42` | Random seed for reproducibility |

### Output files

| File | Contents |
|---|---|
| `abc_all.csv` | All successful runs: parameter values, simulated summary stats (`fledge_rate`, `eggs_per_50`, `total_birds`, `fledged`, `total_eggs`), and `distance` |
| `abc_accepted.csv` | Accepted runs only (top `ACCEPT_FRACTION` by distance) — the approximate posterior |

The posterior parameter ranges printed to stdout identify which combinations of parameters are most consistent with observed breeding outcomes.

## Data

Parameter estimation is handled by `parameters/model_params.R`, which reads:

- `egg_level_data_2000_2025.csv` – nest-level egg and hatch records from the 2000–2025 breeding seasons
- `captures_morphometrics_data_1990_2025.csv` – individual band/resight records with morphometric data (1990–2025)

These datasets are used to derive breeding parameters (e.g., clutch frequencies, breeding ages, sex ratios) and survival estimates.
