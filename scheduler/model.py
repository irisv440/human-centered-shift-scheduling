# -*- coding: utf-8 -*-
"""
model.py

CPMpy roster model: decision variables, linkage of sleep to shifts, labour and staffing
constraints, and the objective (sleep loss plus a penalty on expected short nights).

@author: irisv
"""

import cpmpy as cp
import numpy as np
import pandas as pd
from cpmpy.solvers.solver_interface import ExitStatus
from pathlib import Path
import sys

# [Added 2026-11-16] Makes 'from scheduler import ...' work when running this file with F5,
# whatever the working directory is: adds the repo root to the import path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scheduler import requirements_config as cf
from scheduler import cost_table

from evaluator.estimate_lmm import estimate_cell_parameters_lmm


def make_objective(early_linked, late_linked, night_linked, off_linked, difference_table_int, p_table_int): # [Changed 2026-11-16 18:24] off_linked added
    """
    Objective of the solver: same definition as compute_objective in evaluator/objective.py,
    in whole numbers.

    Per worker i, summed over the 29 linked nights:
      sleep_loss[i]               = minus the sum of difference_table_int (minutes vs own Off night)
      short_nights_thousandths[i] = the sum of p_table_int (expected short nights x 1000, Off included)
      excess_thousandths[i]       = max(0, short_nights_thousandths[i] - threshold)

    objective = objective_scale x sum of sleep_loss + objective_weight x sum of excess_thousandths

    Threshold, scale and weight come from the config. compute_objective uses the weight
    objective_weight / objective_scale (0.36); the solver needs whole numbers, so here the whole
    objective is multiplied by objective_scale instead. Divide by objective_scale to compare.
    """
    sleep_loss = []

    for i in range(cf.n_workers):
        sleep_loss.append(-cp.sum(
            difference_table_int[i][0] * off_linked[i, night] # Cost * off_linked yes/no --> always zero
            + difference_table_int[i][1] * early_linked[i, night] # Cost * early_linked yes/no
            + difference_table_int[i][2] * late_linked[i, night] # Cost * late_linked yes/no
            + difference_table_int[i][3] * night_linked[i, night] # Cost * night_linked yes/no
            for night in range(cf.n_days + 1)
        ))

    short_nights_thousandths = []
    # cp.sum over the probabilities of a short night (x 1000), Off nights included
    for i in range(cf.n_workers):
        short_nights_thousandths.append(cp.sum(
            p_table_int[i][0] * off_linked[i, night] # Probability * off_linked yes/no
            + p_table_int[i][1] * early_linked[i, night] # Probability * early_linked yes/no
            + p_table_int[i][2] * late_linked[i, night] # Probability * late_linked yes/no
            + p_table_int[i][3] * night_linked[i, night] # Probability * night_linked yes/no
            for night in range(cf.n_days + 1)
        ))

    excess_thousandths = []
    # Per worker: expected short nights (thousandths) above the threshold, never below 0
    for i in range(cf.n_workers):
        excess_thousandths.append(cp.max([0, short_nights_thousandths[i] - cf.objective_threshold_thousandths]))

    # [Changed 2026-11-16] 100 and 36 read from the config (same values) instead of typed in
    objective = cf.objective_scale * cp.sum(sleep_loss) + cf.objective_weight * cp.sum(excess_thousandths)

    return objective

# Linkage rule, cpmpy variant of the linkage rule in 'linkage.py'
def add_linkage(model, early_linked, late_linked, night_linked, off_linked, shifts):
    
    """
    Linkage rule, in CPMpy terms.
    Same rule as evaluator/linkage.py, now on variables:
      night t is Early if day t is Early;
      else Night if day t-1 was Night; else Late if day t-1 was Late; else Off.

    Assumptions (must match link_roster):
      - the day before the roster is not Late nor Night;
      - the day after the roster is not Early.

    [Changed 2026-11-16 18:21] Off-linked is explicit (off_linked), no longer implicit:
    a sleep_date is Off-linked when it is not Early-, Late- or Night-linked.
    This is enforced by "exactly one of the four linked types per worker per night"
    (the cp.sum(...) == 1 constraint at the end of this function).
    """
    
    for i in range(cf.n_workers):
        for t in range(cf.n_days + 1): # cf.n_days + 1 = range(28+1) --> range 29 but loops from 0 to 28 (29 days in total)
            # early linked gets preference
            model.add(early_linked[i,t] == (shifts[i,t] == 1) if t < cf.n_days else ~ early_linked[i,t]) # if t between 0 and 27: can be early linked, however if t=28 --> outside roster
            
            if t == 0: # edge case at start of the roster
                model.add(late_linked[i,t] == 0) # late shift would have taken place outside the roster (1 day before the horizon) -- our assumption: day before roster is not Late or Night
                model.add(night_linked[i,t] == 0) # (!) assumption: day before roster was not night or late
            else: # e.g. t == 1 --> t=0 was possibly late or night
                # late linked
                model.add(late_linked[i,t] == (shifts[i,t-1] == 2) & ~early_linked[i,t])
                # night linked
                model.add(night_linked[i,t] == (shifts[i,t-1] == 3) & ~early_linked[i,t])
    
    # Exactly one of the four linked types per worker per night
    for i in range(cf.n_workers):
        for t in range(cf.n_days + 1):
            model.add(cp.sum([early_linked[i,t], late_linked[i,t], night_linked[i,t], off_linked[i,t]]) == 1)


def build_model():
    
    # 1. Prepare the data
    
    # Data dir
    data_dir = Path(__file__).resolve().parent.parent / "data"
    # Load historical sleep in order to estimate LMM parameters
    sleep_records = pd.read_csv(data_dir / "historical_sleep.csv").to_dict("records")
    
    # Fit the LMM
    cell_parameters, result = estimate_cell_parameters_lmm(sleep_records)
    
    # Make differences table and convert the table contents into integers that represent minutes (hours * 60)
    difference_table = cost_table.make_diff_table(cell_parameters) # uses diff_vs_off_hours
    difference_table_int = cost_table.to_integer_table(difference_table, 60)
    
    # Make table and convert the table contents to integers (*1000)
    p_table = cost_table.make_p_table(cell_parameters) # uses mean_hours and sigma_hours
    p_table_int = cost_table.to_integer_table(p_table, 1000)
    
    # difference_table_int: list[list[int]], represents minutes
    # p_table_int: list[list[int]]
    
    
    # 2. Main decision variables 
 
    # Shifts[i,d] denotes the shift that worker i should work on day d.
    # 0 = off, 1 = early, 2 = late, 3 = night (cf.SHIFT_CODES)
    shifts = cp.intvar(0,3, shape=(cf.n_workers, cf.n_days), name = 'shifts')
    

    # --> the decision variable 'assigned_team' supports (occasional) swaps:
    # a worker's home_team stays the same, while the assigned team denotes which team the worker is assigned to during a particular day, e.g. because they asked
    # for a swap.
    
    # assigned team: its values denote the real team a worker is assigned to at a particular day.
    assigned_team = cp.intvar(0,cf.n_teams-1, shape = (cf.n_workers, cf.n_days), name = 'assigned_team') # example: 4 teams
    
    # Constant arrays
    team_shift_CP = cp.cpm_array(cf.TEAM_SHIFT)   # 4 teams x 28 days
    home_team_CP = cp.cpm_array(cf.HOME_TEAM)     # 30 workers
    shift_times_CP = cp.cpm_array(cf.SHIFT_TIMES)
    role_np = np.array(cf.ROLE)
    
    # 3.The model 
    
    model = cp.Model()


    # 4.  Linkage variables  & add_linkage(model, decision variables) 
    early_linked = cp.boolvar(shape=(cf.n_workers, cf.n_days + 1), name='early_linked')
    late_linked = cp.boolvar(shape=(cf.n_workers, cf.n_days + 1), name='late_linked')
    night_linked = cp.boolvar(shape=(cf.n_workers, cf.n_days + 1), name='night_linked')
    off_linked = cp.boolvar(shape=(cf.n_workers, cf.n_days + 1), name='off_linked') 
    
    # call function add_linkage: the linkage constraints are added using that definition
    add_linkage(model, early_linked, late_linked, night_linked, off_linked, shifts)
    
   
    """ Constraints """
       
    
    """ Rest Constraints:
        # Each worker must have at least 11 hours of rest between consecutive shifts
        # Each worker must work at most 7 consecutive days.
        # Each worker must have at least 2 full days off after 7 consecutive working days.
        Source: https://werk.belgie.be/nl/themas/arbeidsreglementering/arbeidsduur-en-rusttijden/rusttijden
    """
    # Viewpoint of shifts: 
    # For each worker, take every shift pair and put the constraint on that pair of shifts that time beween both should be
    # at least 11h 
    for i in range(cf.n_workers):
        for t1 in range(cf.n_days - 1):
            for t2 in range(t1+1, cf.n_days):
                # only consecutive pairs:
                if t1 == t2 - 1:
                    # If neither of the days is an off-day, force the 11-hour rest constraint
                    # Start of shift on t2 + 24 (given the day difference) - end time of shift on t1
                    # shift_times_CP[shift, 0]: row and column in one bracket, needed to index with a variable
                    model.add( ((shifts[i,t1] != 0) & (shifts[i,t2] != 0)).implies( shift_times_CP[shifts[i,t2], 0] + 24 - shift_times_CP[shifts[i,t1], 1] >= 11))
    

    # Each worker must work at most 7 consecutive days:
    # in every window of 8 consecutive days there is at least one off-day (0).
    for i in range(cf.n_workers):
        for t in range(cf.n_days - 7):
            model.add(cp.Count(shifts[i, t:t + 8], 0) >= 1)
    
    # Each worker must have at least 2 full days off after 7 consecutive working days:
    for i in range(cf.n_workers):
        for t in range(cf.n_days - 8):
            model.add( (~cp.any(shifts[i,t:t+7] == 0)).implies(cp.all(shifts[i,t+7:t+9] == 0)) )
    
    """
    Each shift must be staffed by at least 1 supervisor, at least 2 senior operators, and at least 4 operators.
    
    """
    # Viewpoint of assigned_teams: 
    # for each day in range(cf.n_days):  
    # For each team in range(cf.n_teams): 
    for t in range(cf.n_days):
        for team in range(cf.n_teams):
            if cf.TEAM_SHIFT[team][t] != 0:
                # select the workers that are supervisors with role_np==0, and count them
                # Reads as: "the amount of supervisors assigned to the team today should be at least 1"
                model.add(cp.sum(assigned_team[role_np == 0, t] == team) >= 1)
                # select the workers that are senior operators with role_np==1, and count them
                model.add(cp.sum(assigned_team[role_np == 1, t] == team) >= 2)
                model.add(cp.sum(assigned_team[role_np == 2, t] == team) >= 4)
    
        
    """
    Each team must have the required amount of team members for each roster day, as specified in cf.TEAM_SIZES
    """
    # Viewpoint of assigned_teams:
    for t in range(cf.n_days):
        for team in range(cf.n_teams): # 0 1 2 3, a b c d
            if cf.TEAM_SHIFT[team][t] != 0:
                # alternatively cp.Count(assigned_team[:, t], team) == cf.TEAM_SIZES_CODES[team] 
                model.add(cp.sum(assigned_team[i,t] == team for i in range(cf.n_workers)) == cf.TEAM_SIZES_CODES[team])
    
    
    
    """
    Each worker must work at most 168 hours per 28-day cycle.
    """
    #  Counters per worker and per cycle,
    # maximum from cf.max_hours_per_cycle instead of 168.
    # early_count[i, c] = number of early shifts of worker i in cycle c
    early_count = cp.intvar(0, cf.cycle_length, shape=(cf.n_workers, cf.n_cycles), name = 'early_count') # max = cycle length (would mean 28 early shifts in a cycle)
    late_count = cp.intvar(0, cf.cycle_length, shape=(cf.n_workers, cf.n_cycles), name = 'late_count')
    night_count = cp.intvar(0, cf.cycle_length, shape=(cf.n_workers, cf.n_cycles), name = 'night_count')

    # Working hours are most easily counted using the shifts_viewpoint
    for i in range(cf.n_workers): # how many times is worker i working early, late and night?
        for c in range(cf.n_cycles):
            cycle_start = c * cf.cycle_length # eg cycle 0: day 0, cycle 1: day 28
            cycle_end = cycle_start + cf.cycle_length
            model.add(early_count[i, c] == cp.Count(shifts[i, cycle_start:cycle_end], 1))
            model.add(late_count[i, c] == cp.Count(shifts[i, cycle_start:cycle_end], 2))
            model.add(night_count[i, c] == cp.Count(shifts[i, cycle_start:cycle_end], 3))
            # restriction over one cycle
            model.add(early_count[i, c]*cf.HOURS_PER_SHIFT['early'] + late_count[i, c]*cf.HOURS_PER_SHIFT['late'] + night_count[i, c]*cf.HOURS_PER_SHIFT['night'] <= cf.max_hours_per_cycle)
        

    """
    Channeling constraint between 'shifts' and 'assigned_team':
        
        shifts is cp.intvar(0, 3, shape=(cf.n_workers, cf.n_days)). Each cell shifts[i,d] takes exactly one value (off, early,
     late or night), so a worker can never have two shifts on one day. No extra constraint is needed: this follows from
     the shifts variable itself, even without the teams.
    
     assigned_team also has one value per worker per day, but its link to shifts does not follow automatically. Without an
     extra constraint, the solver could put a worker in team B and still let them work a different shift than team B has
     that day. So we still need a constraint saying that the shift of worker i on day d equals the shift of their
     assigned_team[i,d] on that day. Only then are the two variables consistent with each other.
     
     https://developers.google.com/optimization/scheduling/employee_scheduling
        
    """
        
    for i in range(cf.n_workers):
        for t in range(cf.n_days):
            for s in cf.SHIFT_CODES.values():
                # Two-way channelling
                model.add( (shifts[i,t] == s) == (team_shift_CP[assigned_team[i,t],t] == s) )
               
    
    """
    Constraint: On an Off-day assigned_team should equal home_team
    """
    
    for i in range(cf.n_workers):
        for t in range(cf.n_days):
            model.add((shifts[i,t] == 0).implies(assigned_team[i,t] == home_team_CP[i]))
    
    
    """
    Constraint: handling "shift on requests" and "shift off requests"
    Shift on/off requests can be handled by putting constraints on assigned_team[i,t]
    
    """
    # Planned, not yet implemented.


    """
    Objective: same definition as compute_objective in evaluator/objective.py (see make_objective)
    """
    objective = make_objective(early_linked, late_linked, night_linked, off_linked, difference_table_int, p_table_int)
    model.minimize(objective)

    # 5. Return the model
    return model, shifts, assigned_team, early_linked, late_linked, night_linked, off_linked, objective

if __name__ == "__main__":
    # Run from the project root:  python -m scheduler.model

    model, shifts, assigned_team, early_linked, late_linked, night_linked, off_linked, objective = build_model()
    
    model.solve()
    
    print(model.status())
    
    if model.status().exitstatus == ExitStatus.FEASIBLE or model.status().exitstatus == ExitStatus.OPTIMAL:
        for w in range(cf.n_workers):
            print(shifts[w,:].value())
        # Objective value in solver units (x objective_scale): not directly comparable with compute_objective
        print("objective:", objective.value())
        # Divided by objective_scale (100): same unit as compute_objective (minutes), so it can be
        # compared with the historical roster of cycle 1 (72235.36 with the same integer tables)
        print("objective / objective_scale:", objective.value() / cf.objective_scale)

