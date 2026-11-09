# -*- coding: utf-8 -*-
"""
score_all_workers.py

Scores a full roster, per worker.

Also prints a summary

@author: irisv
"""

from pathlib import Path

import pandas as pd

from evaluator.estimate_lmm import estimate_cell_parameters_lmm
from evaluator.roster_score import score_roster # individual scores needed to group all scores together
from evaluator.validity import check_roster_validity, get_historical_patterns, get_rosters_from_records # validity: individual validity FB to group all scores together


def score_all_workers(rosters, cell_parameters, historical_patterns):
    """
    Score every worker's roster and check its validity.

    Parameters
    ----------
    rosters : dict
        worker_id (str) -> list of str, the shift WORKED per date.
        The output of get_rosters_from_records.
    cell_parameters : dict
        worker_id (str) -> that worker's estimates.
        The first element of the output of estimate_cell_parameters_lmm.
    historical_patterns : dict
        The output of get_historical_patterns.

    Returns
    -------
    list of dict, one per worker, see example below:
        {
          "worker_id": str,
          "cumulative_diff_hours": float or None,                    # T
          "expected_short_nights_given_main_sleep": float or None,   # K
          "per_linked_shift": dict or None,                          # breakdown of T and K
          "is_extrapolation": bool,
          "unseen_transitions": list of tuples,
          "unseen_block_lengths": list of tuples,
          "uncertain_boundary_block_lengths": list of tuples,
        }

    "per_linked_shift" [Added 2026-11-09]: the breakdown returned by
    score_roster, so linked shift type ("off", "early", "late", "night")
    -> dict with six values: num_nights, diff_contribution_hours,
    expected_short_nights_contribution, diff_per_night_hours,
    p_short_per_night, p_short_increase_vs_off. See the docstring of
    score_roster for their meaning. None when score_roster returns None,
    just like T and K; the validity feedback is always filled in.
    """
    
    results = []  # one dict per worker, filled in the loop
    
    # Loops through all workers, collecting scores and validity feedback.
    for worker_id in sorted(rosters): # sorted: W001 --> W030
        roster_shifts = rosters[worker_id]            # list of str: this worker's shifts only
        worker_parameters = cell_parameters[worker_id]  # dict: this worker's estimates
        
        scores = score_roster(roster_shifts, worker_parameters)  # dict with T and K, or None
        # validity of the historical patterns, which are the same for everyone.
        validity = check_roster_validity(roster_shifts, historical_patterns)  # dict with 4 keys
        
        # score_roster returns None if an estimate is missing: then T and K are both None (instead of just one)
        if scores is None:
            cumulative_diff_hours = None
            expected_short_nights = None
            per_linked_shift = None  # [Added 2026-11-09]
        else:
            cumulative_diff_hours = scores["cumulative_diff_hours"]
            expected_short_nights = scores["expected_short_nights_given_main_sleep"]
            per_linked_shift = scores["per_linked_shift"]  # [Added 2026-11-09]
        
        # Results with worker identification, scores (if any), and roster feedback (validity)
        results.append({
            "worker_id": worker_id,
            "cumulative_diff_hours": cumulative_diff_hours,                   # T
            "expected_short_nights_given_main_sleep": expected_short_nights,  # K
            "per_linked_shift": per_linked_shift,  # [Added 2026-11-09] breakdown per linked shift type, or None
            "is_extrapolation": validity["is_extrapolation"],
            "unseen_transitions": validity["unseen_transitions"],
            "unseen_block_lengths": validity["unseen_block_lengths"],
            "uncertain_boundary_block_lengths": validity["uncertain_boundary_block_lengths"],
        })
    
    return results

def summarize_results(results):
    """
    Descriptive statistics over all workers of one roster.
    Not an objective for the scheduler: only a description.

    Parameters
    ----------
    results : list of dict
        The output of score_all_workers, one dict per worker.

    Returns
    -------
    dict:
        {
          "mean_cumulative_diff_hours": float,          # mean T over all workers
          "mean_expected_short_nights": float,          # mean K over all workers
          "worst_cumulative_diff_worker": str,          # worker_id with the lowest T 
          "worst_cumulative_diff_hours": float,         # that lowest T (negative, hence huge deviation from the mean)
          "worst_expected_short_nights_worker": str,    # worker_id with the highest K (highest probability short sleep)
          "worst_expected_short_nights": float,         # that highest K
          "range_cumulative_diff_hours": float,         # highest T minus lowest T (biggest difference T)
          "range_expected_short_nights": float,         # highest K minus lowest K (biggest difference K)
          "num_extrapolation": int,                     # workers with is_extrapolation True
          "per_shift_summary": dict,                    # statistics per linked shift type, see below
        }

    "per_shift_summary" [Added 2026-11-09]: linked shift type ("off", "early",
    "late", "night") -> dict with five keys, computed over the scored workers:
      "diff_contribution_hours"             cumulative T contribution
      "expected_short_nights_contribution"  cumulative K contribution
      "diff_per_night_hours"                personal T effect per night
      "p_short_per_night"                   personal probability of a short night per night
          each of these four -> {"mean", "worst_worker", "worst", "range"}:
          mean over workers (every worker counts once, whatever their
          number of nights), the worker with the worst value (lowest for
          the two T measures, highest for the two K measures) and that
          value, and highest minus lowest value.
          For Off, worst_worker and worst are None for the two T measures:
          T is 0 for Off by definition.
      "num_nights"                          number of linked nights per worker
          -> {"mean", "min", "max"}
    A measure is None when no worker has a value for it.
    """
    
    # With regard to T & K (see docstring): Keep only the workers who received a score.
    # A worker either has BOTH T and K, or neither (both None),
    # so checking T alone tells whether the worker was scored.
    scored = []
    for row in results:
        if row["cumulative_diff_hours"] is not None:
            scored.append(row)

    # [Added 2026-11-09] per linked shift type and measure: (worker_id, value) of every scored worker
    measures = ("num_nights", "diff_contribution_hours", "expected_short_nights_contribution",
                "diff_per_night_hours", "p_short_per_night")
    values_per_shift = {}
    for shift_type in ("off", "early", "late", "night"):
        values_per_shift[shift_type] = {}
        for measure in measures:
            values_per_shift[shift_type][measure] = []
    for row in scored:
        for shift_type in ("off", "early", "late", "night"):
            for measure in measures:
                value = row["per_linked_shift"][shift_type][measure]
                if value is not None:
                    values_per_shift[shift_type][measure].append((row["worker_id"], value))

    # Added 2026-11-09: per linked shift type and per measure: mean, lowest and highest over workers
    per_shift_statistics = {}
    for shift_type in ("off", "early", "late", "night"):
        per_shift_statistics[shift_type] = {}
        for measure in measures:
            pairs = values_per_shift[shift_type][measure]
            if len(pairs) == 0:
                per_shift_statistics[shift_type][measure] = None
                continue
            total = 0.0
            lowest_worker, lowest_value = pairs[0]
            highest_worker, highest_value = pairs[0]
            for worker_id, value in pairs:
                total += value
                if value < lowest_value:
                    lowest_worker, lowest_value = worker_id, value
                if value > highest_value:
                    highest_worker, highest_value = worker_id, value
            per_shift_statistics[shift_type][measure] = {
                "mean": total / len(pairs),
                "lowest_worker": lowest_worker,
                "lowest": lowest_value,
                "highest_worker": highest_worker,
                "highest": highest_value,
            }

    # [Added 2026-11-09] per linked shift type and per measure: mean, worst worker and range
    # T measures: worst = lowest (most negative); K measures: worst = highest
    worst_is_lowest = {
        "diff_contribution_hours": True,
        "expected_short_nights_contribution": False,
        "diff_per_night_hours": True,
        "p_short_per_night": False,
    }
    per_shift_summary = {}
    for shift_type in ("off", "early", "late", "night"):
        per_shift_summary[shift_type] = {}
        for measure in worst_is_lowest:
            statistics = per_shift_statistics[shift_type][measure]
            if statistics is None:
                per_shift_summary[shift_type][measure] = None
                continue
            if shift_type == "off" and measure in ("diff_contribution_hours", "diff_per_night_hours"):
                worst_worker, worst_value = None, None  # T is 0 for Off by definition: no worst worker
            elif worst_is_lowest[measure]:
                worst_worker, worst_value = statistics["lowest_worker"], statistics["lowest"]
            else:
                worst_worker, worst_value = statistics["highest_worker"], statistics["highest"]
            per_shift_summary[shift_type][measure] = {
                "mean": statistics["mean"],
                "worst_worker": worst_worker,
                "worst": worst_value,
                "range": statistics["highest"] - statistics["lowest"],
            }

    # [Added 2026-11-09] per linked shift type: number of linked nights per worker (mean, minimum, maximum)
    for shift_type in ("off", "early", "late", "night"):
        statistics = per_shift_statistics[shift_type]["num_nights"]
        if statistics is None:
            per_shift_summary[shift_type]["num_nights"] = None
            continue
        per_shift_summary[shift_type]["num_nights"] = {
            "mean": statistics["mean"],
            "min": statistics["lowest"],
            "max": statistics["highest"],
        }

    # Extrapolation counted over ALL workers, also those without a score
    num_extrapolation = 0
    for row in results:
        if row["is_extrapolation"]:
            num_extrapolation += 1
        
    # Mean T and mean K: add up the values, then divide by the number of scored workers
    total_cumulative_diff_hours = 0.0
    total_expected_short_nights = 0.0
    for row in scored:
        total_cumulative_diff_hours += row["cumulative_diff_hours"]
        total_expected_short_nights += row["expected_short_nights_given_main_sleep"]

    mean_cumulative_diff_hours = total_cumulative_diff_hours / len(scored) # 'None' not included
    mean_expected_short_nights = total_expected_short_nights / len(scored) # 'None' not included
    
    # Worst worker for T (lowest T) and for K (highest K), searched separately.
    # Start with the first scored worker, then replace whenever someone scores worse.
    worst_cumulative_diff_worker = scored[0]["worker_id"] # --> '0': first scored
    worst_cumulative_diff_hours = scored[0]["cumulative_diff_hours"]
    worst_expected_short_nights_worker = scored[0]["worker_id"]
    worst_expected_short_nights = scored[0]["expected_short_nights_given_main_sleep"]

    for row in scored:
        if row["cumulative_diff_hours"] < worst_cumulative_diff_hours:
            worst_cumulative_diff_hours = row["cumulative_diff_hours"]
            worst_cumulative_diff_worker = row["worker_id"]
        if row["expected_short_nights_given_main_sleep"] > worst_expected_short_nights:
            worst_expected_short_nights = row["expected_short_nights_given_main_sleep"]
            worst_expected_short_nights_worker = row["worker_id"]
    
    # Spread: highest value minus lowest value.
    # The lowest T and the highest K are the worst values found above,
    # so only the highest T and the lowest K still have to be found.
    highest_cumulative_diff_hours = scored[0]["cumulative_diff_hours"]
    lowest_expected_short_nights = scored[0]["expected_short_nights_given_main_sleep"]

    for row in scored:
        if row["cumulative_diff_hours"] > highest_cumulative_diff_hours:
            highest_cumulative_diff_hours = row["cumulative_diff_hours"]
        if row["expected_short_nights_given_main_sleep"] < lowest_expected_short_nights:
            lowest_expected_short_nights = row["expected_short_nights_given_main_sleep"]

    range_cumulative_diff_hours = highest_cumulative_diff_hours - worst_cumulative_diff_hours
    range_expected_short_nights = worst_expected_short_nights - lowest_expected_short_nights
    
    return {
    "mean_cumulative_diff_hours": mean_cumulative_diff_hours,
    "mean_expected_short_nights": mean_expected_short_nights,
    "worst_cumulative_diff_worker": worst_cumulative_diff_worker,
    "worst_cumulative_diff_hours": worst_cumulative_diff_hours,
    "worst_expected_short_nights_worker": worst_expected_short_nights_worker,
    "worst_expected_short_nights": worst_expected_short_nights,
    "range_cumulative_diff_hours": range_cumulative_diff_hours,
    "range_expected_short_nights": range_expected_short_nights,
    "num_extrapolation": num_extrapolation,
    "per_shift_summary": per_shift_summary,  # [Added 2026-11-09] statistics per linked shift type
    }


      
if __name__ == "__main__":
    # Score the historical roster of all workers.
    # Run from the project root:  python -m evaluator.score_all_workers

    data_dir = Path(__file__).resolve().parent.parent / "data"

    # Historical shifts -> one roster per worker, and the patterns for the validity flag
    assignment_records = pd.read_csv(data_dir / "historical_assignments.csv").to_dict("records") # load data
    rosters = get_rosters_from_records(assignment_records) # first argument for score_all_workers, obligatory
    historical_patterns = get_historical_patterns(rosters) # argument for score_all_workers, obligatory

    # Historical sleep -> LMM estimates per worker (the fitted model itself is not needed here)
    sleep_records = pd.read_csv(data_dir / "historical_sleep.csv").to_dict("records")
    cell_parameters, _ = estimate_cell_parameters_lmm(sleep_records) # argument for score_all_workers, obligatory

    results = score_all_workers(rosters, cell_parameters, historical_patterns)
    
    # One row per worker, rounded to 2 decimals for display only
    table = pd.DataFrame(results).drop(columns=["per_linked_shift"])  # [Changed 2026-11-09] breakdown shown in a separate table
    print(table.round(2).to_string(index=False))

    # [Added 2026-11-09] one row per worker per linked shift type
    breakdown_rows = []
    for row in results:
        if row["per_linked_shift"] is None:
            continue  # no scores for this worker, so no breakdown
        for linked_shift, values in row["per_linked_shift"].items():
            breakdown_rows.append({
                "worker_id": row["worker_id"],
                "linked_shift": linked_shift,
                "num_nights": values["num_nights"],
                "diff_contribution_hours": values["diff_contribution_hours"],
                "expected_short_nights_contribution": values["expected_short_nights_contribution"],
                "diff_per_night_hours": values["diff_per_night_hours"],
                "p_short_per_night": values["p_short_per_night"],
                "p_short_increase_vs_off": values["p_short_increase_vs_off"],
            })

    breakdown_table = pd.DataFrame(breakdown_rows)  # [Added 2026-11-09] 120 rows: 30 workers x 4 linked shift types
    print()
    print("Breakdown per worker and linked shift type:")
    print(breakdown_table.round({
        "diff_contribution_hours": 2,
        "expected_short_nights_contribution": 2,
        "diff_per_night_hours": 2,
        "p_short_per_night": 3,
        "p_short_increase_vs_off": 3,
    }).to_string(index=False))

    # Descriptive statistics over all workers, one per line
    summary = summarize_results(results)
    print()
    print("Summary over all workers:")
    for name, value in summary.items():
        if name == "per_shift_summary":
            continue  # [Added 2026-11-09] shown in a separate table below
        if isinstance(value, float):
            value = round(value, 2)  # rounded for display only
        print(f"  {name}: {value}")

    # [Added 2026-11-09] summary per linked shift type: one row per measure and linked shift type
    summary_rows = []
    for measure in ("diff_contribution_hours", "expected_short_nights_contribution",
                    "diff_per_night_hours", "p_short_per_night"):
        if measure == "p_short_per_night":
            decimals = 3  # probabilities: 3 decimals
        else:
            decimals = 2
        for shift_type in ("off", "early", "late", "night"):
            statistics = summary["per_shift_summary"][shift_type][measure]
            if statistics is None:
                continue
            worst = statistics["worst"]
            if worst is not None:
                worst = round(worst, decimals)
            summary_rows.append({
                "measure": measure,
                "linked_shift": shift_type,
                "mean": round(statistics["mean"], decimals),
                "worst_worker": statistics["worst_worker"],
                "worst": worst,
                "range": round(statistics["range"], decimals),
            })

    print()
    print("Summary per linked shift type:")
    print(pd.DataFrame(summary_rows).to_string(index=False))  # [Added 2026-11-09]

    # [Added 2026-11-09] number of linked nights per worker, per linked shift type
    nights_rows = []
    for shift_type in ("off", "early", "late", "night"):
        nights = summary["per_shift_summary"][shift_type]["num_nights"]
        if nights is None:
            continue
        nights_rows.append({
            "linked_shift": shift_type,
            "mean": round(nights["mean"], 2),
            "min": nights["min"],
            "max": nights["max"],
        })
    print()
    print("Number of linked nights per worker:")
    print(pd.DataFrame(nights_rows).to_string(index=False))
      