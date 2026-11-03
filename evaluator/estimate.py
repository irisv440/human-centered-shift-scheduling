# -*- coding: utf-8 -*-
"""
Created on Wed Oct 28 11:51:17 2026

@author: irisv

evaluator/estimate.py

Evaluator v0, step 1: estimate the cell parameters per worker.

A "cell" is one combination of worker and linked shift, for example
(W007, night). For every cell we compute:

- mean_hours:        the average sleep duration of that worker after that
                     linked shift (mu-hat in the plan)
- num_nights:        how many valid nights that average is based on

and per worker, for early / late / night:

- diff_vs_off_hours: mean after that shift minus the worker's own Off mean
                     (D-hat in the plan, signal B). Negative = shorter sleep.
and per worker:
- sigma_hours: night-to-night standard deviation around the worker's own shift
                    means (sigma-hat). Denominator: valid nights munus the number
                    of non-empty cells. None when no degrees of freedom are left.

Why only averages?
    The per-worker regression in the plan has one dummy per night type.
    For such a model, the OLS estimates are exactly the cell averages.
    So we can compute the averages directly: every number can be checked by hand.

Not in v0 (comes later): the probability of short sleep
(signal A), standard errors.

The evaluator only uses observable data (historical_sleep.csv or the API).
It never reads latent_sleep_profiles.csv: that is ground truth, used only
by a separate validation script.
"""

import numpy as np


# The four linked-shift categories, written the same way as in the data
# and in the API ("early", "late", "night", "off").
LINKED_SHIFTS = ("off", "early", "late", "night")

# The shifts that are compared with Off (Off itself is the reference).
WORK_SHIFTS = ("early", "late", "night")


def estimate_cell_parameters(sleep_records):
    """
    Estimate mean sleep duration per worker and linked shift,
    and the difference with the worker's own Off nights.

    Parameters
    ----------
    sleep_records : list of dict
        One dict per worker-night, with at least these keys:
        worker_id, linked_shift, sleep_duration_hours, no_main_sleep_episode.
        (Same shape as the records the API already works with.)

    Returns
    -------
    dict
        One entry per worker, for example:

        {
          "W001": {
            "mean_hours":        {"off": 8.0, "early": 6.2, "late": 7.6, "night": 5.6},
            "num_nights":        {"off": 3,   "early": 3,   "late": 3,   "night": 3},
            "diff_vs_off_hours": {"early": -1.8, "late": -0.4, "night": -2.4},
            "sigma_hours": 0.9,
          },
          ...
        }

        A cell without valid nights gets mean_hours = None, and every
        difference that needs that mean also becomes None.

        Values are NOT rounded here: rounding is only for display.
        Rounding inside an estimate would add small errors to everything
        computed from it later (the roster score sums many of these values).
    """

    # --- Step A: collect the durations per worker and per linked shift ---
    #
    # durations_by_worker becomes:
    #   {"W001": {"off": [8.51, ...], "early": [...], "late": [...], "night": [...]},
    #    "W002": {...}, ...}
    durations_by_worker = {}

    for record in sleep_records:
        worker_id = record["worker_id"]
        linked_shift = record["linked_shift"]

        # First time we see this worker: create an empty list per shift.
        # This way every worker always has all four shifts as keys,
        # even if a shift never occurs for them.
        if worker_id not in durations_by_worker:
            durations_by_worker[worker_id] = {shift: [] for shift in LINKED_SHIFTS}

        # Nights without a main sleep episode have no duration (NaN / None).
        # They are left out of every estimate (strategy B in the plan).
        # Check the flag FIRST, before touching the duration.
        if record["no_main_sleep_episode"]:
            continue

        durations_by_worker[worker_id][linked_shift].append(
            float(record["sleep_duration_hours"])
        )
    

    # --- Step B: per worker, compute means, counts and differences vs Off ---
    cell_parameters = {}

    for worker_id, durations_by_shift in durations_by_worker.items():

        # Cell means (mu-hat) and number of nights behind each mean
        mean_hours = {}
        num_nights = {}
        for shift in LINKED_SHIFTS:
            durations = durations_by_shift[shift]
            num_nights[shift] = len(durations)
            # np.mean of an empty list gives a warning and NaN; use None instead
            mean_hours[shift] = float(np.mean(durations)) if durations else None

        # Signal B: difference with the worker's own Off mean (D-hat)
        mean_off = mean_hours["off"]
        diff_vs_off_hours = {}
        for shift in WORK_SHIFTS:
            if mean_hours[shift] is not None and mean_off is not None:
                diff_vs_off_hours[shift] = mean_hours[shift] - mean_off
            else:
                # Difference only possible if both means exist
                diff_vs_off_hours[shift] = None
                
        # Sigma-hat: night-to-night SD around the workers own shift means
        sum_squares = 0.0
        num_valid_nights = 0
        num_means = 0
        for shift  in LINKED_SHIFTS:
            durations = durations_by_shift[shift]
            if durations: # if empty for this shift: no mean estimated (no df lost either)
                for duration in durations:
                    sum_squares += (duration - mean_hours[shift])**2
                num_valid_nights += len(durations)
                num_means += 1
        
        degrees_of_freedom = num_valid_nights - num_means
        if degrees_of_freedom > 0: # there is at least one mean
            sigma_hours = float(np.sqrt(sum_squares/degrees_of_freedom))
        else:
            sigma_hours = None
        
        cell_parameters[worker_id] = {
            "mean_hours": mean_hours,
            "num_nights": num_nights,
            "diff_vs_off_hours": diff_vs_off_hours,
            "sigma_hours": sigma_hours,
        }

    return cell_parameters


if __name__ == "__main__":
    # Quick look at the estimates for the real (synthetic) data.
    # Run from the project root:  python -m evaluator.estimate
    from pathlib import Path
    import pandas as pd

    data_path = Path(__file__).resolve().parent.parent / "data" / "historical_sleep.csv"
    sleep = pd.read_csv(data_path)

    # Turn the DataFrame into a list of dicts, the input shape of the function
    records = sleep.to_dict("records")

    parameters = estimate_cell_parameters(records)

    # One row per worker, rounded to 2 decimals for display only
    rows = []
    for worker_id, p in sorted(parameters.items()):
        rows.append({
            "worker_id": worker_id,
            "mean_off": p["mean_hours"]["off"],
            "D_early": p["diff_vs_off_hours"]["early"],
            "D_late": p["diff_vs_off_hours"]["late"],
            "D_night": p["diff_vs_off_hours"]["night"],
            "n_off": p["num_nights"]["off"],
            "n_early": p["num_nights"]["early"],
            "n_late": p["num_nights"]["late"],
            "n_night": p["num_nights"]["night"],
        })

    print(pd.DataFrame(rows).round(2).to_string(index=False))
