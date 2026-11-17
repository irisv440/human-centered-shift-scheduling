# -*- coding: utf-8 -*-
"""
compare_rosters.py

Historical roster (cycle 1) versus the candidate roster of the CPMpy model (scheduler/model.py).
Both rosters are scored on the same route: score_all_workers, then compute_objective.
The candidate roster is also checked against the historical patterns (evaluator/validity.py).

@author: irisv
"""

from pathlib import Path
import sys

# Makes 'from scheduler import ...' work when running this file with F5,
# whatever the working directory is: adds the repo root to the import path (same as model.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from cpmpy.solvers.solver_interface import ExitStatus
from scheduler import requirements_config as cf
from scheduler.model import build_model

from evaluator.estimate_lmm import estimate_cell_parameters_lmm
from evaluator.validity import get_historical_patterns, get_rosters_from_records
from evaluator.score_all_workers import score_all_workers
from evaluator.objective import compute_objective


def build_baseline_roster(cell_parameters, assignments):
    """
    Objective of the historical roster of cycle 1 (first 28 days), via compute_objective.

    cell_parameters: the first element of the output of estimate_cell_parameters_lmm
                     (the same fit as for the candidate roster).
    assignments: DataFrame of data/historical_assignments.csv (all 84 days);
                 this function selects cycle 1 itself.
    """

    # Get dates from the first cycle (28 days)
    first_dates = sorted(assignments["date"].unique())[:28]
    cycle_1 = assignments[assignments["date"].isin(first_dates)] # keep data from the first 28 dates
    
    # Get rosters from records: # import from evaluator.validity, returns roster from ALL workers
    rosters = get_rosters_from_records(cycle_1.to_dict("records")) # returns 1 dictionary per row due to the "records" argument of "to_dict"
    
    # Get scores - no validity check for the historical roster itself, so no 'historical_patterns' argument
    results = score_all_workers(rosters, cell_parameters)

    # Objective:
    # 1. 'results' contains T and K at roster level; 'compute_objective' turns these scores
    #    into sleep_loss_minutes (= minus T * 60) and short_nights_thousandths (= K * 1000)
    # 2. Threshold and weight come from the config (values still to be tuned);
    #    weight 36 / scale 100 = 0.36 minutes per thousandth
    baseline_objective = compute_objective(results, threshold_thousandths=cf.objective_threshold_thousandths, weight=cf.objective_weight / cf.objective_scale)
    
    return baseline_objective

# Solve, convert, score, objective and validity check
def build_candidate_roster(cell_parameters, historical_rosters_all):
    """
    Solve the CPMpy model and score the candidate roster on the same route as the baseline.

    cell_parameters: the first element of the output of estimate_cell_parameters_lmm.
    historical_rosters_all: get_rosters_from_records on ALL historical assignments (84 days),
                            not only cycle 1, so the validity check knows every historical pattern.

    Returns None if the solver finds no roster, otherwise a dict:
    {
      "status": the solver status,
      "solver_objective": objective.value(), in the solver unit (x objective_scale),
      "rosters": worker_id -> list of str ("off", "early", "late", "night"),
      "results": the output of score_all_workers, including the validity fields,
      "candidate_objective": the output of compute_objective (minutes, same unit as the baseline),
    }
    """
    model, shifts, assigned_team, early_linked, late_linked, night_linked, off_linked, objective = build_model(cell_parameters)

    # solve the model
    model.solve()

    # Check status
    print(model.status())

    if not (model.status().exitstatus == ExitStatus.FEASIBLE or model.status().exitstatus == ExitStatus.OPTIMAL):
        return None

    # 1. shifts.value() -> one roster per worker, same form as get_rosters_from_records
    # Codes 0 - 3 become "off"/"early"/"late"/"night" (reverse of cf.SHIFT_CODES).
    code_to_shift = {code: shift for shift, code in cf.SHIFT_CODES.items()}
    # Row i in the model = worker i in sorted order (W001 ... W030), same as the cost tables
    worker_ids = sorted(cell_parameters)
    shift_values = shifts.value()  # numpy array, n_workers x n_days, values 0 - 3
    rosters = {}
    for i, worker_id in enumerate(worker_ids):
        rosters[worker_id] = [code_to_shift[int(code)] for code in shift_values[i]]

    # 2. Historical patterns from ALL historical data (transitions and block lengths)
    historical_patterns = get_historical_patterns(historical_rosters_all)

    # 3. Score every worker; with historical_patterns, score_all_workers also runs
    #    check_roster_validity per worker (one worker's list at a time)
    results = score_all_workers(rosters, cell_parameters, historical_patterns)

    # 4. Objective on the same route as the baseline (compute_objective, not rounded per cell)
    candidate_objective = compute_objective(results, threshold_thousandths=cf.objective_threshold_thousandths, weight=cf.objective_weight / cf.objective_scale)

    return {
        "status": model.status(),
        "solver_objective": objective.value(),
        "rosters": rosters,
        "results": results,
        "candidate_objective": candidate_objective,
    }


if __name__ == "__main__":

    # Get the data for the LMM estimations:
    data_dir = Path(__file__).resolve().parent.parent / "data" # [Changed 2026-11-16] relative to this file, so F5 works whatever the working directory is
    sleep_records = pd.read_csv(data_dir / "historical_sleep.csv").to_dict("records")
    
    # Fit the LMM
    cell_parameters, result = estimate_cell_parameters_lmm(sleep_records)

    # Historical assignments (all 84 days): used for the baseline roster (cycle 1)
    # and for the historical patterns of the validity check of the candidate roster
    assignments = pd.read_csv(data_dir/"historical_assignments.csv")
    
    # Build baseline roster
    baseline_objective = build_baseline_roster(cell_parameters, assignments)
    
    # Totals, rounded to 2 decimals for display only
    print("Objective of the baseline roster:")
    for name in ("objective", "total_sleep_loss_minutes", "total_excess_thousandths", "penalty"):
        print(f"  {name}: {round(baseline_objective[name], 2)}")
    print(f"  unscored_workers: {baseline_objective['unscored_workers']}")
    
    # One row per scored worker, rounded to 2 decimals for display only
    print()
    print("Per worker:")
    print(pd.DataFrame(baseline_objective["per_worker"]).round(2).to_string(index=False))

    # Candidate roster: solve, score on the same route, check validity
    historical_rosters_all = get_rosters_from_records(assignments.to_dict("records"))  # all 84 days, for the patterns
    # Build candidate roster + check its validity
    candidate = build_candidate_roster(cell_parameters, historical_rosters_all)

    if candidate is None:
        print("\nNo candidate roster found.")
    else:
        candidate_objective = candidate["candidate_objective"]

        print("\nObjective of the candidate roster:")
        for name in ("objective", "total_sleep_loss_minutes", "total_excess_thousandths", "penalty"):
            print(f"  {name}: {round(candidate_objective[name], 2)}")
        print(f"  unscored_workers: {candidate_objective['unscored_workers']}")

        # Check of make_objective: solver value / scale should be close to compute_objective (rounding only)
        print()
        print("Check of make_objective:")
        print(f"  solver objective / objective_scale: {candidate['solver_objective'] / cf.objective_scale}")
        print(f"  compute_objective (not rounded):    {round(candidate_objective['objective'], 2)}")

        # Comparison with the baseline, both from compute_objective
        difference = baseline_objective["objective"] - candidate_objective["objective"]
        print()
        print("Baseline versus candidate (compute_objective):")
        print(f"  baseline:  {round(baseline_objective['objective'], 2)}")
        print(f"  candidate: {round(candidate_objective['objective'], 2)}")
        print(f"  difference: {round(difference, 2)} lower ({round(100 * difference / baseline_objective['objective'], 1)} %)")

        # Validity per worker: which patterns never occur in the historical roster
        print()
        print("Validity of the candidate roster (patterns compared with all historical data):")
        n_extrapolation = 0
        for row in candidate["results"]:
            if row["is_extrapolation"]:
                n_extrapolation += 1
            print(f"  {row['worker_id']}: is_extrapolation={row['is_extrapolation']}"
                  f" | unseen_transitions={row['unseen_transitions']}"
                  f" | unseen_block_lengths={row['unseen_block_lengths']}"
                  f" | uncertain_boundary_block_lengths={row['uncertain_boundary_block_lengths']}")
        print(f"  Workers flagged as extrapolation: {n_extrapolation} of {len(candidate['results'])}")
