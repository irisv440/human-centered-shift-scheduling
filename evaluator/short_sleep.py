# -*- coding: utf-8 -*-
"""

evaluator/short_sleep.py

Signal A, v1: the probability of a short night for one worker and linked
shift, GIVEN that there was a main sleep episode.

Intended definition of signal A: the full probability of a short night,
including nights without a main sleep episode. That full probability is
not estimated yet: the current data contain 0 blank nights out of 2520.

Assumes normally distributed sleep durations.
"""

from scipy.stats import norm


SHORT_SLEEP_HOURS = 6.0


def p_short_given_main_sleep(mean_hours, sigma_hours):
    """
    Probability of sleeping under 6 hours, given a main sleep episode.

    mean_hours:  the worker's expected sleep after this linked shift
    sigma_hours: the worker's night-to-night standard deviation

    Returns None when a value is missing or sigma_hours is 0,
    because the probability cannot be computed then.
    """
    if mean_hours is None or sigma_hours is None or sigma_hours == 0:
        return None

    # Distance from the threshold to the mean, in standard deviations
    distance = (SHORT_SLEEP_HOURS - mean_hours) / sigma_hours

    # Share of a normal distribution that lies below that distance
    return float(norm.cdf(distance))

