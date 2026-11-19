# -*- coding: utf-8 -*-
"""
tune_parameters.py

Sensitivity analysis of the objective settings: objective_threshold_thousandths and
objective_weight vary over a grid, request_penalty_minutes stays at its config value.
Each run goes through build_candidate_roster (validation/compare_rosters.py).

Per run:
  - total_sleep_loss_minutes: from compute_objective, without the penalty term
  - workers_above_10: workers with more than FIXED_SHORT_NIGHTS_LIMIT expected short
    nights; a fixed limit, the same in every run, whatever the threshold of that run
  - violated_requests: number of violated off requests
  - workers_extrapolation: workers flagged as extrapolation by the validity check

@author: irisv
"""

from pathlib import Path
import sys

# Makes 'from scheduler import ...' work when running this file with F5 (same as compare_rosters.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import date
import pandas as pd
from scheduler import requirements_config as cf

from evaluator.estimate_lmm import estimate_cell_parameters_lmm
from evaluator.validity import get_rosters_from_records
from validation.compare_rosters import build_candidate_roster


# Grid: thresholds symmetric around the config value (10000), steps of 2.5 nights;
# weights half, equal to and double the config value (36)
THRESHOLDS = [7500, 10000, 12500]   # objective_threshold_thousandths, in thousandths of a short night
WEIGHTS = [18, 36, 72]              # objective_weight, in the solver unit (config value: 36)

# Fixed limit for counting workers: 10 expected short nights, in thousandths.
# Does NOT change with the threshold of the run.
FIXED_SHORT_NIGHTS_LIMIT = 10000

# Maximum solver time per run, in seconds (5 minutes)
TIME_LIMIT_SECONDS = 300


if __name__ == "__main__":

    # Data: fit the LMM once, read the historical assignments once
    data_dir = Path(__file__).resolve().parent.parent / "data"
    sleep_records = pd.read_csv(data_dir / "historical_sleep.csv").to_dict("records")
    cell_parameters, result = estimate_cell_parameters_lmm(sleep_records)

    assignments = pd.read_csv(data_dir / "historical_assignments.csv")
    historical_rosters_all = get_rosters_from_records(assignments.to_dict("records"))

    rows = []  # one row per run

    for threshold in THRESHOLDS:
        for weight in WEIGHTS:
            print(f"\nRun: threshold {threshold}, weight {weight}")
            candidate = build_candidate_roster(cell_parameters, historical_rosters_all,
                                               threshold=threshold, weight=weight,
                                               time_limit=TIME_LIMIT_SECONDS)

            if candidate is None:
                # No roster found: record the run, without outcomes
                rows.append({
                    "threshold": threshold,
                    "weight": weight,
                    "status": "no solution",
                    "total_sleep_loss_minutes": None,
                    "workers_above_10": None,
                    "violated_requests": None,
                    "workers_extrapolation": None,
                })
                continue  # next run

            # Workers above the fixed limit
            workers_above_10 = 0
            for worker in candidate["candidate_objective"]["per_worker"]:
                if worker["short_nights_thousandths"] > FIXED_SHORT_NIGHTS_LIMIT:
                    workers_above_10 += 1

            # Workers flagged as extrapolation
            workers_extrapolation = 0
            for row in candidate["results"]:
                if row["is_extrapolation"]:
                    workers_extrapolation += 1

            rows.append({
                "threshold": threshold,
                "weight": weight,
                "status": candidate["status"].exitstatus.name,  # e.g. "OPTIMAL"
                "total_sleep_loss_minutes": round(candidate["candidate_objective"]["total_sleep_loss_minutes"], 2),
                "workers_above_10": workers_above_10,
                "violated_requests": candidate["n_violated_requests"],
                "workers_extrapolation": workers_extrapolation,
            })

    # Table: print and write to Excel (scheduler/output/, gitignored)
    table = pd.DataFrame(rows)
    print("\nSensitivity analysis (request_penalty_minutes = " + str(cf.request_penalty_minutes) + "):")
    print(table.to_string(index=False))

    output_dir = Path(__file__).resolve().parent.parent / "scheduler" / "output"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"tune_parameters_{date.today().isoformat()}.xlsx"
    table.to_excel(output_path, index=False)
    print(f"\nWritten to {output_path}")
