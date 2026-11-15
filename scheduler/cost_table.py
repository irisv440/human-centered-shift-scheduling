# -*- coding: utf-8 -*-
"""
cost_table.py

@author: irisv
"""
from pathlib import Path

import pandas as pd

from evaluator.estimate_lmm import estimate_cell_parameters_lmm
from scheduler import requirements_config as cf
from evaluator.short_sleep import p_short_given_main_sleep

from evaluator.linkage import link_roster
from evaluator.roster_score import score_roster
from evaluator.validity import get_rosters_from_records


# Difference table (signal B per cell) for CPMpy
def make_diff_table(cell_parameters):
    """
    Table of diff_vs_off_hours: one row per worker (sorted on worker_id),
    one column per shift code (order of cf.SHIFT_CODES: off, early, late, night).
    Off is 0 by definition.
    """
    table = []  # becomes a list of rows: one row per worker

    # sorted(...) gives W001, W002, ..., W030: same order as ROLE and HOME_TEAM,
    # so row number i in the table = worker i in model.py.
    # (result.random_effects in the LMM does not guarantee this order.)
    for worker_id in sorted(cell_parameters):

        # Signal B of this worker: {"early": ..., "late": ..., "night": ...} in hours
        diffs = cell_parameters[worker_id]["diff_vs_off_hours"]

        row = []
        # Loop over the keys of SHIFT_CODES (off, early, late, night), so that
        # column number = shift code in model.py (0 = off, 1 = early, 2 = late, 3 = night).
        for shift in cf.SHIFT_CODES:
            if shift == "off":
                # diff_vs_off_hours has no "off" key: off compared with itself = 0
                row.append(0.0)
            else:
                row.append(diffs[shift])
        table.append(row)

    return table  # 30 rows x 4 columns, still in hours (not yet integers)

# Probability table (signal A per cell) for CPMpy
def make_p_table(cell_parameters):
    """
    Table of p_short_given_main_sleep: one row per worker (sorted on worker_id),
    one column per shift code (order of cf.SHIFT_CODES: off, early, late, night).
    Off is NOT 0: a free night also has a chance of being short.
    """
    table = []  # becomes a list of rows: one row per worker

    # Same row order as make_diff_table: W001, ..., W030
    for worker_id in sorted(cell_parameters):

        # Estimated mean sleep per linked shift, in hours (includes "off")
        means = cell_parameters[worker_id]["mean_hours"]
        # Night-to-night spread of this worker, in hours
        sigma = cell_parameters[worker_id]["sigma_hours"]

        row = []
        # Same column order as make_diff_table: 0 = off, 1 = early, 2 = late, 3 = night
        for shift in cf.SHIFT_CODES:
            # Probability of a short night, given that there is a main sleep episode
            row.append(p_short_given_main_sleep(means[shift], sigma))
        table.append(row)

    return table  # 30 rows x 4 columns, probabilities between 0 and 1 (not yet integers)

# Convert a table to integers (for CPMPY solver)
# Use:
# diff_table_int = to_integer_table(make_diff_table(cell_parameters), 60)
# p_table_int = to_integer_table(make_p_table(cell_parameters), 1000)

# Because of rounding, T will differ from score_roster by at most half a minute
# per night, and K by at most 0.0005 per night.
def to_integer_table(table, scale):
    """
    Multiply every value by scale and round to the nearest integer.
    Example: scale=60 turns hours into minutes, scale=1000 turns a
    probability into "per thousand".
    """
    integer_table = []
    for row in table:
        integer_row = []
        for value in row:
            # round() gives the nearest integer; int() makes sure it is an int
            integer_row.append(int(round(value * scale)))
        integer_table.append(integer_row)
    return integer_table

# [Added 2026-11-11] Check: T and K from the integer tables must match score_roster (up to rounding)
def check_against_score_roster(rosters, cell_parameters, diff_table_int, p_table_int):
    """
    For each worker: compute T and K once with the tables (count of linked
    nights x table value) and once with score_roster, and print both.
    """
    for row_number, worker_id in enumerate(sorted(cell_parameters)):  # row_number = row in the tables
        # Same linkage as score_roster, including the extra night after the roster
        linked_shifts = link_roster(rosters[worker_id], include_next_date=True)

        T_table = 0
        K_table = 0
        for linked in linked_shifts:
            column = cf.SHIFT_CODES[linked]  # "early" -> 1, etc.
            T_table += diff_table_int[row_number][column]
            K_table += p_table_int[row_number][column]

        scores = score_roster(rosters[worker_id], cell_parameters[worker_id])

        # Back to hours and to expected number of short nights, for comparison
        print(worker_id,
              "T table:", round(T_table / 60, 3), "T score_roster:", round(scores["cumulative_diff_hours"], 3),
              "| K table:", round(K_table / 1000, 3), "K score_roster:",
              round(scores["expected_short_nights_given_main_sleep"], 3))


# Build and print both tables from the historical sleep data
if __name__ == "__main__":
    # data/ folder at the root of the repo (one level above scheduler/)
    data_dir = Path(__file__).resolve().parent.parent / "data"
    sleep_records = pd.read_csv(data_dir / "historical_sleep.csv").to_dict("records")

    # Fit the LMM; result (the statsmodels object) is not needed here
    # The LMM is fitted once when cost_table.py is executed. The resulting parameters are used to construct the T and K cost tables.
    cell_parameters, result = estimate_cell_parameters_lmm(sleep_records)
    
    difference_table = make_diff_table(cell_parameters) # uses diff_vs_off_hours
    difference_table_int = to_integer_table(difference_table, 60)
    
    p_table = make_p_table(cell_parameters) # uses mean_hours and sigma_hours
    p_table_int = to_integer_table(p_table, 1000)

    # One line per worker; columns in the order off, early, late, night
    print("Difference table (minutes vs own off night):")
    for worker_id, row in zip(sorted(cell_parameters), difference_table_int):
        print(worker_id, row)

    print("\nProbability table (short night, per thousand):")
    for worker_id, row in zip(sorted(cell_parameters), p_table_int):
        print(worker_id, row)
    
    
    # [Added 2026-11-11] Check the tables against score_roster on the historical roster
    # Scale differences: minutes for T (instead of hours) and probabilities × 1000 for K
    assignment_records = pd.read_csv(data_dir / "historical_assignments.csv").to_dict("records")
    rosters = get_rosters_from_records(assignment_records)
    print("\nCheck against score_roster:")
    check_against_score_roster(rosters, cell_parameters, difference_table_int, p_table_int)
    
    ##################################################
    # [Added 2026-11-11] Write both tables to one Excel file (two sheets), date in the file name
    from datetime import date

    columns = list(cf.SHIFT_CODES)  # off, early, late, night
    worker_ids = sorted(cell_parameters)  # same row order as the tables

    diff_df = pd.DataFrame(difference_table_int, index=worker_ids, columns=columns)
    p_df = pd.DataFrame(p_table_int, index=worker_ids, columns=columns)
    diff_df.index.name = "worker_id"
    p_df.index.name = "worker_id"

    output_dir = Path(__file__).resolve().parent / "output"  # scheduler/output/
    output_dir.mkdir(exist_ok=True)  # create the folder if it does not exist yet
    output_path = output_dir / f"cost_table_{date.today().isoformat()}.xlsx"  # e.g. cost_table_2026-11-11.xlsx

    with pd.ExcelWriter(output_path) as writer:
        diff_df.to_excel(writer, sheet_name="diff_minutes")
        p_df.to_excel(writer, sheet_name="p_short_per_thousand")

    print(f"\nWritten to {output_path}")