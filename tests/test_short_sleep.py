# -*- coding: utf-8 -*-
"""
Tests for evaluator/short_sleep.py
"""

import pytest

from evaluator.short_sleep import p_short_given_main_sleep


def test_worked_example_from_plan():
    # Section 6 of the plan: standard deviation = square root of 0.13 (variance = 0.13 = 1.04/8) 
    sigma = 0.13 ** 0.5 # +- 0.36 uur
    
    # margin 0.01 is necessary given the rounding at 2 decimals
    assert p_short_given_main_sleep(6.2, sigma) == pytest.approx(0.29, abs=0.01)  # Early
    assert p_short_given_main_sleep(5.6, sigma) == pytest.approx(0.87, abs=0.01)  # Night

# A worker without sigma (for instance: nog enough nights available to compute sigma)
def test_missing_sigma_gives_none():
    assert p_short_given_main_sleep(6.2, None) is None



