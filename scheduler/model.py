# -*- coding: utf-8 -*-
"""
model.py

@author: irisv
"""

import cpmpy as cp
import numpy as np
import pandas as pd
from cpmpy.solvers.solver_interface import ExitStatus
from pathlib import Path

from scheduler import requirements_config as cf
from scheduler import cost_table

from evaluator.estimate_lmm import estimate_cell_parameters_lmm



# Linkage rule, cpmpy variant of the linkage rule in 'linkage.py'
def add_linkage(model, early_linked, late_linked, night_linked, shifts):
    
    """
    Linkage rule, in CPMpy terms 
    Same rule as evaluator/linkage.py, now on variables:
       night t is Early if day t is Early;
       else Night if day t-1 was Night; else Late if day t-1 was Late; else Off.
     Assumptions (must match link_roster): 
        1. the day before the roster is not Late nor Night,
     the date after the roster is not Early.
        2. 'Off'-linked is implicit. A sleep_date is 'off'-linked when 
        it is not early-linked, nor late- or night-linked.
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
    # 1= 'early', 2='late', 3='night, 0='off
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
    role_CP = cp.cpm_array(cf.ROLE)
    role_np = np.array(cf.ROLE)
    
    # 3.The model 
    
    model = cp.Model()


    # 4.  Linkage variables  & add_linkage(model, decision variables) 
    early_linked = cp.boolvar(shape=(cf.n_workers, cf.n_days + 1), name='early_linked')
    late_linked = cp.boolvar(shape=(cf.n_workers, cf.n_days + 1), name='late_linked')
    night_linked = cp.boolvar(shape=(cf.n_workers, cf.n_days + 1), name='night_linked')
    # no specific off-linked boolvar: Off is implicit 
    
    # call function add_linkage: the linkage constraints are added using that definition
    add_linkage(model, early_linked, late_linked, night_linked, shifts)
    
   
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
                    # Start of shift on T2 + 24 (given the day difference) - end time of shift on T1
                    # indexing changed from [shift][0] to [shift, 0] (row and column in one bracket)
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
    # TO DO (planned)
    
    
    
    """ Objective 
    
    Objective: TODO, same definition as "evaluator/objective.py"
    
    """
    
    # 5. Return the model
    return model, shifts, assigned_team, early_linked, late_linked, night_linked

if __name__ == "__main__":
    # Run from the project root:  python -m scheduler.model

    model, shifts, assigned_team, early_linked, late_linked, night_linked = build_model()
    
    model.solve()
    
    print(model.status())
    
    if model.status().exitstatus == ExitStatus.FEASIBLE or model.status().exitstatus == ExitStatus.OPTIMAL:
        for w in range(cf.n_workers):
            print(shifts[w,:].value())
        
