# -*- coding: utf-8 -*-
"""
Created on Sat Oct 17 21:47:31 2026

@author: irisv
"""

import numpy as np

def summarize_by_linked_shift(sleep_records):
    """
   Summarize sleep duration per linked shift (early, late, night, off).

   - sleep_records: list of dicts with 'linked_shift', 'no_main_sleep_episode'
   and 'sleep_duration_hours'.

   - Returns: a dict per linked shift with num_nights, num_valid_sleep_episodes,
   num_no_main_sleep_episodes, mean_duration, min and max (None if no valid nights).
    """
    
    # Strategy B, per linked shift:
    # - durations: nights WITH a main sleep episode (used for mean/min/max);
    # - num_no_main_sleep_episodes: observed nights without main sleep,
    #   counted separately (not treated as missing data).
        
    sleep_by_shift = {
        "early": {"durations": [], "num_no_main_sleep_episodes": 0},
        "late": {"durations": [], "num_no_main_sleep_episodes": 0},
        "night": {"durations": [], "num_no_main_sleep_episodes": 0},
        "off": {"durations": [], "num_no_main_sleep_episodes": 0},
        }
    
    for record in sleep_records:
        # linked_shift is always one of the four keys above (set by the generator)
        shift = record["linked_shift"]
        
        if record["no_main_sleep_episode"]:
            sleep_by_shift[shift]["num_no_main_sleep_episodes"] +=1
        else: # if no main sleep episode, there is no valid sleep episode to store in durations
            sleep_by_shift[shift]["durations"].append(record["sleep_duration_hours"])
        
    
    summary_by_shift = {}
    
    # Go through sleep duration             
    for shift, data in sleep_by_shift.items(): # sleep_by_shift before: {"early": [], ...}
        durations = data["durations"] # a list
        num_no_main_sleep = data["num_no_main_sleep_episodes"]
        
        # Fill the dictionary with new keys and the collected data
        summary_by_shift[shift] = {
            "num_nights": len(durations) + num_no_main_sleep, # valid durs + per shift hebben we een teller voor nonvalid durs
            "num_valid_sleep_episodes": len(durations),
            "num_no_main_sleep_episodes": num_no_main_sleep,
            "mean_duration": round(np.mean(durations),2) if durations else None,
            "min_sleep_duration": np.min(durations) if durations else None,
            "max_sleep_duration": np.max(durations) if durations else None,
                          
            }

    return summary_by_shift #return the filled summary_by_shift (6 keys, + data)
