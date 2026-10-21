# -*- coding: utf-8 -*-
"""
Tests for build_sri_input (sleep_metrics/calculate_sri.py).

These tests use small hand-made sleep records (fixtures) with a known,
hand-calculated answer. They test the anchoring rule itself, independent
of the generated dataset, and need no PostgreSQL connection.

Anchoring rule: the context day starts at 00:00 on the day before
the first sleep_date. Minute 0-1439 = context day;
minute 1440 = 00:00 on the first sleep_date (first analysis day).
"""


from datetime import date, datetime
from sleep_metrics.calculate_sri import build_sri_input



def test_first_sleep_after_midnight_starts_on_first_analysis_day():
    """
    Regression test for the context-day bug.

    If the first sleep episode starts after midnight on its own sleep_date,
    it must still land on the first analysis day (minute 1440 onwards),
    not in the context day (minute 0-1439).
    """

    # 1. Input: one sleep record whose sleep_start falls after midnight
    #    on the same calendar day as its sleep_date (like W005).
    records = [
        {"sleep_date": date(2026, 9, 10),
         "sleep_start": datetime(2026, 9, 10, 1, 12),
         "sleep_end": datetime(2026, 9, 10, 8, 12),
         "no_main_sleep_episode": False},

    ]

    # 2. Call the function under test.
    episodes, total_days = build_sri_input(records)

    # 3. Check the result.
    # Context start = 9 Sept 00:00, so:
    # 10 Sept 01:12 = 1440 (one full day) + 72 (1 h 12 min) = 1512
    # 10 Sept 08:12 = 1440 + 492 (8 h 12 min)               = 1932
    # With the old anchor (10 Sept 00:00) this would be (72, 492): context day.
    assert episodes[0] == (1512, 1932) # start end end of first analysis episode

    # One sleep_date means one analysis day.
    assert total_days == 1


def test_first_sleep_before_midnight_starts_in_context_day():
    """
    Control case: the situation that was already handled correctly.

    If the first sleep episode starts before midnight, on the day before
    its sleep_date, its start lies in the context day and its end on the
    first analysis day.
    """

    # 1. Input: sleep starts on 9 Sept (the evening before sleep_date).
    records = [
        {"sleep_date": date(2026, 9, 10),
         "sleep_start": datetime(2026, 9, 9, 23, 30),
         "sleep_end": datetime(2026, 9, 10, 7, 0),
         "no_main_sleep_episode": False},
    ]

    # 2. Call the function under test.
    episodes, _ = build_sri_input(records)   # _ = total_days, not needed here

    # 3. Check the result.
    # Context start = 9 Sept 00:00, so:
    # 9 Sept 23:30  = 1410 (23 h 30 min)        -> in the context day
    # 10 Sept 07:00 = 1440 + 420 (7 h) = 1860   -> on the first analysis day
    assert episodes[0] == (1410, 1860)


def test_anchor_does_not_depend_on_first_sleep_start():
    """
    The core of the bug: the anchor must depend on sleep_date only.

    Two workers with the same sleep_dates, whose first sleep starts on
    different sides of midnight, must share the same timeline.
    Their identical second night must therefore land on the same minutes.
    """

    # The second night is identical for both workers.
    second_night = {"sleep_date": date(2026, 9, 11),
                    "sleep_start": datetime(2026, 9, 10, 23, 0),
                    "sleep_end": datetime(2026, 9, 11, 7, 0),
                    "no_main_sleep_episode": False}

    # Worker A: first sleep starts before midnight (was already correct).
    before_midnight = [
        {"sleep_date": date(2026, 9, 10),
         "sleep_start": datetime(2026, 9, 9, 23, 30),
         "sleep_end": datetime(2026, 9, 10, 7, 0),
         "no_main_sleep_episode": False},
        second_night,
    ]

    # Worker B: first sleep starts after midnight (was affected by the bug).
    after_midnight = [
        {"sleep_date": date(2026, 9, 10),
         "sleep_start": datetime(2026, 9, 10, 1, 12),
         "sleep_end": datetime(2026, 9, 10, 8, 12),
         "no_main_sleep_episode": False},
        second_night,
    ]

    episodes_before, _ = build_sri_input(before_midnight)
    episodes_after, _ = build_sri_input(after_midnight)

    # episodes[1] = the second night. Same input -> same minutes.
    # With the old anchor, worker B's timeline started one day later,
    # so this value differed by 1440 minutes.
    assert episodes_before[1] == episodes_after[1]
    
    
def test_build_sri_input_skips_blank_night():   
    """
    Test that build_sri_input skips records without a main sleep episode.
    
    Three consecutive sleep_dates, of which the middle one is a blank night
    (no_main_sleep_episode=True, sleep_start and sleep_end None).
    
    Expected result: two episodes (the blank night is skipped, so that day
    counts as awake) and total_days = 3.
    """
    records = [
        {"sleep_date": date(2026, 9, 10),
         "sleep_start": datetime(2026, 9, 10, 1, 12),
         "sleep_end": datetime(2026, 9, 10, 8, 12),
         "no_main_sleep_episode": False},
        
        # Blank night: no main sleep episode
        {"sleep_date": date(2026, 9, 11),
         "sleep_start": None,
         "sleep_end": None,
         "no_main_sleep_episode": True}, # no main sleep
        
        {"sleep_date": date(2026, 9, 12),
         "sleep_start": datetime(2026, 9, 12, 1, 12),
         "sleep_end": datetime(2026, 9, 12, 8, 12),
         "no_main_sleep_episode": False},
    ]
    
    # 2. Call sri input function
    episodes, total_days = build_sri_input(records)
    
    # Blank night (11/9) is skipped: only two episodes remain,
    # but the analysis window still covers all three sleep_dates
    assert episodes == [(1512, 1932), (4392, 4812)]
    assert total_days == 3