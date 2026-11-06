# -*- coding: utf-8 -*-
"""
tests for evaluator/validity.py

@author: irisv
"""

import pytest

from evaluator.validity import check_roster_validity


historical_patterns = {
    "transitions": {
        ("early", "early"),
        ("early", "off"),
        ("off", "off"),
        ("off", "late"),
        ("late", "late"),
    },
    "block_lengths": {
        ("early", 2),
        ("early", 3),
        ("off", 2),
        ("late", 2),
    },
}




def test_no_extrapolation():
    
    roster_shifts = ["early"] * 3 + ["off"] * 2 + ["late"] * 2 # nothing unseen (no unseen transitions, no unseen blocklengths), no uncertainty
    
    result = check_roster_validity(roster_shifts, historical_patterns)
    
    assert result["is_extrapolation"] is False
    assert result["unseen_transitions"] == []
    assert result["unseen_block_lengths"] == []
    assert result["uncertain_boundary_block_lengths"] == []
    
def test_unseen_transition():
    
    roster_shifts = ["early"] * 3 + ["late"] * 3 # unseen transition (early - late) & unseen blocklength ("late",3) is longer than historical length
    
    result = check_roster_validity(roster_shifts, historical_patterns)
    
    assert result["is_extrapolation"] is True
    assert result["unseen_transitions"] == [("early", "late")]
    assert result["unseen_block_lengths"] == [("late", 3)]
    assert result["uncertain_boundary_block_lengths"] == []
    
def test_unseen_internal_block_length():
    
    roster_shifts = ["early"] * 2 + ["off"] * 1 + ["late"] * 2 # off: unseen blocklength 1
    
    result = check_roster_validity(roster_shifts, historical_patterns)
    
    assert result["is_extrapolation"] is True
    assert result["unseen_transitions"] == []
    assert result["unseen_block_lengths"] == [("off", 1)]
    assert result["uncertain_boundary_block_lengths"] == []
    
def test_uncertain_boundary_block():
    
    roster_shifts = ["early"] * 1 + ["off"] * 2 + ["late"] * 2 # block[0] --> (early, 1) at boundary, not longer than historical lengths for early shift
    
    result = check_roster_validity(roster_shifts, historical_patterns)
    
    assert result["is_extrapolation"] is False
    assert result["unseen_transitions"] == []
    assert result["unseen_block_lengths"] == []
    assert result["uncertain_boundary_block_lengths"] == [("early",1)]
    
def test_unseen_shift():
    
    roster_shifts = ["off"] * 2 + ["night"] * 3 + ["off"] * 2
    
    result = check_roster_validity(roster_shifts, historical_patterns)
    
    assert result["is_extrapolation"] is True
    assert result["unseen_transitions"] == [("off", "night"), ("night","night"), ("night", "off")] # night doesn't exist in the worked example
    assert result["unseen_block_lengths"] == [("night",3)]
    assert result["uncertain_boundary_block_lengths"] == []


def test_longer_than_historical_blocks_is_unseen_not_uncertain():
    
    roster_shifts = ["early"] * 10 + ["off"] * 2
    
    result = check_roster_validity(roster_shifts, historical_patterns)
    
    assert result["is_extrapolation"] is True
    assert result["unseen_transitions"] == []
    assert result["unseen_block_lengths"] == [("early",10)]
    assert result["uncertain_boundary_block_lengths"] == [] # not flagged as uncertain, since 10 >> historical block length for early shift




    
    
    



