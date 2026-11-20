# -*- coding: utf-8 -*-
"""
roster_table.py

Purpose: turn the historical roster and the candidate roster into a readable text table,
one letter per day, so the changes made by the solver can be seen at a glance.
Used by GET /roster-comparison/table in api/main.py.

The rosters come from data/roster_comparison.json, in the format {"W001": ["early", ...], ...}.
This module does not read the file itself.
"""

# One letter per shift type; off is a dot so the working blocks stand out
SHIFT_LETTERS = {
    "early": "E",
    "late": "L",
    "night": "N",
    "off": ".",
}

# Number of days per week: a space is placed after each week
DAYS_PER_WEEK = 7


def roster_to_line(shifts):
    """
    Turn the roster of one worker (a list of shift names, one per day) into one line
    of letters, with a space after every week.
    Example: ["early", "early", ..., "off"] -> "EEEEEEE ..LLLLL ..."
    """
    line = ""
    for day in range(len(shifts)):
        # Space before each new week, not before the first day
        if day > 0 and day % DAYS_PER_WEEK == 0:
            line = line + " "
        line = line + SHIFT_LETTERS[shifts[day]]
    return line


def changes_line(historical_shifts, candidate_shifts):
    """
    Compare the historical and the candidate roster of one worker day by day.
    Returns a line with "^" on each day where the shift differs and a space where it is
    the same, with the same week spacing as roster_to_line, so each "^" sits under its day.
    """
    if len(historical_shifts) != len(candidate_shifts):
        raise ValueError("Historical and candidate roster have a different number of days.")

    line = ""
    for day in range(len(historical_shifts)):
        if day > 0 and day % DAYS_PER_WEEK == 0:
            line = line + " "
        if historical_shifts[day] != candidate_shifts[day]:
            line = line + "^"
        else:
            line = line + " "
    # Trailing spaces carry no information
    return line.rstrip()


def build_roster_table(historical_rosters, candidate_rosters):
    """
    Build the full text table: title, legend, a header with week numbers, and per worker
    three lines (historical roster, candidate roster, changes), followed by an empty line.
    Both inputs have the format {"W001": ["early", ...], ...} and must contain the same workers.
    Returns one string.
    """
    if sorted(historical_rosters) != sorted(candidate_rosters):
        raise ValueError("Historical and candidate roster contain different workers.")

    workers = sorted(historical_rosters)

    lines = []
    # Title and legend
    lines.append("Roster comparison: historical roster (cycle 1) vs candidate roster of the solver")
    lines.append("E = early, L = late, N = night, . = off, ^ = shift changed by the solver")
    lines.append("")

    # Header with week numbers, aligned with the roster lines below.
    # The text in front of each roster line ("W001  hist  ") sets the width of the empty start.
    prefix_width = len(workers[0] + "  hist  ")
    number_of_days = len(historical_rosters[workers[0]])
    # Number of weeks, rounded up (28 days -> 4 weeks)
    number_of_weeks = (number_of_days + DAYS_PER_WEEK - 1) // DAYS_PER_WEEK
    header = " " * prefix_width
    for week in range(number_of_weeks):
        label = "week " + str(week + 1)
        # Each week takes 7 letters plus 1 space
        header = header + label.ljust(DAYS_PER_WEEK + 1)
    lines.append(header.rstrip())

    for worker in workers:
        historical_shifts = historical_rosters[worker]
        candidate_shifts = candidate_rosters[worker]
        lines.append(worker + "  hist  " + roster_to_line(historical_shifts))
        lines.append(worker + "  cand  " + roster_to_line(candidate_shifts))
        changes = " " * prefix_width + changes_line(historical_shifts, candidate_shifts)
        # A worker without changes gets an empty line here
        lines.append(changes.rstrip())
        lines.append("")

    return "\n".join(lines)
