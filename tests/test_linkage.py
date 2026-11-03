# -*- coding: utf-8 -*-
"""
Tests for evaluator/linkage.py

@author: irisv
"""

from evaluator.linkage import linked_shift, link_roster


def test_early_today_is_early():
    assert linked_shift("early", "off") == "early"


def test_night_yesterday_is_night():
    assert linked_shift("off", "night") == "night"


def test_late_yesterday_is_late():
    assert linked_shift("off", "late") == "late"


def test_no_rule_applies_is_off():
    assert linked_shift("off", "off") == "off"

def test_shift_today_without_early_looks_at_yesterday():
     # A Night shift today affects the sleep AFTER it, so it does not count yet
     assert linked_shift("night", "off") == "off"


def test_early_has_priority_over_night_yesterday():
    # Night followed by Early: rule 1 wins, the post-Night sleep is not counted
    assert linked_shift("early", "night") == "early"


def test_night_today_after_late_yesterday_is_late(): # night shift today: no role as long as yesterday was 'late'
    # The Night shift today only affects the sleep after it,
    # so this date's sleep is still post-Late sleep
    assert linked_shift("night", "late") == "late"


def test_first_date_has_no_previous_shift():
    assert linked_shift("off", None) == "off"
    assert linked_shift("early", None) == "early"

# Tests regarding a full roster (tests link_roster)
def test_link_roster_short_example():
    # off:   nothing yesterday, so off
    # early: early today, so early
    # late:  affects the sleep after it, and yesterday was early, so off
    # off:   late yesterday, so late
    shifts = ["off", "early", "late", "off"]

    assert link_roster(shifts) == ["off", "early", "off", "late"]


def test_link_roster_night_block():
    # The first night only affects the next date.
    # The date after the last night is still night-linked.
    shifts = ["off", "night", "night", "off", "off"]

    assert link_roster(shifts) == ["off", "off", "night", "night", "off"]


def test_link_roster_empty():
    assert link_roster([]) == []
    
# Tests regarding the day following on a given list of shifts (influence of last shift)
def test_next_date_after_night_block():
    # Two Night shifts must give two night-linked sleeps
    shifts = ["off", "off", "night", "night"]

    result = link_roster(shifts, include_next_date=True)

    assert result == ["off", "off", "off", "night", "night"]


def test_next_date_is_left_out_by_default():
    assert link_roster(["off", "night"]) == ["off", "off"]