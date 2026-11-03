# -*- coding: utf-8 -*-
"""
evaluator/estimate_lmm.py

Evaluator v1, step 1 (LMM version): estimate per worker how long they sleep
after each linked shift, with a linear mixed model (statsmodels MixedLM).

This file replaces nothing: evaluator/estimate.py (plain per-worker averages)
stays available as the simple alternative.

The model
---------
For worker i on night t:

    duration_it = (b0 + u0_i)
                  + (bE + uE_i) * is_early_it
                  + (bL + uL_i) * is_late_it
                  + (bN + uN_i) * is_night_it
                  + noise_it

- is_early / is_late / is_night: 1 if the linked shift of that night is
  Early / Late / Night, else 0. Off is the reference (all three are 0).
- b0, bE, bL, bN: FIXED effects, the same for everyone.
  b0 = average Off sleep, bE/bL/bN = average difference vs Off.
- u0_i, uE_i, uL_i, uN_i: RANDOM effects, the personal deviation of worker i.
  These are "shrunk" towards 0 when a worker has little or noisy data
  (partial pooling).
- noise_it ~ N(0, sigma^2): ONE sigma shared by all workers (a limitation
  of MixedLM; per-worker sigma is not part of this model).
  [Added on 2026-10-28] Because one shared sigma recovered the true
  per-worker sigma poorly (validation: MAE 0.33 h), the output now holds a
  sigma PER WORKER, computed afterwards from that worker's LMM residuals
  (see residual_sigma_per_worker). Validation: MAE 0.057 h.

What the evaluator uses per worker i:
    Off mean:          mu_off   = b0 + u0_i
    Difference vs Off: D_s      = b_s + u_s_i         ('signal B')
    Mean after shift:  mu_s     = mu_off + D_s

Output has the same structure as estimate.py, so later steps (roster scoring) work with either version.

The evaluator only uses observable data. It never reads latent_sleep_profiles.csv (ground truth).
"""

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf


# Same category names as in the data and the API
LINKED_SHIFTS = ("off", "early", "late", "night")
WORK_SHIFTS = ("early", "late", "night")


def prepare_data(sleep_records):
    """
    Turn the sleep records into a DataFrame the model can use.

    - Drops nights without a main sleep episode (no duration; strategy B).
    - Adds the dummy columns is_early, is_late, is_night (0/1).
    """
    data = pd.DataFrame(sleep_records)

    # Keep only nights with a main sleep episode.
    # astype(bool): the CSV / API may deliver the flag as a bool or 0/1.
    data = data[~data["no_main_sleep_episode"].astype(bool)].copy() # filter
    data["sleep_duration_hours"] = data["sleep_duration_hours"].astype(float)

    # One dummy column per work shift: 1 if this night is linked to that shift
    for shift in WORK_SHIFTS: # Creates one column for each workshift --> 3 columns (early, late, night)
        data[f"is_{shift}"] = (data["linked_shift"] == shift).astype(int)

    return data


def fit_lmm(data, random_slopes=WORK_SHIFTS):
    """
    Fit the mixed model on prepared data.

    Parameters
    ----------
    data : DataFrame from prepare_data()
    random_slopes : which shifts get a personal (random) effect per worker.
        Default: all three. If the fit gives a convergence warning, a
        likely cause is a shift where workers hardly differ (in the
        synthetic data: Late). Then try random_slopes=("early", "night"):
        Late keeps its fixed effect, but everyone gets the same Late effect.

    Returns
    -------
    statsmodels MixedLMResults (use .summary() to inspect it)
    """
    # Fixed part: always all three shift dummies
    formula = "sleep_duration_hours ~ is_early + is_late + is_night"

    # Random part: an intercept per worker ("1") plus the chosen slopes.
    # Example: "~ 1 + is_early + is_late + is_night"
    re_formula = "~ 1" + "".join(f" + is_{shift}" for shift in random_slopes)

    model = smf.mixedlm(formula,data,groups=data["worker_id"],   # one group = one worker
        re_formula=re_formula,
    )

    # REML as standard estimation method for variance components
    return model.fit(reml=True)


# Added 2026-10-28: per-worker sigma from the LMM residuals
def residual_sigma_per_worker(data, result, num_means=4):
    """
    Night-to-night standard deviation per worker, from the LMM residuals.

    Residual of a night = observed duration - the model's prediction for
    that worker and shift (fixed + personal effects).

        sigma_i = sqrt( sum of squared residuals of worker i / (n_i - num_means) )

    num_means = 4: one estimated mean per linked shift, the same
    denominator as in section 4 of the plan.

    Returns a dict {worker_id: sigma or None}. None when a worker has
    num_means valid nights or fewer (no degrees of freedom left).
    """
    
    # result.resid follows the row order of `data`, so the positions match
    squared = pd.Series(np.asarray(result.resid) ** 2, index=data["worker_id"].to_numpy())
    grouped = squared.groupby(level=0)
    sum_squares = grouped.sum()
    num_nights = grouped.size()

    sigma = {}
    for worker_id in sum_squares.index:
        degrees_of_freedom = num_nights[worker_id] - num_means
        if degrees_of_freedom > 0:
            sigma[worker_id] = float(np.sqrt(sum_squares[worker_id] / degrees_of_freedom))
        else:
            sigma[worker_id] = None
    return sigma


def estimate_cell_parameters_lmm(sleep_records, random_slopes=WORK_SHIFTS):
    """
    Estimate mean sleep per worker and linked shift with the LMM.

    Parameters
    ----------
    sleep_records : list of dict
        Keys: worker_id, linked_shift, sleep_duration_hours,
        no_main_sleep_episode (same shape as for estimate.py).
    random_slopes : passed on to fit_lmm().

    Returns
    -------
    (cell_parameters, result)

    cell_parameters: dict per worker, same keys as estimate.py plus sigma:
        {
          "W001": {
            "mean_hours":        {"off": ..., "early": ..., "late": ..., "night": ...},
            "num_nights":        {"off": ..., "early": ..., "late": ..., "night": ...},
            "diff_vs_off_hours": {"early": ..., "late": ..., "night": ...},
            "sigma_hours":       ...,   # per worker, from LMM residuals [changed 2026-10-28 17:26; was shared]
          },
          ...
        }
        Note: unlike estimate.py, a cell with 0 nights still gets an
        estimate (the group effect). num_nights = 0 shows it is not based
        on that worker's own data.

    result: the fitted statsmodels object, for inspection
        (result.summary(), result.converged). The model's single shared
        sigma is sqrt(result.scale).
    """
    data = prepare_data(sleep_records) # returns filtered data, with dummies for early, late and night shift
    result = fit_lmm(data, random_slopes = random_slopes) # formula, model specification, fit, return params

    # Fixed effects: a Series with index Intercept, is_early, is_late, is_night
    fixed = result.fe_params

    # Changed 2026-10-28: sigma per worker instead of the shared
    # sqrt(result.scale)
    sigma = residual_sigma_per_worker(data, result) # Get residual standard deviation/worker

    # Number of valid nights per worker and shift.
    # unstack + reindex: every worker gets all four shifts, missing = 0.
    counts = (
        data.groupby(["worker_id", "linked_shift"]).size()
        .unstack(fill_value=0)
        .reindex(columns=list(LINKED_SHIFTS), fill_value=0)
    )

    cell_parameters = {}

    # result.random_effects: dict {worker_id: Series of personal deviations}.
    # Careful: statsmodels calls the personal intercept "Group" (not
    # "Intercept" as in the fixed effects); the slopes keep their names
    # (is_early, ...).
    for worker_id, personal in result.random_effects.items():

        # Off mean = fixed intercept + personal intercept deviation
        mean_off = fixed["Intercept"] + personal["Group"]

        diff_vs_off_hours = {}
        for shift in WORK_SHIFTS:
            column = f"is_{shift}"
            # .get(column, 0.0): a shift without random slope has no
            # personal deviation, only the fixed effect
            diff_vs_off_hours[shift] = float(fixed[column] + personal.get(column, 0.0))

        mean_hours = {"off": float(mean_off)}
        for shift in WORK_SHIFTS:
            mean_hours[shift] = float(mean_off + diff_vs_off_hours[shift])

        cell_parameters[worker_id] = {
            "mean_hours": mean_hours,
            "num_nights": {shift: int(counts.loc[worker_id, shift]) for shift in LINKED_SHIFTS},
            "diff_vs_off_hours": diff_vs_off_hours,
            "sigma_hours": sigma[worker_id],   # [changed 2026-10-28 17:26] per worker
        }

    return cell_parameters, result


if __name__ == "__main__":
    # Fit the model on the synthetic data and show the results.
    # Run from the project root:  python -m evaluator.estimate_lmm
    from pathlib import Path

    data_path = Path(__file__).resolve().parent.parent / "data" / "historical_sleep.csv"
    records = pd.read_csv(data_path).to_dict("records") # convert to dictionary

    parameters, result = estimate_cell_parameters_lmm(records) # return model.fit(reml=True)

    print(result.summary())
    print("Converged:", result.converged)

    # One row per worker, rounded to 2 decimals for display only
    rows = []
    for worker_id, p in sorted(parameters.items()):
        rows.append({
            "worker_id": worker_id,
            "mean_off": p["mean_hours"]["off"],
            "D_early": p["diff_vs_off_hours"]["early"],
            "D_late": p["diff_vs_off_hours"]["late"],
            "D_night": p["diff_vs_off_hours"]["night"],
        })
    print(pd.DataFrame(rows).round(2).to_string(index=False))
