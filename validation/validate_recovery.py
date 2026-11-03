# -*- coding: utf-8 -*-
"""
validation/validate_recovery.py

Recovery check: does the evaluator get back what the generator put in?

Compares two estimators with the ground truth, for all workers:
- OLS: evaluator/estimate.py      (plain averages per worker, no pooling)
- LMM: evaluator/estimate_lmm.py  (mixed model, partial pooling)

This is the ONLY place that reads latent_sleep_profiles.csv (ground truth).
The evaluator itself never does. That is why this script lives in its own
folder, outside evaluator/.

Run from the project root:  python -m validation.validate_recovery

What is compared (per worker, then averaged over workers):
- mu_off:   expected sleep on Off nights
- D_early, D_late, D_night: difference vs Off (signal B)
- sigma:    night-to-night standard deviation (needed for signal A)
- short-night probability per linked shift (signal A, given a main sleep
  episode): the estimated probability vs p_latent. p_latent is the same
  formula, filled in with the true mean and the true sigma of the worker.

Error metric: mean absolute error (MAE) over the workers.
For mu_off, D_early, D_late, D_night and sigma the MAE is in hours.
Example: MAE D_night = 0.20 means the estimated Night effect is on average
12 minutes away from the true Night effect of that worker.

For the short-night probability the MAE is a difference in probability.
Example: MAE = 0.04 means the estimated probability is on average 0.04
away from p_latent. It is also shown which five worker-shift combinations
have the largest error, per model.

Caveats (see section 7 of the plan):
- The generator resamples durations > 12 h and drops durations <= 0 h.
  This slightly shifts true means, so a small error remains even with
  infinite data. For the same reason p_latent is an approximation: its
  formula assumes a normal distribution without these two rules.
- The models have the same form as the generator. Good recovery shows the
  code works and the data are sufficient, not that the model is right for
  real sleep.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from evaluator.estimate import estimate_cell_parameters # import OLS function
from evaluator.estimate_lmm import estimate_cell_parameters_lmm # import LMM function
from evaluator.short_sleep import p_short_given_main_sleep 


DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Fixed duration effects used by the generator
# (SHIFT_EFFECTS in data_generation/generate_historical_sleep.py).
# Copied here on purpose, so validation does not import generator code.
OFF_EFFECT = 0.7
LATE_EFFECT = 0.2

WORK_SHIFTS = ("early", "late", "night")
COLUMNS = ["mu_off", "D_early", "D_late", "D_night"]


# --- Ground truth ------------------------------------------------------------

def load_truth():
    """
    Compute the true values per worker from the latent profiles.

    In the generator, a night has mean  'latent_duration + shift_effect',
    with shift_effect = +0.7 for Off, +0.2 for Late, and worker-specific
    values for Early and Night. So, compared with Off:

        D_early = early_effect - 0.7
        D_late  = 0.2 - 0.7 = -0.5        (the same for everyone)
        D_night = night_effect - 0.7
    """
    profiles = pd.read_csv(DATA_DIR / "latent_sleep_profiles.csv").set_index("worker_id")

    truth = pd.DataFrame(index=profiles.index)
    truth["mu_off"] = profiles["latent_sleep_duration_hours"] + OFF_EFFECT
    truth["D_early"] = profiles["latent_early_duration_effect_hours"] - OFF_EFFECT
    truth["D_late"] = LATE_EFFECT - OFF_EFFECT
    truth["D_night"] = profiles["latent_night_duration_effect_hours"] - OFF_EFFECT
    truth["sigma"] = profiles["latent_duration_variability_hours"]
    
    # 2026-11-03
    # True mean sleep per linked shift: the generator formula without the noise
    # duration_noise is sampled afterwards (in generate_historical_sleep.py)
    truth["true_mean_off"] = profiles["latent_sleep_duration_hours"] + OFF_EFFECT
    truth["true_mean_early"] = profiles["latent_sleep_duration_hours"] + profiles["latent_early_duration_effect_hours"]
    truth["true_mean_late"] = profiles["latent_sleep_duration_hours"] + LATE_EFFECT
    truth["true_mean_night"] = profiles["latent_sleep_duration_hours"] + profiles["latent_night_duration_effect_hours"]
    return truth


# --- Short-night probabilities ------------------------------------------------

def get_latent_probabilities(truth):
      """
      Compute p_latent: the short-night probability from the true values.

      truth: DataFrame from load_truth, one row per worker. Used columns:
             true_mean_off, true_mean_early, true_mean_late, true_mean_night, sigma

      Returns a DataFrame with one row per worker and one column per linked
      shift (off, early, late, night). Each cell is p_latent for that combination.
      """

      rows = {}
      for worker_id in truth.index:
          rows[worker_id] = {}
          for shift in ("off", "early", "late", "night"):
              rows[worker_id][shift] = p_short_given_main_sleep(
                  truth.loc[worker_id, "true_mean_" + shift],
                  truth.loc[worker_id, "sigma"],
              )

      # orient="index": the dict keys (worker ids) become the row index
      return pd.DataFrame.from_dict(rows, orient="index")

# Estimated probabilities to compare with the latent probabilities
def get_estimated_probabilities(cell_parameters):
    """
    Compute the short-night probability from the estimates of one model.

    cell_parameters: output of estimate_cell_parameters or
                     estimate_cell_parameters_lmm (dict per worker).
                     Used keys: mean_hours, sigma_hours

    Returns a DataFrame with one row per worker and one column per linked
    shift (off, early, late, night), the same shape as latent_probabilities.
    """
    rows = {}
    for worker_id, parameters in cell_parameters.items():
        rows[worker_id] = {}
        for shift in ("off", "early", "late", "night"):
            rows[worker_id][shift] = p_short_given_main_sleep(
                parameters["mean_hours"][shift],
                parameters["sigma_hours"],
            )
    # orient="index": the dict keys (worker ids) become the row index
    return pd.DataFrame.from_dict(rows, orient="index")


# 2026-11-03
def get_largest_probability_errors(p_estimated, p_latent, truth):
    """
    Find the five worker-shift combinations with the largest probability error.

    p_estimated: DataFrame from get_estimated_probabilities (one model)
    p_latent:    DataFrame from get_latent_probabilities
    truth:       DataFrame from load_truth. Used columns: true_mean_off,
                 true_mean_early, true_mean_late, true_mean_night, sigma

    Returns a DataFrame with five rows, the largest error first.
    """
    rows = []
    for worker_id in p_latent.index:
        for shift in p_latent.columns:
            latent = p_latent.loc[worker_id, shift]
            estimated = p_estimated.loc[worker_id, shift]
            rows.append({
                "worker_id": worker_id,
                "shift": shift,
                "true_mean": truth.loc[worker_id, "true_mean_" + shift],
                "sigma": truth.loc[worker_id, "sigma"],
                "p_latent": latent,
                "p_estimated": estimated,
                "abs_error": abs(estimated - latent),
            })

    errors = pd.DataFrame(rows)
    return errors.sort_values("abs_error", ascending=False).head(5)

def estimates_to_frame(cell_parameters):
    """Turn the evaluator output (dict per worker) into a DataFrame."""
    rows = {}
    for worker_id, p in cell_parameters.items():
        rows[worker_id] = {
            "mu_off": p["mean_hours"]["off"],
            "D_early": p["diff_vs_off_hours"]["early"],
            "D_late": p["diff_vs_off_hours"]["late"],
            "D_night": p["diff_vs_off_hours"]["night"],
        }
    # orient="index": the dict keys (worker ids) become the row index
    return pd.DataFrame.from_dict(rows, orient="index")

# --- One validation run -----------------------------------------------------

def run_validation(records, truth, label):
    """Fit both estimators on `records`, compare with the truth, print MAE."""
    print(f"\n=== {label} ===")

    # Both estimators get exactly the same records
    ols_parameters = estimate_cell_parameters(records)
    ols = estimates_to_frame(ols_parameters)
    lmm_parameters, lmm_result = estimate_cell_parameters_lmm(records) # Also includes residual sigma per worker using 'residual_sigma_per_worker' function
    lmm = estimates_to_frame(lmm_parameters)
    print("LMM converged:", lmm_result.converged)

    # Same row order everywhere, so the subtraction compares the same worker
    workers = truth.index
    ols, lmm = ols.loc[workers], lmm.loc[workers]

    # --- Means and differences: MAE per column -------------------------------
    mae = pd.DataFrame({
        "OLS": (ols[COLUMNS] - truth[COLUMNS]).abs().mean(),
        "LMM": (lmm[COLUMNS] - truth[COLUMNS]).abs().mean(),
    })
    print("\nMAE in hours (lower is better):")
    print(mae.round(3).to_string())

    # --- Sigma (residual sd per worker) -----------------------------------------------------------------
    sigma_ols = {}
    for worker_id, parameters in ols_parameters.items():
        sigma_ols[worker_id] = parameters["sigma_hours"]
    sigma_ols = pd.Series(sigma_ols)
    
    
    # LMM: (a) the one shared sigma of the model (result.scale = variance),
    #      (b) per worker, the spread of that worker's LMM residuals.
    # Changed 2026-10-28: sigma_hours in the LMM output is now (b),
    # so (b) is read from the output and (a) from the model itself.
    sigma_lmm_shared = pd.Series(np.sqrt(lmm_result.scale), index=workers) # from LMM
    # LMM: sigma per worker from estimate_lmm.py
    sigma_lmm_worker = {}
    for worker_id, parameters in lmm_parameters.items():
        sigma_lmm_worker[worker_id] = parameters["sigma_hours"]
        sigma_lmm_worker = pd.Series(sigma_lmm_worker)

    true_sigma = truth["sigma"] # Per worker, directly from profiles["latent_duration_variability_hours"]
    sigma_mae = pd.Series({
        "OLS, per worker": (sigma_ols.loc[workers] - true_sigma).abs().mean(),
        "LMM, shared": (sigma_lmm_shared - true_sigma).abs().mean(),
        "LMM residuals, per worker": (sigma_lmm_worker.loc[workers] - true_sigma).abs().mean(),
    })
    print("\nMAE sigma in hours:")
    print(sigma_mae.round(3).to_string())
    
    # --- Short-night probability: estimates vs p_latent ------------------------
    # 2026-11-03
    # Three DataFrames: one row per worker, one column per linked shift
    p_latent = get_latent_probabilities(truth)
    p_ols = get_estimated_probabilities(ols_parameters).loc[workers]
    p_lmm = get_estimated_probabilities(lmm_parameters).loc[workers]
  
    # One row per linked shift. The subtraction matches on worker and shift.
    p_table = pd.DataFrame({
        "mean p_latent": p_latent.mean(),
        "MAE OLS": (p_ols - p_latent).abs().mean(),
        "MAE LMM": (p_lmm - p_latent).abs().mean(),
    })
    print("\nShort-night probability per linked shift (MAE: lower is better):")
    print(p_table.round(3).to_string())

    print("\nFive largest probability errors, OLS:")
    print(get_largest_probability_errors(p_ols, p_latent, truth).round(3).to_string(index=False))
    print("\nFive largest probability errors, LMM:")
    print(get_largest_probability_errors(p_lmm, p_latent, truth).round(3).to_string(index=False))

    # --- Largest errors: which workers are hardest? ----------------------------
    worst = pd.DataFrame({
        "true_D_night": truth["D_night"],
        "OLS_D_night": ols["D_night"],
        "LMM_D_night": lmm["D_night"],
        "true_sigma": true_sigma, # per worker
    })
    worst["LMM_abs_error"] = (worst["LMM_D_night"] - worst["true_D_night"]).abs()
    print("\nFive largest LMM errors for D_night:")
    print(worst.sort_values("LMM_abs_error", ascending=False).head(5).round(2).to_string())

    return mae


def main():
    truth = load_truth()
    sleep = pd.read_csv(DATA_DIR / "historical_sleep.csv")

    # Run 1: all 84 nights (about 21 per linked shift)
    run_validation(sleep.to_dict("records"), truth, "All data (84 nights)") # All nights

    # Run 2: only the first 28-day cycle (about 7 nights per linked shift).
    # Errors should grow, roughly by sqrt(3) = 1.7 (section 7 of the plan).
    first_date = pd.to_datetime(sleep["sleep_date"]).min()
    in_first_cycle = pd.to_datetime(sleep["sleep_date"]) < first_date + pd.Timedelta(days=28)
    run_validation(sleep[in_first_cycle].to_dict("records"), truth, "First cycle only (28 nights)") # Only the first 28 days


if __name__ == "__main__":
    main()
