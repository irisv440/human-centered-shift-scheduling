# -*- coding: utf-8 -*-
"""
evaluator/objective.py

Computes the value of the objective for one roster, from the output of
score_all_workers. Smaller is better.

In words, the objective adds up two things:
1. The total sleep loss of all workers over all linked nights, in minutes.
   This part always steers: it looks for the roster with the least sleep
   lost compared to Off nights.
2. A penalty for every worker who goes above the threshold for short
   nights. Only the part above the threshold counts, multiplied by a
   weight. This part stays silent as long as everyone is below the
   threshold: it is a guard rail, not a second steering wheel. It only
   steps in for workers who lose little sleep in minutes but sit close to
   the 6 hour limit.

Per worker, three quantities:
- sleep_loss: sum over the linked nights of minus T for the linked shift
  type, in minutes. An Off night adds 0. Because of the minus sign, a loss
  is a positive number, so smaller is better.
- short_nights: sum over the linked nights of K for the linked shift type,
  including Off nights, because the threshold is about all short nights.
- excess: short_nights minus the threshold, but never below 0. So 0 as long
  as the worker stays below the threshold; above it, only the part that
  sticks out.

Then, over all workers together:
    objective = sum of sleep_loss
              + weight times the sum of excess

The weight says how many minutes of sleep loss for the group we accept to
avoid one expected short night above the threshold.

This is the calculation version, used to score an existing roster (baseline
or candidate). The solver in scheduler/model.py will need its own
formulation with the decision variables, following the same definition.

@author: irisv
"""

def compute_objective(results, threshold_thousandths, weight):
    """
    Compute the objective for one roster.

    Parameters
    ----------
    results : list of dict
        The output of score_all_workers, one dict per worker.
        Only these keys are used:
          1. "worker_id"                               str
          2. "cumulative_diff_hours"                   float or None (T, in hours)
          3. "expected_short_nights_given_main_sleep"  float or None (K, in nights)
    threshold_thousandths : int or float
        The maximum acceptable expected number of short nights per worker
        over the roster, in thousandths of a night (2500 = 2.5 nights).
        Thousandths, like the cost tables of the solver.
    weight : float
        Minutes of sleep loss per thousandth of a short night above the
        threshold (0.36 = 360 minutes per short night).

    Returns
    -------
    dict:
        {
          "objective": float,                   # total_sleep_loss_minutes + penalty
          "total_sleep_loss_minutes": float,    # sum of sleep_loss over the scored workers
          "total_excess_thousandths": float,    # sum of excess over the scored workers
          "penalty": float,                     # weight times total_excess_thousandths
          "per_worker": list of dict,           # one dict per scored worker, see below
          "unscored_workers": list of str,      # worker_ids without T and K, left out
        }

    "per_worker": one dict per scored worker:
        {
          "worker_id": str,
          "sleep_loss_minutes": float,          # minus T, times 60
          "short_nights_thousandths": float,    # K, times 1000
          "excess_thousandths": float,          # short nights above the threshold, never below 0
        }

    Units: T comes in hours and K in nights from score_all_workers. They are
    converted to minutes and thousandths, so the threshold and the weight
    mean the same here as in the solver later.
    """
    per_worker = []          # one dict per scored worker, filled in the loop
    unscored_workers = []    # worker_ids without T and K

    for row in results:
        # A worker either has BOTH T and K, or neither (both None),
        # so checking T alone tells whether the worker was scored.
        if row["cumulative_diff_hours"] is None:
            unscored_workers.append(row["worker_id"])
            continue # next worker
        
        # sleep loss: minus T (T is negative when sleep is lost), hours -> minutes
        sleep_loss_minutes = -row["cumulative_diff_hours"] * 60
        
        # short nights: K, nights -> thousandths of a night
        short_nights_thousandths = row["expected_short_nights_given_main_sleep"] * 1000
        
        # excess: only the part above the threshold, never below 0
        excess_thousandths = max(0.0, short_nights_thousandths - threshold_thousandths)

        per_worker.append({
            "worker_id": row["worker_id"],
            "sleep_loss_minutes": sleep_loss_minutes,
            "short_nights_thousandths": short_nights_thousandths,
            "excess_thousandths": excess_thousandths,
        })
        
    # Totals over the scored workers
    total_sleep_loss_minutes = 0.0 # related to 'T'
    total_excess_thousandths = 0.0 # related to 'K'
    
    for worker in per_worker:
        total_sleep_loss_minutes += worker["sleep_loss_minutes"]
        total_excess_thousandths += worker["excess_thousandths"]

    # Penalty: only the short nights above the threshold, times the weight
    penalty = weight * total_excess_thousandths
    objective = total_sleep_loss_minutes + penalty

    return {
        "objective": objective,
        "total_sleep_loss_minutes": total_sleep_loss_minutes,
        "total_excess_thousandths": total_excess_thousandths,
        "penalty": penalty,
        "per_worker": per_worker,
        "unscored_workers": unscored_workers,
    }

