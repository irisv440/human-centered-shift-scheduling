# -*- coding: utf-8 -*-
"""
evaluator/linkage.py

Linkage rule: which shift is linked to the main sleep of a given date?

Same rule as the generator of the synthetic data, written separately on purpose: 
the evaluator does not import generator code.

@author: irisv
"""

def linked_shift(current_shift, previous_shift):
    """
    Return the linked shift for the sleep stored on the current date.

    current_shift:  the shift on this date ("early", "late", "night", "off")
    previous_shift: the shift on the previous date (None on the first date)

    Early affects the sleep BEFORE the shift, so it looks at today.
    Late and Night affect the sleep AFTER the shift, so they look at yesterday.
    """
    if current_shift == "early":
        return "early"
    if previous_shift == "night":
        return "night"
    if previous_shift == "late":
        return "late"
    return "off"

def link_roster(shifts, include_next_date=False):
      """
      Apply the linkage rule to one worker's roster.

      shifts: list of shifts of one worker, one per date, in date order
              and without missing dates. Example: ["off", "early", "late"]
      include_next_date: also return the date after the last shift, because a
              Late or Night shift on the last date affects that sleep.
              The shift on that next date is unknown: assumed not Early.

      Returns a list with the linked shift per date.
      Same length as shifts, or one longer with include_next_date=True.
      Example: ["off", "early", "off"]
      With include_next_date=True: ["off", "early", "off", "late"]
      """
      linked_shifts = []
      previous_shift = None

      for current_shift in shifts:
          linked_shifts.append(linked_shift(current_shift, previous_shift))
          previous_shift = current_shift

      if include_next_date and shifts:
          linked_shifts.append(linked_shift("off", previous_shift))

      return linked_shifts

    