# -*- coding: utf-8 -*-
"""
Tests for evaluator/roster_score.py
"""

import pytest

from evaluator.roster_score import score_roster


# Estimates of one worker, from the worked example in the plan
WORKER = {
    "mean_hours": {"off": 8.0, "early": 6.2, "late": 7.6, "night": 5.6},
    "diff_vs_off_hours": {"early": -1.8, "late": -0.4, "night": -2.4},
    "sigma_hours": 0.13 ** 0.5,
}


def test_worked_example_from_plan():
    # Linked nights: early x3, off x3, late x2 (the last one after the roster)
    # Difference vs Off: 3 x -1.8 + 2 x -0.4 = -6.2
    # Short nights: 3 x 0.29 = 0.87, Off and Late add almost nothing
    roster_shifts = ["early", "early", "early", "off", "off", "late", "late"]

    result = score_roster(roster_shifts, WORKER)

    assert result["cumulative_diff_hours"] == pytest.approx(-6.2)
    assert result["expected_short_nights_given_main_sleep"] == pytest.approx(0.87, abs=0.01)


def test_missing_estimate_gives_none():
    # This worker has no estimate for Night, and the roster needs one
    # Return None if the necessary parameter is missing (here: mean_hours and diff_vs_off_hours lacking for night)
    worker = {
        "mean_hours": {"off": 8.0, "early": 6.2, "late": 7.6, "night": None},
        "diff_vs_off_hours": {"early": -1.8, "late": -0.4, "night": None},
        "sigma_hours": 0.13 ** 0.5,
    }

    assert score_roster(["off", "night"], worker) is None
