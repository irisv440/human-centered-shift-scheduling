# -*- coding: utf-8 -*-
"""
requirements_config.py

Notes on the shift system:
Each team rotates through the same cycle, shifting by one week. So each
  day, one team works the Early shift, one the Late shift, one the Night shift, and the fourth team is off.
  Changed: "each week" -> "each day": the 2- and 3-day off blocks shift this pattern within a week.

Each team has one supervisor and two senior operators;
  the rest are operators.

@author: irisv
"""

TEAM_SIZES = {"A": 8, "B": 8, "C": 7, "D": 7}  # number of workers per team; in the model, teams are coded 0-3 (see TEAM_SIZES_CODES)
TEAM_OFFSETS = {"A": 0, "B": 7, "C": 14, "D": 21}

# Derived from TEAM_SIZES.
# Result: {0: 8, 1: 8, 2: 7, 3: 7}  # 0=A, 1=B, 2=C, 3=D
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
n_cycles = n_days // cycle_length  # number of full cycles in the horizon; n_days must be a multiple of cycle_length
contract_hours = 38  # not (yet) used in the model; kept as documentation (same as contract_hours_week in the data).
n_workers = sum(TEAM_SIZES.values()) # in our example: 30 workers

# Rostered maximum, separate from contract_hours:
# the contract is 38h per week, the roster gives 42h per week (21 shifts x 8h per cycle);
# the difference is compensated outside the roster.
max_hours_per_week = 42
max_hours_per_cycle = int(max_hours_per_week * (cycle_length // 7))  # 42 x 4 = 168


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

# Which shift each team has on each day of the horizon.
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

# ROLE coded as numbers instead of strings, so it can go into a cpm_array:
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

# Off requests, one row per worker (W001-W030), one column per day (0-27), grouped per week.
# -5 = no request, -1 = no early, -2 = no late, -3 = no night, -4 = no shift at all (day off).
# Soft: a violated request adds request_penalty_minutes to the objective (see below).
# Chosen by hand: almost every request falls on a day on which the worker's home team has that
# shift. A -1/-2/-3 request is then granted by putting the worker in another team that day;
# a -4 request by letting the worker be off while the home team works (only allowed on a -4 day,
# see model.py). Three requests fall on an off-day of the home team on purpose
# (W010 day 5, W012 day 26, W021 day 19): they can never be violated.
requests = [
    # days 0-6                   days 7-13                    days 14-20                   days 21-27
    [-5, -5, -3, -5, -5, -5, -5,  -5, -5, -5, -4, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5],  # W001 (D)
    [-5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -2, -5, -5,  -5, -5, -5, -5, -5, -5, -5],  # W002 (D)
    [-5, -5, -5, -5, -5, -2, -5,  -5, -5, -5, -5, -5, -5, -5,  -3, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -4, -5, -5, -5],  # W003 (B)
    [-5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -3, -5,  -5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5],  # W004 (B)
    [-5, -5, -5, -5, -5, -5, -5,  -5, -1, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -2,  -5, -5, -5, -5, -5, -5, -5],  # W005 (D)
    [-5, -5, -5, -5, -5, -5, -3,  -5, -5, -5, -5, -5, -5, -5,  -5, -5, -4, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5],  # W006 (C)
    [-5, -5, -5, -1, -5, -5, -5,  -5, -5, -5, -5, -5, -2, -5,  -5, -5, -5, -5, -5, -5, -5,  -3, -5, -5, -5, -5, -5, -5],  # W007 (A)
    [-5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -2, -5, -5],  # W008 (C)
    [-5, -5, -5, -5, -5, -5, -5,  -5, -5, -3, -5, -5, -5, -5,  -5, -5, -5, -1, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5],  # W009 (C)
    [-5, -4, -5, -5, -5, -1, -5,  -5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5],  # W010 (D)
    [-5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -1, -5, -5,  -5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5],  # W011 (D)
    [-5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -3, -5,  -5, -5, -5, -5, -5, -4, -5],  # W012 (A)
    [-5, -1, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5,  -2, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5],  # W013 (A)
    [-5, -5, -5, -2, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5,  -5, -1, -5, -5, -5, -5, -5],  # W014 (B)
    [-5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5,  -5, -5, -3, -5, -5, -5, -5],  # W015 (A)
    [-5, -5, -5, -5, -5, -3, -5,  -3, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -4, -5, -5,  -5, -5, -5, -5, -5, -5, -5],  # W016 (C)
    [-5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -2, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -4,  -5, -5, -5, -5, -5, -5, -5],  # W017 (A)
    [-5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5,  -5, -3, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5],  # W018 (B)
    [-2, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -2, -5],  # W019 (C)
    [-5, -5, -5, -5, -5, -5, -5,  -4, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -1, -5, -5],  # W020 (B)
    [-5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -3,  -5, -5, -5, -5, -5, -2, -5,  -5, -5, -5, -5, -5, -5, -5],  # W021 (B)
    [-5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5,  -5, -1, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5],  # W022 (C)
    [-5, -5, -5, -5, -2, -5, -5,  -5, -5, -5, -5, -5, -5, -5,  -5, -5, -3, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -1],  # W023 (B)
    [-5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5,  -5, -5, -4, -5, -5, -5, -5],  # W024 (B)
    [-5, -5, -5, -5, -5, -1, -5,  -5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5,  -5, -3, -5, -5, -5, -5, -5],  # W025 (A)
    [-5, -5, -5, -5, -5, -5, -5,  -5, -3, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -2, -5, -5, -5],  # W026 (C)
    [-5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -2,  -5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5],  # W027 (A)
    [-5, -5, -5, -5, -5, -5, -5,  -5, -5, -1, -5, -5, -5, -5,  -5, -5, -5, -2, -5, -5, -5,  -5, -5, -5, -5, -5, -3, -5],  # W028 (D)
    [-5, -5, -4, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5],  # W029 (A)
    [-3, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5,  -5, -5, -5, -5, -5, -5, -5,  -2, -5, -5, -5, -5, -5, -5],  # W030 (D)
]

# Objective settings

# Used by make_objective (scheduler/model.py) and validation/compare_rosters.py.
# Values still to be tuned.
# Threshold: maximum acceptable expected number of short nights per worker over the roster,
# in thousandths of a night (10000 = 10 short nights), same unit as p_table_int.
objective_threshold_thousandths = 10000

# Weight: 0.36 minutes of sleep loss per thousandth of a short night above the threshold
# (= 360 minutes per short night). The solver needs whole numbers, so the whole objective is
# multiplied by 100: sleep loss in minutes x 100, plus 36 x excess in thousandths.
objective_scale = 100
objective_weight = 36

# Penalty per violated off request (cf. requests), in minutes of sleep loss.
# Value still to be tuned: 60 = one violated request weighs as much as one hour of sleep loss.
request_penalty_minutes = 60
