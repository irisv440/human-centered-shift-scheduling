# -*- coding: utf-8 -*-
"""
Created on Tue Oct 20 11:14:07 2026

@author: irisv
"""

from datetime import timedelta
import numpy as np

def build_sleep_by_shift(shift_sleep_records):
                    
    sleep_by_shift = {
        "early": [],
        "late": [],
        "night": []
    }
    
    date_format = '%Y-%m-%d'
    day_in_shift_block = {
        "early": 1,
        "late": 1,
        "night": 1
    }
    
    for record in shift_sleep_records:
        
        shift = record["shift_type"]
        
        # shift_date = datetime.strptime(record["shift_date"], date_format).date() # take the shift_date, transform to date
        shift_date = record["shift_date"]

        if len(sleep_by_shift[shift]) == 0: # no entries yet
            sleep_by_shift[shift].append({
                    "shift_date": shift_date,
                    "sleep_duration_hours": record["sleep_duration_hours"],
                    "no_main_sleep_episode": record["no_main_sleep_episode"],
                    "day_in_shift_block": 1
                    })
        # If this is the same shift sequence:
        elif shift_date == sleep_by_shift[shift][-1].get("shift_date") + timedelta(days=1): # there exist a previous shift_date in early_records early_records["shift_date"]
            
            day_in_shift_block[shift] += 1
            
            sleep_by_shift[shift].append({
                "shift_date": shift_date,
                "sleep_duration_hours": record["sleep_duration_hours"],
                "no_main_sleep_episode": record["no_main_sleep_episode"],
                "day_in_shift_block": day_in_shift_block[shift]
                })
            
        # Not the same shift sequence: the shift_dates differ by more than one day:
        else:
            
            day_in_shift_block[shift] = 1  # Need to restart 'day_in_shift_block' > reset to 1
        
            sleep_by_shift[shift].append({
                "shift_date": shift_date,
                "sleep_duration_hours": record["sleep_duration_hours"],
                "no_main_sleep_episode": record["no_main_sleep_episode"],
                "day_in_shift_block": day_in_shift_block[shift]
                })
            
     # --- CENSORING (not active yet) ---------------------------------
    # Idea: give every block a number, then mark blocks that touch the
    # first or last date of the data. Those may be incomplete.
    #
    # Part A - in the loop above, keep a block counter per shift type:
    #   block_number = {"early": 0, "late": 0, "night": 0}   # before the loop
    #   block_number[shift] += 1                             # when a NEW block starts (day 1)
    #   "block_number": block_number[shift],                 # add to each appended entry
    #
    # Part B - after the loop, mark blocks at the edges:
    # first_shift_date = shift_sleep_records[0]["shift_date"]   # query is ORDER BY shift_date ASC
    # last_shift_date = shift_sleep_records[-1]["shift_date"]
    #
    # for shift, records in sleep_by_shift.items():
    #     # set of block numbers that contain the first or last date
    #     censored_blocks = {
    #         r["block_number"] for r in records
    #         if r["shift_date"] in (first_shift_date, last_shift_date)
    #     }
    #     for r in records:
    #         r["possibly_censored_block"] = r["block_number"] in censored_blocks
    #
    # Conservative: a block that happens to start exactly on the first
    # date is also marked, because the data cannot tell us otherwise.
    # Use in STEP 4: skip records where r["possibly_censored_block"] is True.
    # -----------------------------------------------------------------
    
    return sleep_by_shift


def summarize_by_day_in_block(sleep_by_shift):
    
    sleep_by_day_in_block = {
        "early": {}, # becomes { 1: [4.28, 6.28, 4.93], 2:}
        "late": {},
        "night": {}
    }
    
    
    # Shift = Key (early, late, night), records: items
    for shift, records in sleep_by_shift.items():
        # records consist of shift_date, sleep_duration_hours and day_in_shift_block
        for record in records:
            day = record["day_in_shift_block"]
            
            # First time we see this day number: create its entry:
            if day not in sleep_by_day_in_block[shift]:

                sleep_by_day_in_block[shift][day] = { # creation of [day]
                    "durations": [],
                    "num_no_main_sleep_episodes": 0,
                    }
                
            # Count nights without main sleep separately,
            # keep durataions only for nights with a main sleep episode
            if record["no_main_sleep_episode"]:
                sleep_by_day_in_block[shift][day]["num_no_main_sleep_episodes"] += 1
            else:
                sleep_by_day_in_block[shift][day]["durations"].append(record["sleep_duration_hours"])
            
    # Dictionary to store num_nights, amount of valid sleep episodes, amount of nonvalid episodes, mean sleep duration
    mean_sleep_by_day_in_block = {
        "early": {},
        "late": {},
        "night": {}
    }
    
    for shift, days in sleep_by_day_in_block.items():
        for day, data in days.items():
            durations = data["durations"]
            num_no_main_sleep = data["num_no_main_sleep_episodes"]
            
            mean_sleep_by_day_in_block[shift][day] = {
                "num_nights": len(durations) + num_no_main_sleep, # valid durs + per shift hebben we een teller voor nonvalid durs
                "num_valid_sleep_episodes": len(durations),
                "num_no_main_sleep_episodes": num_no_main_sleep,
                "mean_duration": round(np.mean(durations), 2) if durations else None,
                
                }
    
    return mean_sleep_by_day_in_block


def count_short_sleep(sleep_by_shift, threshold_hours):
    
    short_sleep_by_shift = {
        "early": {"count": 0, "total": 0, "percentage": 0, "num_no_main_sleep_episodes": 0},
        "late": {"count": 0, "total": 0, "percentage": 0, "num_no_main_sleep_episodes": 0},
        "night": {"count": 0, "total": 0, "percentage": 0, "num_no_main_sleep_episodes": 0}           
    }
    
    # Decision: a night without main sleep counts as short sleep (0 h < 6 h),
    # in line with studies that sum all sleep between two shifts.
    # These nights are also counted separately, so it is visible
    # how much they contribute to the short-sleep count.
    for shift, records in sleep_by_shift.items():
        # records consist of shift_date, sleep_duration_hours and day_in_shift_block
        for record in records:
            
            # Check the flag FIRST: None < 6 would raise a TypeError
            if record["no_main_sleep_episode"]:
                short_sleep_by_shift[shift]["count"] += 1 # count blank night as short sleep
                short_sleep_by_shift[shift]["num_no_main_sleep_episodes"] += 1 # also count no main sleep
            elif record["sleep_duration_hours"] < threshold_hours: # SHORT SLEEP --> COUNT
                short_sleep_by_shift[shift]["count"] += 1 

        total = len(records)
        short_sleep_by_shift[shift]["total"] = total
        # Percentage: count/total_records_per_shift - returns None if list for a shift is empty  
        short_sleep_by_shift[shift]["percentage"] = round(short_sleep_by_shift[shift]["count"] / total * 100, 2) if total else None
    
    
    return short_sleep_by_shift
    


def compute_diff_vs_off(summary_by_linked_shift):
    
    # Use summary_by_shift to get mean sleep duration during off days
    mean_duration_off = summary_by_linked_shift["off"]["mean_duration"]
    num_nights_off = summary_by_linked_shift["off"]["num_valid_sleep_episodes"]
    
    duration_diff_vs_off= {
        "early": {},
        "late": {},
        "night": {}
        }
        
    for shift_type, data in summary_by_linked_shift.items():
        
        # Calculate 
        if shift_type != "off": # working with one worker only
            # Calculate individual shift_effect
            # Difference only possible if both means exist; otherwise None
            if data["mean_duration"] is not None and mean_duration_off is not None:
                duration_diff_vs_off_hours = round(data["mean_duration"] - mean_duration_off,2)
            else:
                duration_diff_vs_off_hours = None
            num_shifts = data["num_valid_sleep_episodes"]
    
            duration_diff_vs_off[shift_type] = {
                "diff_hours" : duration_diff_vs_off_hours, # None if e.g. mean_duration_off is none
                "num_shifts" : num_shifts,
                "num_nights_off": num_nights_off
                }
            
    return duration_diff_vs_off
    