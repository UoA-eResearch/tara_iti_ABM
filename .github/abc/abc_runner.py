#!/usr/bin/env python3
"""
Approximate Bayesian Computation (ABC) for calibrating the tara iti ABM.

For each of N_SAMPLES parameter sets sampled from uniform priors the script:
  1. Injects a BehaviorSpace experiment into a temporary copy of the model
  2. Runs NetLogo headlessly for 365 ticks (one simulated year)
  3. Parses the BehaviorSpace table CSV
  4. Computes a normalised Euclidean distance to field-observed summary statistics
  5. Accepts the top ACCEPT_FRACTION of successful runs as the ABC posterior

Output files (written to the working directory):
  abc_all.csv      – all successful runs (parameters, summary stats, distance)
  abc_accepted.csv – accepted runs (top ACCEPT_FRACTION by distance)

Environment variables (all optional):
  NETLOGO_SCRIPT      path to netlogo-headless.sh  (default: ./NetLogo-7.0.4-64/netlogo-headless.sh)
  MODEL_FILE          path to .nlogox model file    (default: breeding_storm_predation2.nlogox)
  ABC_N_SAMPLES       number of prior samples       (default: 30)
  ABC_ACCEPT_FRACTION fraction to accept            (default: 0.20)
  ABC_SEED            random seed                   (default: 42)
"""

from __future__ import annotations

import csv
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time

# ── Configuration ─────────────────────────────────────────────────────────────

NETLOGO_SCRIPT  = os.environ.get("NETLOGO_SCRIPT",      "./NetLogo-7.0.4-64/netlogo-headless.sh")
MODEL_FILE      = os.environ.get("MODEL_FILE",           "breeding_storm_predation2.nlogox")
N_SAMPLES       = int(os.environ.get("ABC_N_SAMPLES",   "30"))
ACCEPT_FRACTION = float(os.environ.get("ABC_ACCEPT_FRACTION", "0.20"))
RANDOM_SEED     = int(os.environ.get("ABC_SEED",        "42"))

# ── Prior distributions (uniform [low, high]) ─────────────────────────────────
# Parameters with the most ecological uncertainty that directly affect fledge
# rate and egg production.  All others are held at their interface defaults.

PRIORS: dict[str, tuple[float, float]] = {
    "hatch_failure":      (0.10, 0.60),  # per-egg probability of failing to hatch
    "court_success":      (0.50, 1.00),  # daily probability of successful pairing
    "breeding_condition": (0.60, 0.95),  # minimum condition score required to breed
    "mean_clutch_no":     (1.00, 2.50),  # mean number of clutches attempted per season
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
# These are the interface defaults from breeding_storm_predation2.nlogox.
# Values listed in PRIORS will override these for each ABC sample.

FIXED_PARAMS: dict[str, float] = {
    "initial_number": 50, "patch_threshold": 0.2, "courting_threshold": 10,
    "court_success": 0.75, "breeding_condition": 0.8, "mean_clutch_no": 1.68,
    "incubation_cond_loss": 0.025, "abandon_threshold": 0.2,
    "hatch_failure": 0.2, "with_chick_cond_loss": 0.005,
    "cooling_off_days": 10, "winter_adult_mort": 4.0e-4, "winter_imm_mort": 3.0e-4,
    "winter_juv_mort": 5.0e-4, "courting_condition": 0.55, "candle_success": 0.8,
    "winter_elder_mort": 0.001, "mean_foraging_gain": 0.06, "sd_foraging_gain": 0.008,
    "mean_metabolic_loss": 0.06, "sd_metabolic_loss": 0.006,
    "mean_breeding_prep": 0.085, "sd_breeding_prep": 0.03, "chick_health": 0.0025,
    "nest_risk_thresh_small": 0.5, "nest_risk_thresh_large": 0.6,
    "nest_risk_thresh_extreme": 0.95, "nest_loss_extreme": 0.5,
    "nest_loss_large": 0.2, "nest_loss_small": 0.15, "juv_cond_loss": 0.11,
    "extreme_cond_loss": 0.01, "large_cond_loss": 0.006, "small_cond_loss": 0.003,
    "storm_prob": 0.03, "avian_predator_prob": 0.016, "mam_predator_prob": 0.018,
    "sibling_attack": 0.75, "gull_egg_take": 1.0, "kahu_egg_take": 1.5,
    "shorebird_egg_take": 2.0, "gull_chick_take": 1.0, "kahu_chick_take": 1.5,
    "shorebird_chick_take": 1.0, "rat_egg_take": 1.3, "cat_egg_take": 1.5,
    "other_egg_take": 2.0, "rat_chick_take": 1.3, "cat_chick_take": 1.5,
    "other_chick_take": 2.0,
}

# ── Helpers ───────────────────────────────────────────────────────────────────

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
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if r.returncode != 0:
            return False, (r.stderr or r.stdout)[:400]
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "timeout after 180 s"


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


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    rng = random.Random(RANDOM_SEED)

    with open(MODEL_FILE) as f:
        model_src = f.read()

    tmpdir  = tempfile.mkdtemp(prefix="abc_tara_")
    records: list[dict] = []
    n_failed = 0

    print(f"ABC calibration: {N_SAMPLES} samples  seed={RANDOM_SEED}")
    print(f"Parameters:  {', '.join(PRIORS)}")
    print(
        f"Targets:     fledge_rate={TARGET_STATS['fledge_rate']:.3f}  "
        f"eggs_per_50={TARGET_STATS['eggs_per_50']:.3f}\n"
    )

    try:
        for i in range(N_SAMPLES):
            params  = {k: rng.uniform(*v) for k, v in PRIORS.items()}
            name    = f"abc_{i:03d}"
            exp_xml = build_experiment_xml(params, name)
            src     = inject_experiments(model_src, exp_xml)

            tmp_model = os.path.join(tmpdir, f"model_{i:03d}.nlogox")
            tmp_csv   = os.path.join(tmpdir, f"results_{i:03d}.csv")

            with open(tmp_model, "w") as f:
                f.write(src)

            t0 = time.monotonic()
            ok, err = run_netlogo(tmp_model, name, tmp_csv)
            elapsed = time.monotonic() - t0

            if not ok:
                n_failed += 1
                print(f"  [{i:3d}/{N_SAMPLES}] FAILED ({elapsed:.1f}s): {err[:120]}")
                continue

            row = parse_last_row(tmp_csv)
            if row is None:
                n_failed += 1
                print(f"  [{i:3d}/{N_SAMPLES}] NO RESULTS ({elapsed:.1f}s)")
                continue

            ss   = compute_summary_stats(row)
            dist = compute_distance(ss)
            records.append({"sample_id": i, **params, **ss, "distance": dist})

            print(
                f"  [{i:3d}/{N_SAMPLES}] dist={dist:.3f}  "
                f"fledge_rate={ss['fledge_rate']:.3f}  "
                f"eggs/50={ss['eggs_per_50']:.3f}  "
                f"({elapsed:.1f}s)"
            )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

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
    print(f"Completed: {len(records)} successful / {n_failed} failed / {N_SAMPLES} total")
    print(f"Accepted (top {ACCEPT_FRACTION:.0%}): {n_accept} runs")
    print(f"\nBest run (distance={records[0]['distance']:.4f}):")
    for k in list(PRIORS) + ["fledge_rate", "eggs_per_50", "fledged", "total_eggs"]:
        print(f"  {k:>22s} = {records[0][k]:.4f}")
    print(f"\nPosterior ranges across {n_accept} accepted runs:")
    for k in PRIORS:
        vals = [r[k] for r in accepted]
        mean = sum(vals) / len(vals)
        print(f"  {k:>22s}: [{min(vals):.4f}, {max(vals):.4f}]  mean={mean:.4f}")
    print(f"\nResults written to abc_all.csv and abc_accepted.csv")


if __name__ == "__main__":
    main()
