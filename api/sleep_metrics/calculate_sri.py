# -*- coding: utf-8 -*-
"""
Created on Mon Oct  5 18:46:28 2026

@author: irisv
"""


import numpy as np
from datetime import datetime, timedelta, time



def calculate_sri(sleep_episodes, total_days):
    """
    sleep_episodes: List of tuples (start_minute, end_minute)
    total_days: Total days in the dataset
    """
    
    if total_days < 2:
        raise ValueError("At least two days are required to calculate SRI.")
        
    day_length = 1440

    context_days = 1

    total_minutes = (total_days + context_days) * day_length

    timeline = np.zeros(total_minutes, dtype=int)

    # 1 = asleep, 0 = awake
    for start, end in sleep_episodes:

        # Protect boundaries
        start_idx = max(start, 0) # avoid negative start indices
        end_idx = min(end, total_minutes)

        if start_idx < end_idx:
            timeline[start_idx:end_idx] = 1

    # The context day is needed because we want the analysis to start at 00:00 on analysis day 1,
    # while still having accurate sleep data for a sleep episode that started before that 00:00 boundary.
    analysis_start = day_length # analysis_start = 1440
    analysis_end = analysis_start + total_days * day_length

    analysis_timeline = timeline[analysis_start:analysis_end]

    # Create Day i and Day i+1 arrays for overall SRI
    today_vectors = analysis_timeline[:-day_length]
    tomorrow_vectors = analysis_timeline[day_length:]

    # Compare matching minutes
    matches = np.sum(today_vectors == tomorrow_vectors)
    total_comparisons = len(today_vectors)

    # Standard SRI scaling
    match_probability = matches / total_comparisons
    sri_score = 200 * (match_probability - 0.5)

    # 6. Calculate day-pair SRI
    day_pair_sri = []
    counter = 0
    delta = 1440

    # Calculate a daily SRI score for each pair of consecutive analysis days.
    # For each day pair, compare the sleep/wake state at every minute 24 hours apart
    # and convert the proportion of matching states to an SRI score.
    for comparison in range(total_days - 1):

        day_current = analysis_timeline[
            0 + counter : day_length + counter]

        day_next = analysis_timeline[day_length + counter : day_length * 2 + counter]

        matches_from_day_to_day = np.sum(day_current == day_next)

        # Per dagpaar vergelijken we exact 1440 minuten.
        day_comparisons = delta

        match_probability_per_day = (
            matches_from_day_to_day / day_comparisons
        )

        daily_sri_score = 200 * (
            match_probability_per_day - 0.5
        )

        day_pair_sri.append(daily_sri_score)

        # Counter: 1440 -> shift one calendar day
        counter += delta


    return sri_score, day_pair_sri

# Possibility to test without real database
def build_sri_input(sleep_records):
    """
    Convert sleep records to minute-indexed sleep episodes for calculate_sri.

    sleep_records: list of dicts with 'sleep_date' (date), 'sleep_start' and
    'sleep_end' (datetime), sorted by sleep_date.
    
    'no_main_sleep_episode' (bool). Records without a main sleep episode
    are skipped, so that day counts as awake for SRI.

    Returns (episodes, total_days), where episodes is a list of
    (start_minute, end_minute) relative to the context start.
    """
    # Get first and last sleep dates in order to determine the amount of days to analyse
    first_sleep_date = sleep_records[0]["sleep_date"]
    last_sleep_date = sleep_records[-1]["sleep_date"]
    
    total_days = (last_sleep_date - first_sleep_date).days + 1

    # The context day starts at 00:00 on the day before the first sleep_date.
    # Every sleep episode assigned to a sleep_date falls between 00:00 on
    # (sleep_date - 1) and the end of sleep_date, for every linked shift type.
    context_start = datetime.combine(first_sleep_date - timedelta(days=1), time(0,0))
    
    # List to append start and end times of sleep as a tuple (start_minute, end_minute)
    episodes_per_worker = []
    for record in sleep_records:
        
        if record["no_main_sleep_episode"]: # doesn't count as a valid sleep episode
            continue
        
        start_minute = round((record["sleep_start"] - context_start).total_seconds() / 60)
        
        end_minute = round((record["sleep_end"] - context_start).total_seconds() / 60)
        
        episodes_per_worker.append((start_minute, end_minute))

    return episodes_per_worker, total_days

