# -*- coding: utf-8 -*-
"""
Created on Tue Oct 20 12:29:19 2026

@author: irisv
"""

from datetime import date
from sleep_metrics.shift_analysis import compute_diff_vs_off, count_short_sleep, build_sleep_by_shift #import function(s) under testing



def test_diff_vs_off_is_none_without_valid_off_nights():
    
    summary_by_linked_shift = {
        "early": {"num_nights": 3, "num_valid_sleep_episodes": 3, "num_no_main_sleep_episodes": 0,
                  "mean_duration": 6.0, "min_sleep_duration": 4.5, "max_sleep_duration": 7.5},
        "late":  {"num_nights": 2, "num_valid_sleep_episodes": 2, "num_no_main_sleep_episodes": 0,
                  "mean_duration": 7.5, "min_sleep_duration": 7.0, "max_sleep_duration": 8.0},
        "night": {"num_nights": 2, "num_valid_sleep_episodes": 2, "num_no_main_sleep_episodes": 0,
                  "mean_duration": 5.5, "min_sleep_duration": 5.0, "max_sleep_duration": 6.0},
        
        # Off: only blank nights, so no valid durations and no mean
        "off":   {"num_nights": 2, "num_valid_sleep_episodes": 0, "num_no_main_sleep_episodes": 2,
                  "mean_duration": None, "min_sleep_duration": None, "max_sleep_duration": None},
    }
        
    # 2. Call the function under test.
    result_duration_diff_vs_off = compute_diff_vs_off(summary_by_linked_shift)
    
    # 3. Check the results.
    assert result_duration_diff_vs_off["early"]["diff_hours"] is None
    
    # Num_shifts: this should be the amount of valid nights for the corresponding shift
    assert result_duration_diff_vs_off["early"]["num_shifts"] == 3
    
    # Num_nights_off should be 0:
    assert result_duration_diff_vs_off["early"]["num_nights_off"] == 0


def test_blank_night_counted_as_short_sleep():
    
    sleep_by_shift = {
        "early": [
            # Blank night: no main sleep episode, so no duration
            {"shift_date": date(2026, 6, 1), "sleep_duration_hours": None,
             "no_main_sleep_episode": True, "day_in_shift_block": 1},
            
            # 'Normal' Short sleep: below the threshold
            {"shift_date": date(2026, 6, 2), "sleep_duration_hours": 5.0,
             "no_main_sleep_episode": False, "day_in_shift_block": 2},
            
            # Normal sleep: above the threshold
            {"shift_date": date(2026, 6, 3), "sleep_duration_hours": 7.0,
             "no_main_sleep_episode": False, "day_in_shift_block": 3},
        ],
        "late": [],
        "night": [],
    }
    
    # 2. Call the function under test.
    result = count_short_sleep(sleep_by_shift, 6)
    
    # 3. Check the results.
    
    # early: count of short sleep should be 2
    assert result["early"]["count"] == 2
    
    # early num_no_main_sleep_episodes: 1
    assert result["early"]["num_no_main_sleep_episodes"] == 1
       
    # early: total should be the amount of records for this type of shift: 3
    assert result["early"]["total"] == 3
    
    # early: percentage should be 2/3 hence 66.67
    assert result["early"]["percentage"] == 66.67
    
    # late: percentage should be None (prevents attemt to diviside by 0 in the function under test)
    assert result["late"]["percentage"] is None  
        
    # night: percentage should be None (prevents attemt to diviside by 0 in the function under test)
    assert result["night"]["percentage"] is None  
    

def test_day_in_shift_block_counts_per_type_and_restarts_after_gap():

    shift_sleep_records = [
        # Early block 1: three consecutive days
        {"shift_date": date(2026, 6, 1), "shift_type": "early", "sleep_duration_hours": 6.0, "no_main_sleep_episode": False},
        {"shift_date": date(2026, 6, 2), "shift_type": "early", "sleep_duration_hours": 5.5, "no_main_sleep_episode": False},
        {"shift_date": date(2026, 6, 3), "shift_type": "early", "sleep_duration_hours": 6.5, "no_main_sleep_episode": False},
        
        # Late block in between: its own counter
        {"shift_date": date(2026, 6, 5), "shift_type": "late", "sleep_duration_hours": 7.5, "no_main_sleep_episode": False},
        {"shift_date": date(2026, 6, 6), "shift_type": "late", "sleep_duration_hours": 8.0, "no_main_sleep_episode": False},
       
        # Early block 2: after a gap, so the count restarts
        {"shift_date": date(2026, 6, 10), "shift_type": "early", "sleep_duration_hours": 6.2, "no_main_sleep_episode": False},
    ]

    # 2. Call the function under test.
    result = build_sleep_by_shift(shift_sleep_records)

    # 3. Check the results.
    
    # early: 
    expected_early = [1, 2, 3, 1]
    assert len(result["early"]) == 4
    
    for record, expected_day in zip(result["early"], expected_early):
        assert record["day_in_shift_block"] == expected_day
    
    # late:
    expected_late = [1, 2]
    assert len(result["late"]) == 2
    
    for record, expected_day in zip(result["late"], expected_late):
        assert record["day_in_shift_block"] == expected_day
    
    # night:
    assert result["night"] == []

