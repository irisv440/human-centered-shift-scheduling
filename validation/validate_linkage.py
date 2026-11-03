# -*- coding: utf-8 -*-
"""
Validate_linkage.py

Cross-check: does evaluator/linkage.py give the same linked shift as the generator, stored in
historical_sleep.csv?
Works with Indicator=True to ..

Run from the main project folder: python -m validation.validate_linkage

@author: irisv
"""

from pathlib import Path
import pandas as pd

from evaluator.linkage import link_roster


DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def main():
    roster = pd.read_csv(DATA_DIR / "historical_assignments.csv")
    historical_sleep = pd.read_csv(DATA_DIR / "historical_sleep.csv")

    # Date order per worker: link_roster depends on the order
    roster = roster.sort_values(["worker_id", "date"])

    # Apply the linkage rule per worker
    rows = []
    # from historical_assignments:
    for worker_id, worker_roster in roster.groupby("worker_id"):
        dates = worker_roster["date"].tolist()
        linked_shifts = link_roster(worker_roster["shift_type"].tolist())

        for date, linked_shift in zip(dates, linked_shifts):
            rows.append({
                "worker_id": worker_id,
                "sleep_date": date,
                "computed_linked_shift": linked_shift,
            })
    computed = pd.DataFrame(rows)
    
    ####### Use 

    # Outer merge: dates that exist in only one of the two tables stay visible
    merged = computed.merge(
        historical_sleep[["worker_id", "sleep_date", "linked_shift"]],
        on=["worker_id", "sleep_date"],
        how="outer", # for visibility of unmatched records (shown as Nan alongside computed_linked_shift or linked_shift)
        indicator=True, # adds an extra column "_merge" with value both, left_only or right_only
    )
    in_both = merged[merged["_merge"] == "both"] # No records with NaN in one of both tables, both computed_linked_shift and linked_shift have a value (not NaN)
    different = in_both[in_both["computed_linked_shift"] != in_both["linked_shift"]] # No records with Nan, shows records where computed_linked_shift != linked_shift from historical_sleep table
    
    print(merged.head(10))

    print("Rows in roster:", len(computed))
    print("Rows in sleep data:", len(historical_sleep))
    print("Rows in only one table:", len(merged) - len(in_both))
    print("Compared rows:", len(in_both))
    print("Different linked shift:", len(different))

    if len(different) > 0:
        print(different.head(10).to_string(index=False))


if __name__ == "__main__":
    main()

