# -*- coding: utf-8 -*-
"""
 evaluator/roster_score.py

 Score one worker's candidate roster, using that worker's estimates.

 Two separate scores, summed over the linked nights of the roster:
 - cumulative_diff_hours: total difference vs Off nights (T in the plan).
   Off nights add 0. Negative = less sleep than on Off nights.
- expected_short_nights_given_main_sleep: expected number of nights under
  6 hours (K in the plan), given a main sleep episode on every night.
  Blank nights are not included yet.

Both scores also count one extra night: the sleep on the date after the
roster, because a Late or Night shift on the last date affects that sleep.
A roster of 7 days therefore counts 8 nights.
- This extra night always adds its probability to the expected short nights,
  also when it is linked to Off, so that score is higher than for the roster
  days alone.
- It changes the total difference vs Off only if the last date is Late or
  Night. Otherwise it is linked to Off and adds 0.
- Assumption: the date after the roster is not Early. If it is, this night
  should be linked to Early, and both scores are off for this night.
  
 """

from evaluator.linkage import link_roster
from evaluator.short_sleep import p_short_given_main_sleep

# function applies to ONE worker
def score_roster(roster_shifts, worker_parameters):
     """
     Parameters
     ----------
     roster_shifts : list of str
         The candidate roster of ONE worker: the shift WORKED per date, in date
         order, without missing dates. No dates in the list itself, only
         the order. Allowed values: "early", "late", "night", "off".
         Example: ["early", "early", "off", "late"]

     worker_parameters: dict
         The estimates of that ONE worker: one entry from the output of
         estimate_cell_parameters or estimate_cell_parameters_lmm, so
         output["W001"], not the whole output.
         Only these three keys are used:
         {
           "mean_hours": {"off": 8.0, "early": 6.2, "late": 7.6, "night": 5.6},
               dict: night_type (str) -> expected sleep in hours (float or None)
           "diff_vs_off_hours": {"early": -1.8, "late": -0.4, "night": -2.4},
               dict: night_type (str) -> difference vs Off in hours (float or None)
               Has no "off" key, because Off is the reference.
           "sigma_hours": 0.36,
               float or None: night-to-night standard deviation in hours
         }

     Returns
     -------
     dict or None
         None if an estimate needed for this roster is missing. Otherwise:
         {
           "cumulative_diff_hours": -6.2,
               = float: sum of the differences vs Off, in hours
           "expected_short_nights_given_main_sleep": 0.87,
               = float: sum of the probabilities, a number of nights
           "per_linked_shift": {"off": {...}, "early": {...}, "late": {...}, "night": {...}},
               = dict: linked shift type (str) -> dict with six values
               [Added 2026-11-09]
         }

         The six values per linked shift type:
           "num_nights": int
               number of nights linked to this shift type, including the
               extra night after the roster. Summed over the four types:
               the length of the roster plus 1.
           "diff_contribution_hours": float
               this type's part of cumulative_diff_hours. Always 0.0 for Off.
           "expected_short_nights_contribution": float
               this type's part of expected_short_nights_given_main_sleep.
           "diff_per_night_hours": float or None
               the worker's difference vs Off for one night of this type.
               Always 0.0 for Off.
           "p_short_per_night": float or None
               the worker's probability of a short night (under 6 hours,
               given a main sleep episode) for one night of this type.
           "p_short_increase_vs_off": float or None
               p_short_per_night of this type minus p_short_per_night of
               Off. Always 0.0 for Off.

         The two contributions are sums over the nights in the roster: they
         are 0.0 for a type without nights. The three values per night do
         not depend on the roster: they are given for every type, also with
         0 nights. They are None only for a type without nights whose
         estimate is missing.
         For every type: contribution = num_nights x value per night.
     """
     # float: running totals of the two scores
     cumulative_diff_hours = 0.0
     expected_short_nights = 0.0

     # Added 2026-11-09: running totals per linked shift type
     per_linked_shift = {}
     for shift_type in ("off", "early", "late", "night"):
         per_linked_shift[shift_type] = {
             "num_nights": 0,
             "diff_contribution_hours": 0.0,
             "expected_short_nights_contribution": 0.0,
         }

     # linked_shifts (list of str): the linked shift per date, plus the date after the roster, so one element more than roster_shifts
     # Hence input = WORKED shifts on a particular date, output = the linked shift - i.e. the one that really influences sleep on that same date
     linked_shifts = link_roster(roster_shifts, include_next_date=True)
     
     # For each night_type (linked_shift: determine cumulative diff hours and probability for that kind of shift,
     # If one of the means or sigma is lacking for that particular shift, the roster_score can't be computed: None)
     # night_type (str): the linked shift of one night, NOT the worked shift
     for night_type in linked_shifts:
         per_linked_shift[night_type]["num_nights"] += 1  # [Added 2026-11-09]
         if night_type != "off":
             # diff (float or None): difference vs Off for this night, in hours
             diff = worker_parameters["diff_vs_off_hours"][night_type]
             if diff is None:
                 return None
             cumulative_diff_hours += diff # sommation of the differences
             per_linked_shift[night_type]["diff_contribution_hours"] += diff  # [Added 2026-11-09]

         # probability (float between 0 and 1, or None): chance that this
         # night is under 6 hours, given a main sleep episode
         probability = p_short_given_main_sleep(
             worker_parameters["mean_hours"][night_type], # 
             worker_parameters["sigma_hours"],
         )
         if probability is None: # E.g. if night_type = Night, but no mean or sigma for this shift_type is available: return None
             return None
         expected_short_nights += probability # sum of the probability for each night (sommation)
         per_linked_shift[night_type]["expected_short_nights_contribution"] += probability  # [Added 2026-11-09]
     # Added 2026-11-09: personal values per night, also for shift types with 0 nights
     p_short_off = p_short_given_main_sleep(
         worker_parameters["mean_hours"]["off"],
         worker_parameters["sigma_hours"],
     )
     for shift_type in ("off", "early", "late", "night"):
         if shift_type == "off":
             diff_per_night = 0.0
         else:
             diff_per_night = worker_parameters["diff_vs_off_hours"][shift_type]
         p_short = p_short_given_main_sleep(
             worker_parameters["mean_hours"][shift_type],
             worker_parameters["sigma_hours"],
         )
         if p_short is None or p_short_off is None:
             p_increase = None
         else:
             p_increase = p_short - p_short_off
         per_linked_shift[shift_type]["diff_per_night_hours"] = diff_per_night
         per_linked_shift[shift_type]["p_short_per_night"] = p_short
         per_linked_shift[shift_type]["p_short_increase_vs_off"] = p_increase

         # Scores needed to score a candidate roster: 1. cumulative diff hours 2. expected short nights

     return {
         "cumulative_diff_hours": cumulative_diff_hours,
         "expected_short_nights_given_main_sleep": expected_short_nights,
         "per_linked_shift": per_linked_shift,  # Added 2026-11-09: breakdown per linked shift type
     }

if __name__ == "__main__":
    # Demonstration using fictional worker parameters.
    # These values are illustrative and are not estimated from historical data.
    # The example rosters can be modified to explore how scoring works.
    # Run from the project root:  python -m evaluator.roster_score

    # Estimates of one worker, feel free to adapt.
    example_worker_1 = {
        "mean_hours": {"off": 8.0, "early": 6.2, "late": 7.6, "night": 5.6},
        "diff_vs_off_hours": {"early": -1.8, "late": -0.4, "night": -2.4},
        "sigma_hours": 0.13 ** 0.5,
    }
    
    example_worker_2 = {
        "mean_hours": {"off": 8.0, "early": None, "late": 7.6, "night": 5.6},
        "diff_vs_off_hours": {"early": None, "late": -0.4, "night": -2.4},
        "sigma_hours": 0.13 ** 0.5,
    }
    
    example_roster_1 = ["early", "early", "early", "off", "off", "late", "late"]
    
    example_roster_2 = ["off", "night"] # example: early parameters absent, but early is not in night_type

    print("Worked shifts:", example_roster_1) # the worked shifts
    # input: list of worked shifts(str) - different from: linked_shift which refers to the shift linked to a particular sleep_date
    print("Linked shifts:", link_roster(example_roster_1, include_next_date=True))
    print("Scores:", score_roster(example_roster_1, example_worker_1)) # example_worker_1: the aggregate scores that have been linked earlier to the correct shift
    
    print("Worked shifts:", example_roster_2)
    # input: list of worked shifts(str)
    print("Linked shifts:", link_roster(example_roster_2, include_next_date=True))
    print("Scores:", score_roster(example_roster_2, example_worker_2))
