# -*- coding: utf-8 -*-
"""
requirements_config.py

Notes on the shift system:
Each team rotates through the same cycle, shifting by one week. So each
  day, one team works the Early shift, one the Late shift, one the Night shift, and the fourth team is off.
  [Changed 2026-11-15 14:14] "each week" -> "each day": the 2- and 3-day off blocks shift this pattern within a week.

Each team has one supervisor and two senior operators;
  the rest are operators.

@author: irisv
"""

TEAM_SIZES = {"A": 8, "B": 8, "C": 7, "D": 7}  # AMOUNT OF WORKERS PER TEAM, assigned_team uses 0–3!
TEAM_OFFSETS = {"A": 0, "B": 7, "C": 14, "D": 21}

# [Changed 2026-11-15 14:14] Derived from TEAM_SIZES instead of typed a second time,
# so both always hold the same numbers. Result: {0: 8, 1: 8, 2: 7, 3: 7}  # 0=A, 1=B, 2=C, 3=D
TEAM_SIZES_CODES = {}
team_index = 0
for team in TEAM_SIZES:  # order of TEAM_SIZES: A, B, C, D
    TEAM_SIZES_CODES[team_index] = TEAM_SIZES[team]
    team_index += 1


# 0 = off, 1 = early, 2 = late, 3 = night.
SHIFT_CODES = {"off": 0, "early": 1, "late": 2, "night": 3}

# SHIFT_TIMES[code] = [start, end], row 0 = off, 1 = early, 2 = late, 3 = night.
# "night" always starts at 22:00 and ends at 6:00 the next day (24 + 6 = 30).
# Off has no times; [0, 0] is only a placeholder (CPMpy arrays cannot contain None).
SHIFT_TIMES = [[0, 0], [6, 14], [14, 22], [22, 30]]

HOURS_PER_SHIFT = {} # Dictionary storing the hours worked in every shift
for shift, code in SHIFT_CODES.items():
    if shift != "off":
        HOURS_PER_SHIFT[shift] = SHIFT_TIMES[code][1] - SHIFT_TIMES[code][0] # e.g. 30 - 22

n_teams = len(TEAM_SIZES)

n_days = 28 # horizon
cycle_length = 28
n_cycles = n_days // cycle_length  # [Added 2026-11-15 13:40] number of full cycles in the horizon; n_days must be a multiple of cycle_length
contract_hours = 38  # [Changed 2026-11-15 14:14] not used in the model; kept as documentation (same as contract_hours_week in the data). n_weeks removed (unused).
n_workers = sum(TEAM_SIZES.values()) # in our example: 30 workers

# [Changed 2026-11-15 13:40] Rostered maximum, separate from contract_hours:
# the contract is 38h per week, the roster gives 42h per week (21 shifts x 8h per cycle);
# the difference is compensated outside the roster.
max_hours_per_week = 42
max_hours_per_cycle = int(max_hours_per_week * (cycle_length // 7))  # 42 x 4 = 168


# [Added 2026-11-07 22:06] Fixed team table: which shift each team has on each day of the horizon.
# (SHIFT_CODES is defined at the top of this file.)

# Same 28-day cycle as shift_for_cycle_day in data_generation/generate_historical_roster.py:
# 7 early, 2 off, 7 late, 2 off, 7 night, 3 off.
def shift_for_cycle_day(cycle_day):
    if 0 <= cycle_day <= 6:
        return "early"
    if 7 <= cycle_day <= 8:
        return "off"
    if 9 <= cycle_day <= 15:
        return "late"
    if 16 <= cycle_day <= 17:
        return "off"
    if 18 <= cycle_day <= 24:
        return "night"
    return "off"

# TEAM_SHIFT[team_index][day], team_index 0-3 = A, B, C, D (order of TEAM_SIZES).
# Assumption: day 0 of the horizon is cycle day 0 for team A (as on the first day of the historical roster).
TEAM_SHIFT = []
for team in TEAM_SIZES:
    offset = TEAM_OFFSETS[team] # e.g. TEAM_OFFSETS["B"] = 7
    row = []
    for day in range(n_days):
        cycle_day = (day + offset) % cycle_length # e.g 84 % 28 ==> cycle day 0 again
        row.append(SHIFT_CODES[shift_for_cycle_day(cycle_day)]) # calls shift for cycle day
    TEAM_SHIFT.append(row)

# [Changed 2026-11-14] ROLE coded as numbers instead of strings, so it can go into a cpm_array:
# 0 = supervisor, 1 = senior_operator, 2 = operator.
ROLE = [
    0, 2, 2, 1, 1,   # W001-W005  (sup, op, op, senior, senior)
    1, 2, 1, 0, 2,   # W006-W010  (senior, op, senior, sup, op)
    1, 1, 2, 2, 1,   # W011-W015  (senior, senior, op, op, senior)
    2, 2, 2, 2, 1,   # W016-W020  (op, op, op, op, senior)
    2, 2, 2, 0, 2,   # W021-W025  (op, op, op, sup, op)
    2, 0, 2, 2, 2,   # W026-W030  (op, sup, op, op, op)
]


# HOME_TEAM coded as team index, same as assigned_team and TEAM_SHIFT:
# 0 = A, 1 = B, 2 = C, 3 = D (order of TEAM_SIZES).
HOME_TEAM = [
    3, 3, 1, 1, 3,   # W001-W005  (D, D, B, B, D)
    2, 0, 2, 2, 3,   # W006-W010  (C, A, C, C, D)
    3, 0, 0, 1, 0,   # W011-W015  (D, A, A, B, A)
    2, 0, 1, 2, 1,   # W016-W020  (C, A, B, C, B)
    1, 2, 1, 1, 0,   # W021-W025  (B, C, B, B, A)
    2, 0, 3, 0, 3,   # W026-W030  (C, A, D, A, D)
]