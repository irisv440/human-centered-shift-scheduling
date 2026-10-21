"""
generate_workers.py

Generate the synthetic worker population for the
Human-Centered Shift Scheduling MVP.

Outputs
-------
data/workers.csv
    Operational worker data that can later be loaded into PostgreSQL.

data/latent_sleep_profiles.csv
    Hidden synthetic ground truth used only to generate historical sleep data.
    The future evaluator/optimizer should NOT read this file directly.
    
data/worker_profiles.csv
    Worker profile information available to the HCSS system.
    sleep_need_hours is derived from the synthetic latent sleep-duration
    parameter and represents a proxy for individual sleep need.
"""

from pathlib import Path
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

SEED = 42
N_WORKERS = 30
CONTRACT_HOURS_WEEK = 38

ROLE_COUNTS = {
    "operator": 18,
    "senior_operator": 8,
    "supervisor": 4,
}

# Preferred sleep duration:
# UK Biobank accelerometer-derived sleep duration
# mean = 7.30 h, SD = 0.86 h, observed range = 3.00–11.87 h
SLEEP_DURATION_MEAN = 7.30
SLEEP_DURATION_SD = 0.86
SLEEP_DURATION_MIN = 3.00
SLEEP_DURATION_MAX = 11.87

# Worker-specific within-person sleep-duration variability:
# mean SD = 0.93 h, between-person SD = 0.57 h
DURATION_VARIABILITY_MEAN = 0.93
DURATION_VARIABILITY_SD = 0.57

# Worker-specific within-person sleep-midpoint variability:
# mean SD = 1.00 h, between-person SD = 0.70 h
MIDPOINT_VARIABILITY_MEAN = 1.00
MIDPOINT_VARIABILITY_SD = 0.70

# Systematic effect of Early/Night shifts on sleep duration (hours).
# Group means match the fixed effects previously used for all workers;
# individual_sd adds worker-specific heterogeneity on top of that mean.
EARLY_DURATION_EFFECT_MEAN = -1.5
EARLY_DURATION_EFFECT_SD = 0.4

NIGHT_DURATION_EFFECT_MEAN = -1.4
NIGHT_DURATION_EFFECT_SD = 0.5


# Approximate MSFsc distribution reconstructed from Figure 1
# in Roenneberg et al. (2019).
# We keep the midpoint values on 30-minute steps for the MVP.
MSFSC_TIMES = [
    "23:00", "23:30", "00:00", "00:30", "01:00",
    "01:30", "02:00", "02:30", "03:00", "03:30",
    "04:00", "04:30", "05:00", "05:30", "06:00",
    "06:30", "07:00", "07:30", "08:00", "08:30",
    "09:00", "09:30", "10:00", "10:30", "11:00",
]

MSFSC_WEIGHTS = np.array([
    0.10, 0.20, 0.50, 1.00, 1.60,
    2.00, 4.00, 8.50, 13.30, 15.30,
    14.20, 11.70, 9.20, 6.80, 4.60,
    3.00, 1.80, 1.20, 0.70, 0.40,
    0.25, 0.15, 0.10, 0.05, 0.05,
], dtype=float)

# Normalize because the hand-read percentages sum to approximately, not exactly, 100%.
MSFSC_PROBABILITIES = MSFSC_WEIGHTS / MSFSC_WEIGHTS.sum()


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def sample_positive_normal(rng, mean, sd, size):
    """
    Sample from a Normal distribution truncated at 0 by rejection sampling.
    This is used for SD-like parameters, which cannot be negative.
    """
    values = rng.normal(mean, sd, size)

    while np.any(values < 0):
        mask = values < 0
        values[mask] = rng.normal(mean, sd, mask.sum())

    return values


def sample_bounded_normal(rng, mean, sd, lower, upper, size):
    """
    Sample from a Normal distribution restricted to an observed empirical range.
    """
    values = rng.normal(mean, sd, size)

    invalid = (values < lower) | (values > upper)

    while np.any(invalid):
        values[invalid] = rng.normal(mean, sd, invalid.sum())
        invalid = (values < lower) | (values > upper)

    return values


# ---------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------

def main():
    rng = np.random.default_rng(SEED)

    # ----- worker IDs -----
    worker_ids = [f"W{i:03d}" for i in range(1, N_WORKERS + 1)]

    # ----- roles -----
    roles = []
    for role, count in ROLE_COUNTS.items():
        roles.extend([role] * count)

    roles = np.array(roles, dtype=object)
    rng.shuffle(roles)

    workers = pd.DataFrame({
        "worker_id": worker_ids,
        "role": roles,
        "contract_hours_week": CONTRACT_HOURS_WEEK,
    })

    # ----- hidden latent sleep profiles -----
    latent_midpoints = rng.choice(
        MSFSC_TIMES,
        size=N_WORKERS,
        p=MSFSC_PROBABILITIES,
    )

    latent_sleep_duration = sample_positive_normal(
        rng,
        mean=SLEEP_DURATION_MEAN,
        sd=SLEEP_DURATION_SD,
        #lower=SLEEP_DURATION_MIN,
        #upper=SLEEP_DURATION_MAX,
        size=N_WORKERS,
    )

    latent_duration_variability = sample_positive_normal(
        rng,
        mean=DURATION_VARIABILITY_MEAN,
        sd=DURATION_VARIABILITY_SD,
        size=N_WORKERS,
    )

    latent_midpoint_variability = sample_positive_normal(
        rng,
        mean=MIDPOINT_VARIABILITY_MEAN,
        sd=MIDPOINT_VARIABILITY_SD,
        size=N_WORKERS,
    )
    # Belangrijk: deze effecten zijn werknemer-specifiek maar constant over de dagen. 
    # De dagelijkse variatie wordt afzonderlijk gegenereerd in generate_historical_sleep.py.
    latent_early_duration_effect = rng.normal(
        EARLY_DURATION_EFFECT_MEAN,
        EARLY_DURATION_EFFECT_SD,
        size=N_WORKERS,
    )

    latent_night_duration_effect = rng.normal(
        NIGHT_DURATION_EFFECT_MEAN,
        NIGHT_DURATION_EFFECT_SD,
        size=N_WORKERS,
    )
    # Early duration effect hours and night duration effect hours:
#         Correct. Beide arrays worden als afzonderlijke kolommen toegevoegd aan latent_profiles, waarbij de volgorde overeenkomt met worker_ids.
# Ze worden terecht niet toegevoegd aan worker_profiles.csv, want ze behoren tot de verborgen synthetische ground truth.
    latent_profiles = pd.DataFrame({
        "worker_id": worker_ids,
        "latent_midpoint": latent_midpoints,
        "latent_sleep_duration_hours": np.round(latent_sleep_duration, 2),
        "latent_duration_variability_hours": np.round(latent_duration_variability, 2),
        "latent_midpoint_variability_hours": np.round(latent_midpoint_variability, 2),
        "latent_early_duration_effect_hours": np.round(latent_early_duration_effect, 2),
        "latent_night_duration_effect_hours": np.round(latent_night_duration_effect, 2),
    })
    
        # ----- worker profiles available to HCSS -----
    # In the synthetic population, latent_sleep_duration_hours is used as
    # a proxy for individual sleep need. In a real-world application,
    # sleep need could be obtained through self-report, intake, or a user profile.
    worker_profiles = latent_profiles[
        ["worker_id", "latent_sleep_duration_hours"]
    ].copy()
    
    worker_profiles = worker_profiles.rename(
        columns={"latent_sleep_duration_hours": "sleep_need_hours"}
    )

    # ----- save -----
    output_dir = Path("data")
    output_dir.mkdir(parents=True, exist_ok=True)

    workers.to_csv(output_dir / "workers.csv", index=False)
    latent_profiles.to_csv(
        output_dir / "latent_sleep_profiles.csv",
        index=False,
    )
    
    worker_profiles.to_csv(
        output_dir / "worker_profiles.csv",
        index=False,
    )

    # Small sanity check in the terminal
    print("\nworkers.csv")
    print(workers.head())

    print("\nlatent_sleep_profiles.csv")
    print(latent_profiles.head())

    print("\nRole counts:")
    print(workers["role"].value_counts())

    print("\nGenerated 30 workers successfully.")


if __name__ == "__main__":
    main()
