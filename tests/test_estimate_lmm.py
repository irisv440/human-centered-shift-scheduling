# -*- coding: utf-8 -*-
"""
Tests for evaluator/estimate_lmm.py

An LMM does not give simple cell averages, so there is no hand-calculated
example. Instead we simulate a small dataset with KNOWN effects and check
that the model finds them back (a mini recovery test).

The simulated data use a fixed seed, so every run gives the same numbers.
"""

import numpy as np
import pytest

from evaluator.estimate_lmm import estimate_cell_parameters_lmm


# --- Simulated data with known truth ----------------------------------------

SEED = 1
NUM_WORKERS = 20
NUM_NIGHTS = 84          # 21 nights per linked shift, as in the real data
SIGMA_TRUE = 0.5         # night-to-night noise, same for everyone

# Average effects vs Off (fixed effects)
MEAN_OFF = 8.0
EFFECT_MEAN = {"early": -1.5, "late": -0.5, "night": -2.0}
# How much workers differ from each other in their Early / Night effect.
# Late: no differences between workers (like the real synthetic data).
EFFECT_SD = {"early": 0.4, "late": 0.0, "night": 0.5}


def simulate_records():
    """
    Return (records, truth).
    truth[worker_id][shift] = the true difference vs Off of that worker.
    """
    rng = np.random.default_rng(SEED)
    # Simple repeating pattern so every shift gets the same number of nights
    pattern = ["off", "early", "late", "night"]

    records = []
    truth = {}
    for w in range(NUM_WORKERS):
        worker_id = f"W{w + 1:03d}"
        worker_off = MEAN_OFF + rng.normal(0.0, 0.5)   # personal Off level
        worker_effect = {s: EFFECT_MEAN[s] + rng.normal(0.0, EFFECT_SD[s])
                         for s in EFFECT_MEAN}
        truth[worker_id] = worker_effect

        for t in range(NUM_NIGHTS):
            shift = pattern[t % 4]
            mean = worker_off + worker_effect.get(shift, 0.0)   # Off adds 0
            records.append({
                "worker_id": worker_id,
                "linked_shift": shift,
                "sleep_duration_hours": mean + rng.normal(0.0, SIGMA_TRUE),
                "no_main_sleep_episode": False,
            })
    return records, truth


# Fit once and reuse in every test (fitting takes a few seconds).
# scope="module": pytest runs this function only once for this file.
@pytest.fixture(scope="module")
def fitted():
    records, truth = simulate_records()
    parameters, result = estimate_cell_parameters_lmm(records)
    return parameters, result, truth


# --- Tests -------------------------------------------------------------------

def test_output_has_expected_structure(fitted):
    parameters, _, _ = fitted

    assert len(parameters) == NUM_WORKERS
    p = parameters["W001"]
    assert set(p["mean_hours"]) == {"off", "early", "late", "night"}
    assert set(p["diff_vs_off_hours"]) == {"early", "late", "night"}
    assert p["num_nights"] == {"off": 21, "early": 21, "late": 21, "night": 21}


def test_mean_equals_off_plus_difference(fitted):
    # Internal consistency: mu_s = mu_off + D_s for every worker and shift
    parameters, _, _ = fitted
    for p in parameters.values():
        for shift in ("early", "late", "night"):
            assert p["mean_hours"][shift] == pytest.approx(
                p["mean_hours"]["off"] + p["diff_vs_off_hours"][shift])


def test_fixed_effects_recovered(fitted):
    # The average effects should be close to the true averages.
    # Tolerance 0.3 h: the estimate itself has sampling error, because only
    # 20 workers are drawn (standard error about 0.1 h for Night).
    _, result, _ = fitted
    for shift, true_mean in EFFECT_MEAN.items():
        assert result.fe_params[f"is_{shift}"] == pytest.approx(true_mean, abs=0.3)


def test_sigma_recovered(fitted):
    # [Changed 2026-10-28 17:26] sigma is now per worker: check the average
    # over workers (each single worker has more sampling error)
    parameters, _, _ = fitted
    sigmas = [p["sigma_hours"] for p in parameters.values()]
    assert np.mean(sigmas) == pytest.approx(SIGMA_TRUE, abs=0.05)


# [Added 2026-10-28 17:26] test for sigma per worker
def test_sigma_differs_per_worker():
    # Simulate two kinds of workers: calm (sigma 0.4) and noisy (sigma 1.0).
    # The per-worker sigma must find back each worker's own noise level.
    rng = np.random.default_rng(SEED)
    pattern = ["off", "early", "late", "night"]
    true_sigma = {}
    records = []
    for w in range(NUM_WORKERS):
        worker_id = f"W{w + 1:03d}"
        true_sigma[worker_id] = 0.4 if w % 2 == 0 else 1.0   # alternate calm / noisy
        for t in range(NUM_NIGHTS):
            shift = pattern[t % 4]
            mean = MEAN_OFF + EFFECT_MEAN.get(shift, 0.0)
            records.append({
                "worker_id": worker_id,
                "linked_shift": shift,
                "sleep_duration_hours": mean + rng.normal(0.0, true_sigma[worker_id]),
                "no_main_sleep_episode": False,
            })

    parameters, _ = estimate_cell_parameters_lmm(records)

    # Mean absolute error per worker below 0.1 h
    errors = [abs(parameters[w]["sigma_hours"] - true_sigma[w]) for w in true_sigma]
    assert np.mean(errors) < 0.1


def test_worker_specific_effects_recovered(fitted):
    # Per worker, the estimated Night effect should be close to that worker's
    # true Night effect. Mean absolute error below 0.2 h (12 minutes).
    parameters, _, truth = fitted
    errors = [abs(parameters[w]["diff_vs_off_hours"]["night"] - truth[w]["night"])
              for w in truth]
    assert np.mean(errors) < 0.2


def test_blank_nights_are_skipped():
    # A blank night (no main sleep, duration None) must be left out
    records, _ = simulate_records()
    records.append({
        "worker_id": "W001",
        "linked_shift": "night",
        "sleep_duration_hours": None,
        "no_main_sleep_episode": True,
    })
    parameters, _ = estimate_cell_parameters_lmm(records)
    assert parameters["W001"]["num_nights"]["night"] == 21
