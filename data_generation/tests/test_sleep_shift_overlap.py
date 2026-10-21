"""
test_sleep_shift_overlap.py

Validates that no generated main sleep episode overlaps with ANY of a
worker's actual scheduled shifts (not only the shift it is linked to).

Run with: pytest data_generation/tests/test_sleep_shift_overlap.py -v
"""

from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import pytest

# Add folder of data location
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def _load_shift_intervals(assignments):
    """
    Build one [start, end) datetime interval per actual scheduled shift,
    grouped by worker_id. Off days have no interval. Night shifts cross
    midnight, so their end time is anchored to the day after `date`.
    """
    intervals = {} # dictionary, collects shifts, grouped by worker_id

    for row in assignments.itertuples(index=False):
        if row.shift_type == "off":
            continue

        shift_date = row.date.date() # take date out
        start_dt = datetime.combine(
            shift_date, datetime.strptime(row.shift_start, "%H:%M").time() # e.g. "06:00", "%H:%M"
        )
        end_dt = datetime.combine(
            shift_date, datetime.strptime(row.shift_end, "%H:%M").time()
        # 
        )
        # We hebben eerder start_dt en end_dt opgebouwd door de shiftdatum te combineren met de begin- en eindtijd.
        if row.shift_type == "night": # only shift in which start moment doesn't fall within the same day as the end moment of the shift
            end_dt += timedelta(days=1)

        intervals.setdefault(row.worker_id, []).append(
            (start_dt, end_dt, row.shift_type, shift_date) #  setdefault() zorgt dat iedere werknemer een lijst heeft; append() voegt daar telkens een shiftinterval aan toe.
            
            
         #Without .setdefault:  
        # if row.worker_id not in intervals:
        #     intervals[row.worker_id] = []
        
        # intervals[row.worker_id].append(
        #     (start_dt, end_dt, row.shift_type, shift_date)
        #)
        )

    return intervals # return dictionary


def _overlaps(sleep_start, sleep_end, shift_start, shift_end):
    return sleep_start < shift_end and sleep_end > shift_start


@pytest.fixture(scope="module")
def assignments_df(): # In dit geval vertelt de decorator aan pytest dat assignments() een fixture is.
    df = pd.read_csv(DATA_DIR / "historical_assignments.csv")
    df["date"] = pd.to_datetime(df["date"]) # convert date strings to pandas datetime
    return df


@pytest.fixture(scope="module")
def sleep_df():
    return pd.read_csv(DATA_DIR / "historical_sleep.csv")

#  test_ Pytest koppelt de namen van de argumenten aan de overeenkomstige fixtures.
# De twee fixtures zijn hier onafhankelijk. De volgorde waarin ze worden uitgevoerd is niet belangrijk voor de test, zolang beide klaar zijn voordat de testfunctie begint.
def test_no_sleep_episode_overlaps_any_shift(assignments_df, sleep_df):
    shift_intervals_dict = _load_shift_intervals(assignments_df) # {}, see intervals = {}, start_dt, end_dt, row.shift_type, shift_date
    sleep_episodes_df = sleep_df[sleep_df["no_main_sleep_episode"] == False] #sleep_df is loaded as dataframe above

    violations = [] # init list
    
    # SLEEPDATA in BUITENSTE LOOP: goes through the sleep start and end times
    for row in sleep_episodes_df.itertuples(index=False):
        sleep_start = datetime.fromisoformat(row.sleep_start) # convert to datetime object (instead of string)
        sleep_end = datetime.fromisoformat(row.sleep_end) # convert to datetime object (instead of sting)
        
        # SHIFTDATA in BINNENSTE LOOP (van 1 spec worker): goes through the shift start and end times
        # En het cruciale detail is dat de binnenste lus alle werkshifts van die werknemer doorloopt, niet alleen de shift waaraan de slaapepisode gekoppeld is.
        for shift_start, shift_end, shift_type, shift_date in shift_intervals_dict.get(row.worker_id, []):
            
            # row.worker_id komt uit de huidige rij van het slaap-DataFrame. 
            # Die waarde gebruik je als sleutel (key) om de juiste gegevens in de shiftdictionary op te zoeken.
            #         [
            # (datetime(2026, 10, 9, 6, 0), datetime(2026, 10, 9, 14, 0), "early", date(2026, 10, 9)),
            # (datetime(2026, 10, 10, 6, 0), datetime(2026, 10, 10, 14, 0), "early", date(2026, 10, 10))
            
            # Bij de _overlap zoek functie worden
            if _overlaps(sleep_start, sleep_end, shift_start, shift_end):
                violations.append({ # violations neemt 2 bronenn samen: de info uit sleep df en de info uit shiften
                    "worker_id": row.worker_id,
                    "sleep_date": row.sleep_date,
                    "linked_shift": row.linked_shift, # komt uit sleep_df
                    "sleep_start": row.sleep_start,
                    "sleep_end": row.sleep_end,
                    "overlapping_shift_type": shift_type, # komt uit shift_intervals_dict
                    "overlapping_shift_date": shift_date.isoformat(), #isoformat()
                })
        # Hier zijn er twee argumenten:
        #- row.worker_id: de sleutel die we zoeken, bijvoorbeeld "W001".
        #- []: de standaardwaarde die wordt teruggegeven als die sleutel niet bestaat.
    assert not violations, (
        f"\n{len(violations)} sleep episode(s) overlap with a scheduled shift.\n"
        f"First examples:\n"
        f"{pd.DataFrame(violations).head(10).to_string(index=False)}"
    )
