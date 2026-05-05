#!/usr/bin/env python3
"""
set_best_params.py

Reads abc_all.csv (pre-sorted ascending by distance from abc_runner.py),
picks the best-fit parameter set, writes best_params.csv, and updates the
<experiments> block in the .nlogox model file so that:

  - the experiment is named "default"
  - all calibrated parameters are set to the ABC best values
  - initial_number is kept at its fixed value (50)
  - timeLimit is set to 18250 ticks (50 years × 365 ticks/year)

Environment variables:
  MODEL_FILE   path to .nlogox file  (default: breeding_storm_predation2.nlogox)
  ABC_ALL_CSV  path to abc_all.csv   (default: abc_all.csv)
"""

from __future__ import annotations

import csv
import os
import re
import sys

MODEL_FILE  = os.environ.get("MODEL_FILE",  "breeding_storm_predation2.nlogox")
ABC_ALL_CSV = os.environ.get("ABC_ALL_CSV", "abc_all.csv")

YEARS      = 50
TIME_LIMIT = YEARS * 365   # 18250 ticks

# Fixed parameter that is not calibrated by ABC
FIXED_PARAMS: dict[str, float] = {"initial_number": 50}

# Columns in abc_all.csv that are NOT calibrated parameters
NON_PARAM_COLS = frozenset({
    "sample_id",
    "fledge_rate", "eggs_per_50",
    "total_birds", "fledged", "total_eggs",
    "distance",
})


def build_experiments_xml(params: dict[str, float]) -> str:
    """Return an <experiments> block with best-fit parameters and 50-year timeLimit."""
    merged: dict[str, float] = dict(FIXED_PARAMS)
    merged.update(params)

    lines = [
        "  <experiments>",
        (
            f'    <experiment name="default" repetitions="1"'
            f' sequentialRunOrder="true" runMetricsEveryStep="false"'
            f' timeLimit="{TIME_LIMIT}">'
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
    """Replace the existing <experiments>…</experiments> block in the model source."""
    cleaned = re.sub(
        r"\s*<experiments>.*?</experiments>", "", source, flags=re.DOTALL
    )
    return cleaned.replace("</model>", experiments_xml + "\n</model>", 1)


def main() -> None:
    # Read the best parameter set (first row = lowest distance)
    with open(ABC_ALL_CSV, newline="") as f:
        reader = csv.DictReader(f)
        best = next(reader, None)

    if best is None:
        print("ERROR: abc_all.csv is empty or has no data rows.", file=sys.stderr)
        sys.exit(1)

    params = {k: float(v) for k, v in best.items() if k not in NON_PARAM_COLS}

    print(f"Best run: distance={float(best['distance']):.6g}")
    print(f"Calibrated parameters ({len(params)}):")
    for k, v in params.items():
        print(f"  {k:>26s} = {v:.6g}")

    # Write best_params.csv (parameter name + value)
    with open("best_params.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["parameter", "value"])
        writer.writerow(["initial_number", FIXED_PARAMS["initial_number"]])
        for k, v in params.items():
            writer.writerow([k, v])
    print("Written best_params.csv")

    # Update the model file
    with open(MODEL_FILE) as f:
        src = f.read()

    exp_xml = build_experiments_xml(params)
    new_src = inject_experiments(src, exp_xml)

    with open(MODEL_FILE, "w") as f:
        f.write(new_src)
    print(
        f"Updated {MODEL_FILE} with best ABC parameters"
        f" (timeLimit={TIME_LIMIT} = {YEARS} years)"
    )


if __name__ == "__main__":
    main()
