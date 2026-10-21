# -*- coding: utf-8 -*-
"""
Je zou dus een pytest schrijven die:
1. Twee opeenvolgende sleep_date-records bevat met hetzelfde slaap-waakpatroon, bijvoorbeeld telkens slapen van 01:00 tot 08:00.
2. Die records via build_sri_input() omzet naar minutenindices.
3. De resulterende episodes doorgeeft aan calculate_sri().
4. Met assert controleert of zowel de overall SRI als de enige daily SRI 100 bedraagt.
"""

import pytest
from datetime import date, datetime
from sleep_metrics.calculate_sri import build_sri_input
from sleep_metrics.calculate_sri import calculate_sri


def test_sri_calculation_identical_days():
    """
    Test the SRI calculation using two consecutive days with identical sleep patterns.
    
    Both days have the same sleep start and end times, so the sleep/wake
    states match at every minute 24 hours apart.
    
    Expected result: overall SRI = 100 and daily SRI = 100.
    """
    
    # 1. Input: two consecutive sleep record with identical sleep start / sleep end times
    records = [
        {"sleep_date": date(2026, 9, 10),
         "sleep_start": datetime(2026, 9, 10, 1, 12),
         "sleep_end": datetime(2026, 9, 10, 8, 12),
         "no_main_sleep_episode": False},
        {"sleep_date": date(2026, 9, 11),
         "sleep_start": datetime(2026, 9, 11, 1, 12),
         "sleep_end": datetime(2026, 9, 11, 8, 12),
         "no_main_sleep_episode": False},
    ]
    
    # 2. Call sri input function (note that the test functions for SRI input are located at test_sri_input.py).
    episodes, total_days = build_sri_input(records)
    
    # 3. Call the function under test: calculate_sri().
    # Calculate the overall SRI and the SRI for each pair of consecutive days.
    sri_full_signal, daily_sri = calculate_sri(episodes, total_days=total_days)
    
    # 4. SRI should be 100 for identical sleep nights
    assert sri_full_signal == 100
    assert daily_sri == [100]


def test_calculate_sri_raises_with_one_day():
    """
    calculate_sri needs at least two days: with one day there is
    no day pair to compare, so it must raise a ValueError.
    """
    # 1. Input: one sleep episode on the first analysis day (same as the regression test)
    episodes = [(1512, 1932)]

    # 2. + 3. Call the function and check that it raises a ValueError
    with pytest.raises(ValueError):
        calculate_sri(episodes, total_days=1)


