# -*- coding: utf-8 -*-
"""
Created on Sun Oct 18 19:56:45 2026

@author: irisv
"""

from sleep_metrics.summarize_sleep import summarize_by_linked_shift #import function(s) under testing


def test_summary_of_regular_nights_per_linked_shift():

    # 1. Test input: regular nights only (no blank nights), for two linked shifts.
    # Early durations are deliberately not sorted, so min and max are not simply
    # the first or last record. Late records check that nights are grouped
    # under the correct linked shift.
    records = [
        {"linked_shift": "early", "no_main_sleep_episode": False, "sleep_duration_hours": 6.0},
        {"linked_shift": "early", "no_main_sleep_episode": False, "sleep_duration_hours": 4.5},
        {"linked_shift": "early", "no_main_sleep_episode": False, "sleep_duration_hours": 7.5},
        {"linked_shift": "late",  "no_main_sleep_episode": False, "sleep_duration_hours": 8.0},
        {"linked_shift": "late",  "no_main_sleep_episode": False, "sleep_duration_hours": 7.0},
    ]

    # 2. Call the function under test
    result = summarize_by_linked_shift(records)

    # 3. Early: 3 regular nights; mean (6.0 + 4.5 + 7.5) / 3 = 6.0
    assert result["early"]["num_nights"] == 3
    assert result["early"]["num_valid_sleep_episodes"] == 3
    assert result["early"]["num_no_main_sleep_episodes"] == 0
    assert result["early"]["mean_duration"] == 6.0
    assert result["early"]["min_sleep_duration"] == 4.5
    assert result["early"]["max_sleep_duration"] == 7.5

    # 3. Late: 2 regular nights; mean (8.0 + 7.0) / 2 = 7.5
    assert result["late"]["num_nights"] == 2
    assert result["late"]["num_valid_sleep_episodes"] == 2
    assert result["late"]["num_no_main_sleep_episodes"] == 0
    assert result["late"]["mean_duration"] == 7.5
    assert result["late"]["min_sleep_duration"] == 7.0
    assert result["late"]["max_sleep_duration"] == 8.0


def test_blank_night_counted_separately_and_excluded_from_mean():
    
    # 1. Test input: three early nights, one of them without a main sleep episode
    # (blank night: no_main_sleep_episode=True, duration None), and two off nights
    # without blank nights for comparison. Only the fields used by
    # summarize_by_linked_shift are included.
    records = [
        {"linked_shift": "early", "no_main_sleep_episode": False, "sleep_duration_hours": 6.0},
        {"linked_shift": "early", "no_main_sleep_episode": True,  "sleep_duration_hours": None},
        {"linked_shift": "early", "no_main_sleep_episode": False, "sleep_duration_hours": 5.0},
        {"linked_shift": "off",   "no_main_sleep_episode": False, "sleep_duration_hours": 8.0},
        {"linked_shift": "off",   "no_main_sleep_episode": False, "sleep_duration_hours": 7.0},
    ]
    
    # 2. Call summarize_sleep on the test records:
    result = summarize_by_linked_shift(records)
      

    # 3. assert statements Early: 
    assert result["early"]["num_valid_sleep_episodes"] == 2
    assert result["early"]["num_no_main_sleep_episodes"] == 1 # telt niet mee in het gemiddelde
    assert result["early"]["num_valid_sleep_episodes"] + result["early"]["num_no_main_sleep_episodes"] == 3
    assert result["early"]["mean_duration"] == 5.5
    
    # assert statements Off:
    assert result["off"]["num_valid_sleep_episodes"] == 2
    assert result["off"]["num_no_main_sleep_episodes"] == 0 # telt niet mee in het gemiddelde
    assert result["off"]["num_valid_sleep_episodes"] + result["off"]["num_no_main_sleep_episodes"] == 2
    assert result["off"]["mean_duration"] == 7.5
    
def test_missing_shift_type_returns_none():
    """
    A linked shift without any records (e.g. a worker who never worked
    nights) must not cause a crash: its counts are 0 and mean, min and max
    are None, because there is nothing to calculate.
    """
    # 1. Test input: early and off nights only. There are no night records,
    # so the night summary must show zero counts and None values.
    records = [
        {"linked_shift": "early", "no_main_sleep_episode": False, "sleep_duration_hours": 6.0},
        {"linked_shift": "early", "no_main_sleep_episode": False, "sleep_duration_hours": 5.0},
        {"linked_shift": "off",   "no_main_sleep_episode": False, "sleep_duration_hours": 8.0},
    ]
    
    # 2. Call summarize_sleep on the test records:
    result = summarize_by_linked_shift(records)
    
    # 3. Early: 2 regular nights; mean (6.0 + 5.0) / 2 = 5.5
    assert result["early"]["num_nights"] == 2
    assert result["early"]["num_valid_sleep_episodes"] == 2
    assert result["early"]["num_no_main_sleep_episodes"] == 0
    assert result["early"]["mean_duration"] == 5.5
    assert result["early"]["min_sleep_duration"] == 5
    assert result["early"]["max_sleep_duration"] == 6
    
    # Off
    assert result["off"]["num_nights"] == 1
    assert result["off"]["num_valid_sleep_episodes"] == 1
    assert result["off"]["num_no_main_sleep_episodes"] == 0
    assert result["off"]["mean_duration"] == 8
    assert result["off"]["min_sleep_duration"] == 8
    assert result["off"]["max_sleep_duration"] == 8
    
    # Night: no records. Expected: 0 for the counters, None for mean, min and max
    assert result["night"]["num_nights"] == 0
    assert result["night"]["num_valid_sleep_episodes"] == 0
    assert result["night"]["num_no_main_sleep_episodes"] == 0
    assert result["night"]["mean_duration"] is None
    assert result["night"]["min_sleep_duration"] is None
    assert result["night"]["max_sleep_duration"] is None

def test_only_blank_nights_returns_none():
    """
    A linked shift with only blank nights (no main sleep episode at all)
    must not cause a crash: the nights are counted, but mean, min and max
    are None, because there is no duration to calculate them from.
    """
    # 1. Test input: two night records, both without a main sleep episode,
    # and one regular early night for comparison. Diff with test 3, where num_nights = 0
    records = [
        {"linked_shift": "night", "no_main_sleep_episode": True,  "sleep_duration_hours": None},
        {"linked_shift": "night", "no_main_sleep_episode": True,  "sleep_duration_hours": None},
        {"linked_shift": "early", "no_main_sleep_episode": False, "sleep_duration_hours": 6.0},
    ]
    
    # 2. Call summarize_sleep on the test records:
    result = summarize_by_linked_shift(records)
    
    # Night: 2 records --> num_nights = 2, num_no_main_sleep_episodes = 2
    assert result["night"]["num_nights"] == 2
    assert result["night"]["num_valid_sleep_episodes"] == 0
    assert result["night"]["num_no_main_sleep_episodes"] == 2
    assert result["night"]["mean_duration"] is None
    assert result["night"]["min_sleep_duration"] is None
    assert result["night"]["max_sleep_duration"] is None
    
    # Early: 1 regular night
    assert result["early"]["num_nights"] == 1
    assert result["early"]["num_valid_sleep_episodes"] == 1
    assert result["early"]["num_no_main_sleep_episodes"] == 0
    assert result["early"]["mean_duration"] == 6.0
    assert result["early"]["min_sleep_duration"] == 6
    assert result["early"]["max_sleep_duration"] == 6
    