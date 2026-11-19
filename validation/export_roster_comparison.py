# -*- coding: utf-8 -*-
"""
export_roster_comparison.py

Purpose: create an example result in JSON for the API (version 1).
The script computes, once, the historical roster (cycle 1) and the candidate roster of the
CPMpy model, scores both, and writes them side by side to data/roster_comparison.json.
GET /roster-comparison serves this file; the solver itself never runs in the API.

In version 2, users can send their own roster to the API. The rosters in this file use the
same format ({"W001": ["early", ...], ...}), so they also serve as an example of that input.

Run from the project root:  python -m validation.export_roster_comparison

@author: irisv
"""

from pathlib import Path
import sys
import json

# Makes 'from scheduler import ...' work when running this file with F5 (same as compare_rosters.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from datetime import datetime

from evaluator.estimate_lmm import estimate_cell_parameters_lmm
from validation.compare_rosters import build_baseline_roster, build_candidate_roster
from evaluator.validity import get_rosters_from_records
from scheduler import requirements_config as cf

# Machine on which the result was computed (fill in by hand): solver time depends on it
MACHINE = "laptop, Intel Core i7-9750H (6 cores, 2.6 GHz), 16 GB RAM"

if __name__ == "__main__":

    # Data folder, relative to this file
    data_dir = Path(__file__).resolve().parent.parent / "data"

    # 1. Load the data and fit the LMM once
    sleep_records = pd.read_csv(data_dir / "historical_sleep.csv").to_dict("records")
    cell_parameters, result = estimate_cell_parameters_lmm(sleep_records)

    # Historical assignments (all 84 days): baseline (cycle 1) and historical patterns
    assignments = pd.read_csv(data_dir / "historical_assignments.csv")

    # 2. Score the historical roster of cycle 1 (baseline)
    baseline_objective = build_baseline_roster(cell_parameters, assignments)

    # The roster itself of cycle 1, same selection as in build_baseline_roster (first 28 dates)
    first_dates = sorted(assignments["date"].unique())[:28]
    cycle_1 = assignments[assignments["date"].isin(first_dates)]
    baseline_rosters = get_rosters_from_records(cycle_1.to_dict("records"))

    # 3. Solve and score the candidate roster (validity check on all 84 historical days)
    historical_rosters_all = get_rosters_from_records(assignments.to_dict("records"))
    
    # candidate: a dict with "status" (solver status and runtime), "solver_objective",
    # "rosters" (the roster per worker), "results" (scores and extrapolation per worker),
    # "candidate_objective" (the objective in minutes) and "n_violated_requests";
    
    # Is None if the solver found no roster.
    candidate = build_candidate_roster(cell_parameters, historical_rosters_all)

    # No roster found (e.g. a config change makes the model infeasible): stop here,
    # so that no incomplete JSON file is written for the API to serve.
    if candidate is None:
        sys.exit("No candidate roster found: nothing written.")

    # 4. Difference between baseline and candidate, both from compute_objective (minutes)
    candidate_objective = candidate["candidate_objective"]
    difference = baseline_objective["objective"] - candidate_objective["objective"]
    difference_percent = 100 * difference / baseline_objective["objective"]

    # 5. Metadata: when, how and with which settings this result was computed
    metadata = {
        "computed_at": datetime.now().isoformat(timespec="seconds"),
        "solver_status": candidate["status"].exitstatus.name,
        "solver_runtime_seconds": round(candidate["status"].runtime, 1),
        "solver_time_limit_seconds": None,  # build_candidate_roster is called without a time limit (step 3)
        "machine": MACHINE,
        "objective_threshold_thousandths": cf.objective_threshold_thousandths,
        "objective_weight": cf.objective_weight,
        "objective_scale": cf.objective_scale,
        "request_penalty_minutes": cf.request_penalty_minutes,
        "baseline": "historical roster, cycle 1 (first 28 days of data/historical_assignments.csv)",
    }

    # 6. Write everything to one JSON file for the API
    output = {
        "metadata": metadata,
        "baseline": {
            "objective": baseline_objective,
            "rosters": baseline_rosters,
        },
        "candidate": {
            "objective": candidate_objective,
            "solver_objective": int(candidate["solver_objective"]),  # x objective_scale, includes the request penalty
            "n_violated_requests": candidate["n_violated_requests"],
            "rosters": candidate["rosters"],
            "results": candidate["results"],
        },
        "comparison": {
            "difference_minutes": difference,
            "difference_percent": difference_percent,
        },
    }
  
    output_path = data_dir / "roster_comparison.json"
    # default = float: converts numpy numbers (e.g. from scipy) that json cannot write by itself
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(output, file, indent=2, default=float)
  
    print("Written:", output_path)
    
  