# -*- coding: utf-8 -*-
"""
evaluator/validity.py

Validity flag: does a candidate roster contain patterns that never occur in
the historical roster? If so, its score is an extrapolation: the score is
still computed, but the data do not show that it holds for this pattern.

Hence, the flag says nothing about whether a roster is good or bad for sleep, it only
tells whether this roster pattern occurred in the historical roster.

Two checks:
- every pair of consecutive days must occur in the historical roster;
- every block must have a length that occurs in the historical roster.
  The first and last block may be cut off by the start and end of the roster,
  so their real length is at least their length in the roster. If the length
  of such a block does not occur in the historical roster:
  - longer than the longest historical block of that shift: reported as
    unseen, and the roster is an extrapolation;
  - not longer: reported as uncertain, because it could be part of a longer
    historical block; the roster is not an extrapolation.
  [Changed 2026-11-06]

The flag does not check the order of the blocks. Example: early, off, off,
night passes, although it never occurs in the historical roster.
"""


def get_blocks(shifts):
    """
    Split one worker's roster into blocks.

    A block is a series of consecutive days with the same shift.

    shifts: list of str, the shift per date, in date order and without
            missing dates. Example: ["early", "early", "off", "late"]

    Returns a list of tuples (shift, length), in date order.
    Example: [("early", 2), ("off", 1), ("late", 1)]
    """
    blocks = []
    current_shift = None
    current_length = 0

    for shift in shifts:
        if shift == current_shift:
            current_length += 1
        else:
            # A new block starts, so the previous block is complete
            if current_shift is not None:
                blocks.append((current_shift, current_length))
            current_shift = shift
            current_length = 1

    # The last block has no next block to close it
    if current_shift is not None:
        blocks.append((current_shift, current_length))

    return blocks


def get_rosters_from_records(records):
    """
    Turn historical assignment records into one roster per worker.

    records: list of dicts, one per worker per date, with the columns of
             data/historical_assignments.csv.
             
             Used keys: worker_id, date, shift_type. Off days must be included as records.
             
             Dates must be in the format YYYY-MM-DD, so that sorting the
             text also sorts the dates.

    Returns a dict: worker_id (str) -> list of str, the shift per date.
    """
    # worker_id -> list of tuples (date, shift_type)
    dated_shifts_per_worker = {}
    for record in records:
        worker_id = record["worker_id"]
        if worker_id not in dated_shifts_per_worker:
            dated_shifts_per_worker[worker_id] = []
        dated_shifts_per_worker[worker_id].append((record["date"], record["shift_type"]))

    rosters = {}
    for worker_id, dated_shifts in dated_shifts_per_worker.items():
        dated_shifts.sort()  # tuples sort on their first element: the date
        shifts = []
        for date, shift_type in dated_shifts:
            shifts.append(shift_type)
        rosters[worker_id] = shifts # in rosters, 'dates' are not included anymore

    return rosters


def get_historical_patterns(rosters):
    """
    Collect which transitions and block lengths occur in the historical roster.

    rosters: dict, worker_id (str) -> list of str, the shift per date.
             
             The output of get_rosters_from_records.

    Returns a dict with two sets:
    {
      "transitions": tuples (shift on one day, shift on the next day),
      "block_lengths": tuples (shift, length), without the first and last
                       block of each worker, because those are cut off
    }
    """
    transitions = set()
    block_lengths = set()

    for shifts in rosters.values():
        for day in range(len(shifts) - 1):
            transitions.add((shifts[day], shifts[day + 1]))

        # blocks[1:-1]: all blocks except the first and the last
        blocks = get_blocks(shifts)
        for block in blocks[1:-1]:
            block_lengths.add(block)

    return {"transitions": transitions, "block_lengths": block_lengths}


def check_roster_validity(roster_shifts, historical_patterns):
    """
    Check one candidate roster against the historical patterns.

    roster_shifts: list of str, the shift WORKED per date of ONE worker, in
                   date order and without missing dates. The same list as
                   the input of score_roster.
    historical_patterns: the output of get_historical_patterns.

    Returns a dict:
    {
      "is_extrapolation": True if unseen_transitions or unseen_block_lengths
                          is not empty,
      "unseen_transitions": list of tuples (shift, next shift) that never occur,
      "unseen_block_lengths": list of tuples (shift, length) that never occur:
                              a block between the first and the last block,
                              or a first or last block that is longer than
                              the longest historical block of that shift,
      "uncertain_boundary_block_lengths": list of tuples (shift, length): the
                              first or last block if that length never occurs
                              but is not longer than the longest historical
                              block of that shift; does not affect
                              is_extrapolation
    }
    Each pattern appears once in its list, in the order of the roster.
    """
    unseen_transitions = []
    for day in range(len(roster_shifts) - 1):
        transition = (roster_shifts[day], roster_shifts[day + 1])
        if transition not in historical_patterns["transitions"]:
            if transition not in unseen_transitions:
                unseen_transitions.append(transition)

    unseen_block_lengths = [] # blocks from which we know they are not truncated (i.e. not first or last of a shift sequence)
    uncertain_boundary_block_lengths = [] # First and last blocks may be truncated, so their full lengths are unknown.
    blocks = get_blocks(roster_shifts) # get the blocks of the candidate roster [Changed 2026-11-05 14:52]
    
    # Longest historical block **per shift**, in which shift is the key in longest_block_length
    longest_block_length = {} # new dict
    for shift, length in historical_patterns["block_lengths"]: # historical_patterns["block_lengths"] is used to fill the new dict longest_block_length
        if length > longest_block_length.get(shift, 0): # 0 is default when the key doesn't exist
            longest_block_length[shift] = length
          
    # blocks[1:-1]: all blocks EXCEPT the first and the last
    for block in blocks[1:-1]: # A block is a tuple (shift, length): one shift and the number of consecutive days of that shift.
        if block not in historical_patterns["block_lengths"]: # then it possibly a new pattern
            if block not in unseen_block_lengths:
                unseen_block_lengths.append(block)
    
   
    #First or last block: may be cut off, so the real block is at least this long.
    if blocks:
        for block in (blocks[0], blocks[-1]): # edge cases
            if block not in historical_patterns["block_lengths"]:
                shift, length = block #unpacking tuple
                if length > longest_block_length.get(shift, 0):
                    # Longer than any historical block: extrapolation
                    if block not in unseen_block_lengths:
                        unseen_block_lengths.append(block)
                else: # length is not longer than historical block length
                    # Could be part of a longer historical block: uncertain
                    if block not in uncertain_boundary_block_lengths:
                        uncertain_boundary_block_lengths.append(block)

    is_extrapolation = len(unseen_transitions) > 0 or len(unseen_block_lengths) > 0

    return {
        "is_extrapolation": is_extrapolation,
        "unseen_transitions": unseen_transitions,
        "unseen_block_lengths": unseen_block_lengths,
        "uncertain_boundary_block_lengths": uncertain_boundary_block_lengths,
    }


if __name__ == "__main__":
    # Quick look at the historical patterns and five example rosters.
    # Run from the project root:  python -m evaluator.validity
    from pathlib import Path
    import pandas as pd

    data_path = Path(__file__).resolve().parent.parent / "data" / "historical_assignments.csv"
    records = pd.read_csv(data_path).to_dict("records")

    rosters = get_rosters_from_records(records)
    historical_patterns = get_historical_patterns(rosters)

    print("Transitions in the historical roster:")
    print(sorted(historical_patterns["transitions"]))
    print("Block lengths in the historical roster:")
    print(sorted(historical_patterns["block_lengths"]))

    example_rosters = [
        ["early"] * 3 + ["off"] * 2 + ["late"] * 2, # uncertainty regarding boundary block lengths: True
        ["early"] * 2 + ["off"] * 1 + ["late"] * 2, #  unseen block length: ("off", 1) --> extrapolation
        ["early"] * 7 + ["late"] * 7, # unseen transition --> extrapolation
        ["off"] * 2 + ["night"] * 3 + ["off"] * 2,
        ["early"] * 10 + ["off"] * 2, # example in which one shift is longer than any seen historical shift --> extrapolation
    ]
    for example_roster in example_rosters:
        print()
        print("Blocks:", get_blocks(example_roster))
        # Finally, check whether the current roster could be a valid roster (without extrapolation)
        print("Result:", check_roster_validity(example_roster, historical_patterns))
