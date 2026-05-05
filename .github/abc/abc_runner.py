#!/usr/bin/env python3
"""
Approximate Bayesian Computation (ABC) for calibrating the tara iti ABM.

Algorithm (ABC rejection sampling with Latin Hypercube Sampling):
  1. Draw N_SAMPLES parameter sets from uniform priors using Latin Hypercube
     Sampling (LHS) for better coverage across the high-dimensional space.
  2. For each parameter set (in parallel across N_WORKERS threads):
     a. Inject a BehaviorSpace experiment into a temporary copy of the model.
     b. Run NetLogo headlessly for 365 ticks (one simulated year).
     c. Parse the BehaviorSpace table CSV.
     d. Compute a normalised Euclidean distance to field-observed summary stats.
  3. Accept the top ACCEPT_FRACTION of successful runs as the ABC posterior.

Output files (written to the working directory):
  abc_all.csv      – all successful runs (parameters, summary stats, distance)
  abc_accepted.csv – accepted runs (top ACCEPT_FRACTION by distance)

Environment variables (all optional):
  NETLOGO_SCRIPT      path to netlogo-headless.sh  (default: ./NetLogo-7.0.4-64/netlogo-headless.sh)
  MODEL_FILE          path to .nlogox model file    (default: breeding_storm_predation2.nlogox)
  ABC_N_SAMPLES       number of LHS samples         (default: 300)
  ABC_N_WORKERS       parallel worker threads       (default: CPU count)
  ABC_ACCEPT_FRACTION fraction to accept            (default: 0.20)
  ABC_SEED            random seed                   (default: 42)
"""

from __future__ import annotations

import concurrent.futures
import csv
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

# ── Configuration ─────────────────────────────────────────────────────────────

NETLOGO_SCRIPT  = os.environ.get("NETLOGO_SCRIPT",      "./NetLogo-7.0.4-64/netlogo-headless.sh")
MODEL_FILE      = os.environ.get("MODEL_FILE",           "breeding_storm_predation2.nlogox")
N_SAMPLES       = int(os.environ.get("ABC_N_SAMPLES",   "300"))
N_WORKERS       = int(os.environ.get("ABC_N_WORKERS",   str(os.cpu_count() or 4)))
ACCEPT_FRACTION = float(os.environ.get("ABC_ACCEPT_FRACTION", "0.20"))
RANDOM_SEED     = int(os.environ.get("ABC_SEED",        "42"))

# Timeout for a single NetLogo run in seconds
NETLOGO_TIMEOUT_SEC = 300

# ── Prior distributions (uniform [low, high]) ─────────────────────────────────
# All modifiable slider parameters from breeding_storm_predation2.nlogox.
# Ranges are ecologically informed: centred on the interface defaults with
# ±50–200 % variation depending on the degree of empirical uncertainty.
# 'initial_number' is excluded – it is an initial condition, not a process
# parameter, and is fixed at 50 to match the observed population baseline.

PRIORS: dict[str, tuple[float, float]] = {
    # ── Breeding ──────────────────────────────────────────────────────────────
    "patch_threshold":        (0.05, 0.50),   # habitat quality threshold for nesting
    "courting_threshold":     (5.0,  20.0),   # days of courtship before pairing
    "court_success":          (0.30, 1.00),   # daily probability of successful pairing
    "breeding_condition":     (0.50, 0.95),   # minimum condition score to attempt breeding
    "mean_clutch_no":         (1.00, 3.00),   # mean clutches attempted per season
    "incubation_cond_loss":   (0.01, 0.06),   # daily condition loss during incubation
    "abandon_threshold":      (0.05, 0.40),   # condition below which nest abandoned
    "hatch_failure":          (0.05, 0.60),   # per-egg probability of failing to hatch
    "with_chick_cond_loss":   (0.001, 0.02),  # daily condition loss while brooding
    "cooling_off_days":       (3.0,  20.0),   # rest days required before relay attempt
    "courting_condition":     (0.30, 0.80),   # minimum condition to begin courtship
    "candle_success":         (0.50, 1.00),   # probability of successful candling detection
    # ── Energetics & mortality ────────────────────────────────────────────────
    "mean_foraging_gain":     (0.03, 0.12),   # mean daily condition gain from foraging
    "sd_foraging_gain":       (0.002, 0.02),  # SD of daily foraging gain
    "mean_metabolic_loss":    (0.03, 0.12),   # mean daily metabolic condition loss
    "sd_metabolic_loss":      (0.002, 0.02),  # SD of daily metabolic loss
    "mean_breeding_prep":     (0.04, 0.15),   # mean daily condition gain in pre-breeding
    "sd_breeding_prep":       (0.01, 0.07),   # SD of pre-breeding gain
    "chick_health":           (0.001, 0.008), # daily condition gain rate for chicks
    "juv_cond_loss":          (0.05, 0.25),   # daily condition loss for juveniles
    "winter_adult_mort":      (1e-4, 2e-3),   # daily overwinter mortality – adults
    "winter_imm_mort":        (1e-4, 2e-3),   # daily overwinter mortality – immatures
    "winter_juv_mort":        (1e-4, 3e-3),   # daily overwinter mortality – juveniles
    "winter_elder_mort":      (1e-4, 5e-3),   # daily overwinter mortality – elders
    # ── Storms ────────────────────────────────────────────────────────────────
    "storm_prob":             (0.005, 0.10),  # daily probability of a storm
    "nest_risk_thresh_small": (0.20, 0.80),   # condition-loss threshold, small storm
    "nest_risk_thresh_large": (0.30, 0.90),   # condition-loss threshold, large storm
    "nest_risk_thresh_extreme":(0.70, 1.00),  # condition-loss threshold, extreme storm
    "nest_loss_small":        (0.03, 0.40),   # fraction of nests lost, small storm
    "nest_loss_large":        (0.05, 0.50),   # fraction of nests lost, large storm
    "nest_loss_extreme":      (0.20, 0.90),   # fraction of nests lost, extreme storm
    "small_cond_loss":        (0.001, 0.01),  # condition loss per bird, small storm
    "large_cond_loss":        (0.003, 0.02),  # condition loss per bird, large storm
    "extreme_cond_loss":      (0.005, 0.03),  # condition loss per bird, extreme storm
    # ── Predation ─────────────────────────────────────────────────────────────
    "avian_predator_prob":    (0.005, 0.05),  # daily probability of avian predator event
    "mam_predator_prob":      (0.005, 0.05),  # daily probability of mammalian predator event
    "sibling_attack":         (0.30, 1.00),   # probability of sibling aggression
    "gull_egg_take":          (0.50, 3.00),   # mean eggs taken per gull visit
    "kahu_egg_take":          (0.50, 4.00),   # mean eggs taken per harrier visit
    "shorebird_egg_take":     (0.50, 4.00),   # mean eggs taken per shorebird visit
    "gull_chick_take":        (0.50, 3.00),   # mean chicks taken per gull visit
    "kahu_chick_take":        (0.50, 4.00),   # mean chicks taken per harrier visit
    "shorebird_chick_take":   (0.50, 3.00),   # mean chicks taken per shorebird visit
    "rat_egg_take":           (0.50, 3.00),   # mean eggs taken per rat event
    "cat_egg_take":           (0.50, 4.00),   # mean eggs taken per cat event
    "other_egg_take":         (0.50, 4.00),   # mean eggs taken per other mammal event
    "rat_chick_take":         (0.50, 3.00),   # mean chicks taken per rat event
    "cat_chick_take":         (0.50, 4.00),   # mean chicks taken per cat event
    "other_chick_take":       (0.50, 4.00),   # mean chicks taken per other mammal event
}

# ── Observed summary statistics (field data 2000–2025) ────────────────────────
# Derived from parameters/raw_data/egg_level_data_2000_2025.csv:
#   mean seasonal fledglings  = 7.04
#   mean seasonal eggs        = 22.92
#   total known population    ≈ 50 (matches model initial_number)
#
#   fledge_rate  = 7.04 / 22.92  ≈ 0.307   (fledglings per egg laid)
#   eggs_per_50  = 22.92 / 50    ≈ 0.458   (eggs per bird in the population)

TARGET_STATS: dict[str, float] = {
    "fledge_rate": 0.307,
    "eggs_per_50": 0.458,
}

# Scale factors for normalising the Euclidean distance (≈ expected SD of each stat)
TARGET_SCALE: dict[str, float] = {
    "fledge_rate": 0.15,
    "eggs_per_50": 0.20,
}

# ── Fixed (non-calibrated) parameter defaults ─────────────────────────────────
# Starting population fixed at observed baseline; all other parameters are
# either in PRIORS (calibrated) or listed here at their interface defaults
# as a fallback.  PRIORS values will always override these.

FIXED_PARAMS: dict[str, float] = {
    "initial_number": 50,
}

# ── Latin Hypercube Sampling ───────────────────────────────────────────────────

def latin_hypercube_samples(
    priors: dict[str, tuple[float, float]],
    n_samples: int,
    rng: random.Random,
) -> list[dict[str, float]]:
    """
    Return n_samples parameter dicts via Latin Hypercube Sampling.

    Each parameter axis is divided into n_samples equal-probability strata;
    one value is drawn uniformly from each stratum, then the strata are
    permuted independently per parameter.  This guarantees full-range
    coverage with far fewer simulations than pure random sampling.
    """
    param_names = list(priors)
    n_params    = len(param_names)

    # Build a (n_samples × n_params) matrix of stratified uniform samples
    matrix: list[list[float]] = []
    for col, (lo, hi) in enumerate(priors.values()):
        col_vals: list[float] = []
        for stratum in range(n_samples):
            u = rng.uniform(stratum / n_samples, (stratum + 1) / n_samples)
            col_vals.append(lo + u * (hi - lo))
        rng.shuffle(col_vals)
        matrix.append(col_vals)

    # Transpose: matrix[col][row] → samples[row][col]
    return [
        {param_names[col]: matrix[col][row] for col in range(n_params)}
        for row in range(n_samples)
    ]


# ── Model helpers ──────────────────────────────────────────────────────────────

def build_experiment_xml(params: dict[str, float], name: str) -> str:
    """Return a full <experiments> block for a single BehaviorSpace run."""
    merged = dict(FIXED_PARAMS)
    merged.update(params)

    lines = [
        "  <experiments>",
        (
            f'    <experiment name="{name}" repetitions="1"'
            ' sequentialRunOrder="true" runMetricsEveryStep="false" timeLimit="365">'
        ),
        "      <setup>setup</setup>",
        "      <go>go</go>",
        "      <metrics>",
        "        <metric>total_birds</metric>",
        "        <metric>fledged</metric>",
        "        <metric>total_eggs</metric>",
        "      </metrics>",
        "      <constants>",
    ]
    for var, val in merged.items():
        lines += [
            f'        <enumeratedValueSet variable="{var}">',
            f'          <value value="{val}"/>',
            "        </enumeratedValueSet>",
        ]
    lines += [
        "      </constants>",
        "    </experiment>",
        "  </experiments>",
    ]
    return "\n".join(lines)


def inject_experiments(source: str, experiments_xml: str) -> str:
    """Replace the <experiments>…</experiments> block in the model source."""
    cleaned = re.sub(
        r"\s*<experiments>.*?</experiments>", "", source, flags=re.DOTALL
    )
    return cleaned.replace("</model>", experiments_xml + "\n</model>", 1)


def run_netlogo(model_path: str, exp_name: str, out_csv: str) -> tuple[bool, str]:
    """Run one BehaviorSpace experiment; return (success, error_message)."""
    cmd = [
        NETLOGO_SCRIPT,
        "--model", model_path,
        "--experiment", exp_name,
        "--table", out_csv,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=NETLOGO_TIMEOUT_SEC)
        if r.returncode != 0:
            return False, (r.stderr or r.stdout)[:400]
        return True, ""
    except subprocess.TimeoutExpired:
        return False, f"timeout after {NETLOGO_TIMEOUT_SEC} s"


def parse_last_row(csv_path: str) -> dict | None:
    """Return the last data row from a BehaviorSpace table CSV."""
    try:
        with open(csv_path) as f:
            lines = f.readlines()
        hdr = next(
            (i for i, line in enumerate(lines) if "[run number]" in line), None
        )
        if hdr is None:
            return None
        rows = list(csv.DictReader(lines[hdr:]))
        return rows[-1] if rows else None
    except Exception as exc:
        print(f"  parse error: {exc}", file=sys.stderr)
        return None


def compute_summary_stats(row: dict) -> dict[str, float]:
    birds  = float(row.get("total_birds", 0) or 0)
    fledge = float(row.get("fledged",     0) or 0)
    eggs   = float(row.get("total_eggs",  0) or 0)
    pop    = float(FIXED_PARAMS["initial_number"])
    return {
        "fledge_rate": fledge / max(1.0, eggs),
        "eggs_per_50": eggs   / pop,
        "total_birds": birds,
        "fledged":     fledge,
        "total_eggs":  eggs,
    }


def compute_distance(stats: dict[str, float]) -> float:
    """Normalised Euclidean distance from the observed targets."""
    return math.sqrt(
        sum(
            ((stats.get(k, 0.0) - TARGET_STATS[k]) / TARGET_SCALE[k]) ** 2
            for k in TARGET_STATS
        )
    )


# ── Per-sample worker (called by thread pool) ──────────────────────────────────

def run_sample(
    sample_id: int,
    params: dict[str, float],
    model_src: str,
    tmpdir: str,
    print_lock: threading.Lock,
) -> dict | None:
    """
    Run one ABC sample in its own temp files.  Returns a result dict on
    success or None on failure.  Thread-safe: all I/O uses unique file paths.
    """
    name      = f"abc_{sample_id:04d}"
    tmp_model = os.path.join(tmpdir, f"model_{sample_id:04d}.nlogox")
    tmp_csv   = os.path.join(tmpdir, f"results_{sample_id:04d}.csv")

    exp_xml = build_experiment_xml(params, name)
    src     = inject_experiments(model_src, exp_xml)

    with open(tmp_model, "w") as f:
        f.write(src)

    t0 = time.monotonic()
    ok, err = run_netlogo(tmp_model, name, tmp_csv)
    elapsed = time.monotonic() - t0

    if not ok:
        with print_lock:
            print(f"  [{sample_id:4d}/{N_SAMPLES}] FAILED ({elapsed:.1f}s): {err[:100]}")
        return None

    row = parse_last_row(tmp_csv)
    if row is None:
        with print_lock:
            print(f"  [{sample_id:4d}/{N_SAMPLES}] NO RESULTS ({elapsed:.1f}s)")
        return None

    ss   = compute_summary_stats(row)
    dist = compute_distance(ss)

    with print_lock:
        print(
            f"  [{sample_id:4d}/{N_SAMPLES}] dist={dist:.3f}  "
            f"fledge_rate={ss['fledge_rate']:.3f}  "
            f"eggs/50={ss['eggs_per_50']:.3f}  "
            f"({elapsed:.1f}s)"
        )

    return {"sample_id": sample_id, **params, **ss, "distance": dist}


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    rng = random.Random(RANDOM_SEED)

    with open(MODEL_FILE) as f:
        model_src = f.read()

    samples = latin_hypercube_samples(PRIORS, N_SAMPLES, rng)

    print(f"ABC calibration: {N_SAMPLES} LHS samples  workers={N_WORKERS}  seed={RANDOM_SEED}")
    print(f"Parameters ({len(PRIORS)}):  {', '.join(PRIORS)}")
    print(
        f"Targets:     fledge_rate={TARGET_STATS['fledge_rate']:.3f}  "
        f"eggs_per_50={TARGET_STATS['eggs_per_50']:.3f}\n"
    )

    tmpdir     = tempfile.mkdtemp(prefix="abc_tara_")
    print_lock = threading.Lock()
    records: list[dict] = []
    n_failed   = 0
    t_start    = time.monotonic()

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=N_WORKERS) as executor:
            futures = {
                executor.submit(run_sample, i, params, model_src, tmpdir, print_lock): i
                for i, params in enumerate(samples)
            }
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result is None:
                    n_failed += 1
                else:
                    records.append(result)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    elapsed_total = time.monotonic() - t_start

    if not records:
        print("\nERROR: all runs failed.", file=sys.stderr)
        sys.exit(1)

    records.sort(key=lambda r: r["distance"])
    n_accept = max(1, round(len(records) * ACCEPT_FRACTION))
    accepted = records[:n_accept]

    fields = list(records[0].keys())
    with open("abc_all.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(records)

    with open("abc_accepted.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(accepted)

    print(f"\n{'='*60}")
    print(
        f"Completed: {len(records)} successful / {n_failed} failed / {N_SAMPLES} total"
        f"  ({elapsed_total:.1f}s wall time)"
    )
    print(f"Accepted (top {ACCEPT_FRACTION:.0%}): {n_accept} runs")
    print(f"\nBest run (distance={records[0]['distance']:.4f}):")
    for k in list(PRIORS)[:8] + ["fledge_rate", "eggs_per_50", "fledged", "total_eggs"]:
        print(f"  {k:>26s} = {records[0][k]:.6g}")
    print(f"\nPosterior ranges across {n_accept} accepted runs:")
    for k in PRIORS:
        vals = [r[k] for r in accepted]
        mean = sum(vals) / len(vals)
        print(f"  {k:>26s}: [{min(vals):.4g}, {max(vals):.4g}]  mean={mean:.4g}")
    print(f"\nResults written to abc_all.csv and abc_accepted.csv")


if __name__ == "__main__":
    main()
