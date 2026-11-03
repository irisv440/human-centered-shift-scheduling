# -*- coding: utf-8 -*-
"""
Created on Wed Oct 28 12:07:21 2026

@author: irisv

Tests for evaluator/estimate.py

Uses the worked example from section 6 of the implementation plan:
one worker, twelve nights, three per linked shift.
All expected values were calculated by hand.
"""

import pytest

from evaluator.estimate import estimate_cell_parameters


def make_record(linked_shift, duration, worker_id="W001", no_main_sleep=False):
    """Build one sleep record in the same shape as the API / CSV data."""
    return {
        "worker_id": worker_id,
        "linked_shift": linked_shift,
        "sleep_duration_hours": duration,
        "no_main_sleep_episode": no_main_sleep,
    }


# The twelve nights of a worked example (section 6 of internal document, step 1)
WORKED_EXAMPLE = (
    [make_record("off", d) for d in (8.0, 8.4, 7.6)]
    + [make_record("early", d) for d in (6.2, 5.8, 6.6)]
    + [make_record("late", d) for d in (7.6, 7.4, 7.8)]
    + [make_record("night", d) for d in (5.6, 6.0, 5.2)]
)


def test_cell_means_worked_example():
    # Section 6, step 2: average of each row
    result = estimate_cell_parameters(WORKED_EXAMPLE)["W001"]

    # pytest.approx: floating-point sums are not exact (8.0 + 8.4 + 7.6 ...)
    assert result["mean_hours"]["off"] == pytest.approx(8.0)
    assert result["mean_hours"]["early"] == pytest.approx(6.2)
    assert result["mean_hours"]["late"] == pytest.approx(7.6)
    assert result["mean_hours"]["night"] == pytest.approx(5.6)


def test_diff_vs_off_worked_example():
    # Section 6, step 4: subtract the Off mean (8.0)
    result = estimate_cell_parameters(WORKED_EXAMPLE)["W001"]

    assert result["diff_vs_off_hours"]["early"] == pytest.approx(-1.8)
    assert result["diff_vs_off_hours"]["late"] == pytest.approx(-0.4)
    assert result["diff_vs_off_hours"]["night"] == pytest.approx(-2.4)


def test_num_nights_worked_example():
    result = estimate_cell_parameters(WORKED_EXAMPLE)["W001"]

    assert result["num_nights"] == {"off": 3, "early": 3, "late": 3, "night": 3}


def test_blank_night_is_skipped():
    # A night without main sleep has no duration and must not change the mean.
    # Its duration is None here: if the function tried to use it, float(None) would fail.
    records = WORKED_EXAMPLE + [make_record("night", None, no_main_sleep=True)]
    result = estimate_cell_parameters(records)["W001"]

    assert result["mean_hours"]["night"] == pytest.approx(5.6)
    assert result["num_nights"]["night"] == 3


def test_workers_are_estimated_separately():
    # A second worker with different values must not affect W001
    other_worker = [make_record("off", 6.0, worker_id="W002"),
                    make_record("night", 3.0, worker_id="W002")]
    result = estimate_cell_parameters(WORKED_EXAMPLE + other_worker)

    assert result["W001"]["mean_hours"]["off"] == pytest.approx(8.0)
    assert result["W002"]["diff_vs_off_hours"]["night"] == pytest.approx(-3.0)


def test_missing_cell_gives_none():
    # W002 has no early or late nights: those means and differences are None
    records = [make_record("off", 8.0, worker_id="W002"),
               make_record("night", 6.0, worker_id="W002")]
    result = estimate_cell_parameters(records)["W002"]

    assert result["mean_hours"]["early"] is None
    assert result["diff_vs_off_hours"]["early"] is None
    assert result["num_nights"]["early"] == 0

def test_sigma_worked_example():
    # Squared residuals per shift: off 0.32, early 0.32, late 0.08, night 0.32
    # Sum = 1.04, degrees of freedom = 12 nights - 4 means = 8
    # sigma = sqrt(1.04/8) = sqrt(0.13)
    result = estimate_cell_parameters(WORKED_EXAMPLE)["W001"]
    
    assert result["sigma_hours"] == pytest.approx(0.13 ** 0.5)
    
def test_sigma_ignores_empty_cells():
    # Off: 8 and 10, mean 9, squared residuals sum to 2
    # Early: 6, 7 and 8, mean 7, squared residuals sum to 2
    # Late and night are empty, so only 2 means are estimated
    # Sum = 4, degrees of freedom = 5 nights - 2 means = 3
    records = [
        make_record("off", 8.0),
        make_record("off", 10.0),
        make_record("early", 6.0),
        make_record("early", 7.0),
        make_record("early", 8.0),
    ]
    result = estimate_cell_parameters(records)["W001"]

    assert result["sigma_hours"] == pytest.approx((4 / 3) ** 0.5)

def test_sigma_is_none_without_degrees_of_freedom():
    # One night per shift: 2 nights - 2 means = 0 degrees of freedom
    records = [
        make_record("off", 8.0),
        make_record("night", 6.0),
    ]
    result = estimate_cell_parameters(records)["W001"]

    assert result["sigma_hours"] is None
