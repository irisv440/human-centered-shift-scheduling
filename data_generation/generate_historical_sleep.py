"""
generate_historical_sleep.py

Generate one sleep observation per worker per calendar date, 
with a main sleep episode when the sampled duration is positive,
using:
- each worker's latent sleep profile,
- worker-specific night-to-night variability,
- the historical roster,
- MVP shift effects agreed for the project.


Sleep/shift linkage
-------------------
Early (06:00-14:00):
    Sleep before the current Early shift.
    Duration effect: worker-specific (mean -1.5 h, SD 0.4 h).
    Timing: anchored to the shift start.

Late (14:00-22:00):
    Sleep after the previous Late shift.
    Duration effect: +0.2 h.
    Timing: anchored to the previous shift end.

Night (22:00-06:00):
    Sleep after the previous Night shift.
    Duration effect: worker-specific (mean -1.4 h, SD 0.5 h).
    Timing: anchored to the previous shift end.

Off:
    Sleep not linked to an Early, Late or Night shift.
    Duration effect: +0.7 h.
    Timing: based on the worker's latent sleep midpoint.

The column `sleep_date` is the current roster date used to anchor
the sleep observation.

Duration guardrail
------------------
- 0 < duration <= 12 h: keep it
- duration > 12 h: resample only the duration noise
- duration <= 0 h: record no main sleep episode
  (sleep timing and duration fields are NaN)


linked_shift: the shift category whose effect parameters were applied when generating this sleep observation.

Meaning linked_shift_date:
the date of the actual shift associated with that applied effect, for 'off' days this is None.
"""

from pathlib import Path
from datetime import datetime, timedelta
import numpy as np
import pandas as pd


SEED = 43

# Fixed duration effects; early and night effects are worker-specific.
SHIFT_EFFECTS = {
    "late": {"duration": 0.2},
    "off":  {"duration": 0.7},
}


def clock_to_hours(clock_string):
    """Convert HH:MM to decimal hours after midnight."""
    hours, minutes = map(int, clock_string.split(":"))
    return hours + minutes / 60.0



def linked_shift_for_sleep(current_shift, previous_shift):
    """
    Determine which scheduled shift is linked to the main sleep episode
    stored for the current `sleep_date`.

    IMPORTANT DATE SEMANTICS
    ------------------------
    `sleep_date` is based on the CURRENT roster date in the loop.

    Early:
        If the current roster day contains an Early shift, the sleep episode
        stored on this same date represents the main sleep BEFORE that shift.

        Example:
            shift_date = 2026-09-10, Early
            sleep_date = 2026-09-10
            linked_shift = "early"

    Late:
        A Late shift affects the main sleep AFTER the shift.
        Therefore a Late shift on the previous roster day produces a
        Late-linked sleep episode on the current date.

        Example:
            shift_date = 2026-09-10, Late
            sleep_date = 2026-09-11
            linked_shift = "late"

    Night:
        A Night shift also affects the main sleep AFTER the shift.
        Therefore a Night shift starting on the previous roster day produces
        a Night-linked sleep episode on the current date.

        Example:
            shift_date = 2026-09-10, Night
            sleep_date = 2026-09-11
            linked_shift = "night"

    Off:
        If none of the above rules applies, the sleep episode is treated
        as Off/baseline sleep.

    Therefore:
        sleep_date == linked shift_date          for Early
        sleep_date == linked shift_date + 1 day  for Late and Night

    Do NOT assume that sleep_date and shift_date refer to the same
    calendar date when joining sleep and roster data.
    
    Priority:
    1. If today's shift is Early, the preceding sleep is Early-linked.
    2. Otherwise, if yesterday's shift was Night, this is post-Night sleep.
    3. Otherwise, if yesterday's shift was Late, this is post-Late sleep.
    4. Otherwise, treat it as Off sleep (other rules not applicable).
    """

    if current_shift == "early":
        return "early"
    if previous_shift == "night":
        return "night"
    if previous_shift == "late":
        return "late"
    return "off"


def sample_duration(rng, latent_duration, variability, shift_effect):
    """
    Sample sleep duration using worker-specific night-to-night variability.
    
    duration = latent_duration + shift_effect + N(0, variability)
    
    Resample noise if duration > 12 h.
    Return (None, noise) if duration <= 0 h.
    Otherwise return (duration, noise).
    """
    while True:
        noise = rng.normal(0.0, variability)
        duration = latent_duration + shift_effect + noise

        if duration > 12.0:
            continue

        if duration <= 0.0:
            return None, noise

        return duration, noise # if succeeded, stops


def main():
    """Generate historical sleep observations from worker profiles and shift assignments."""
    
    #data_dir = Path("data")
    data_dir = Path(__file__).resolve().parent.parent / "data"
    profiles_path = data_dir / "latent_sleep_profiles.csv"
    assignments_path = data_dir / "historical_assignments.csv"

    if not profiles_path.exists():
        raise FileNotFoundError(
            f"{profiles_path} not found. Run generate_workers.py first."
        )

    if not assignments_path.exists():
        raise FileNotFoundError(
            f"{assignments_path} not found. "
            "Run generate_historical_roster.py first."
        )

    rng = np.random.default_rng(SEED)

    profiles = pd.read_csv(profiles_path) # the latent sleep profiles (no dates)
    assignments = pd.read_csv(assignments_path) # the shifts with shift dates

    assignments["date"] = pd.to_datetime(assignments["date"])
    assignments = assignments.sort_values(["worker_id", "date"])

    profile_lookup = profiles.set_index("worker_id") #profiles: latent sleep profile

    rows = []
    truth_rows = []

    for worker_id, worker_roster in assignments.groupby("worker_id"): #(
    #) Een belangrijk detail: groupby() levert hier telkens een tuple van twee elementen op: (worker_id, worker_roster). Python pakt die rechtstreeks uit in de twee variabelen van de for-lus.
        profile = profile_lookup.loc[worker_id] # Get the entire sleep profile row for this worker

        latent_duration = float(profile["latent_sleep_duration_hours"]) # # Get one value from that profile and convert it to float
        latent_midpoint = clock_to_hours(profile["latent_midpoint"])
        duration_sd = float(profile["latent_duration_variability_hours"])
        midpoint_sd = float(profile["latent_midpoint_variability_hours"])
        early_duration_effect = float(profile["latent_early_duration_effect_hours"])
        night_duration_effect = float(profile["latent_night_duration_effect_hours"])

        worker_roster = worker_roster.sort_values("date").reset_index(drop=True)
        
        
        # `sleep_date` is the current roster date used to anchor this generated
        # sleep observation.
        #
        # For Early-linked sleep, this is also the Early shift's date.
        # For Late- or Night-linked sleep, the affecting shift occurred on the
        # PREVIOUS roster date.
        
        # Itererateover the days
        for i, assignment in worker_roster.iterrows(): #worker_roster = 1 
            sleep_date = assignment["date"]
            current_shift = assignment["shift_type"] # zelfde rij, voor een eerdere rij moet je met .loc[i - x, "col_name"] werken

            previous_shift = (
                worker_roster.loc[i - 1, "shift_type"]
                if i > 0
                else None
            )

            # Determine which shift influenced the sleep episode
            linked_shift = linked_shift_for_sleep(
                current_shift=current_shift,
                previous_shift=previous_shift,
            )
            
            # Store the ACTUAL DATE of the shift that influenced the sleep episode.
            #
            # Early:
            #   sleep occurs before the Early shift on the same calendar date.
            #
            # Late/Night:
            #   sleep occurs after a shift that started on the previous calendar date. !!! hence linked shift is een dag vroeger
            #
            # Off:
            #   no specific work shift is linked to the sleep episode.
            if linked_shift == "early":
                linked_shift_date = sleep_date
            
            elif linked_shift in ("late", "night"):
                linked_shift_date = sleep_date - pd.Timedelta(days=1)
            
            else: # off
                linked_shift_date = None

            if linked_shift == "early":
                duration_effect = early_duration_effect
            elif linked_shift == "night":
                duration_effect = night_duration_effect
            else:
                duration_effect = SHIFT_EFFECTS[linked_shift]["duration"]

            duration, duration_noise = sample_duration(
                rng=rng,
                latent_duration=latent_duration,
                variability=duration_sd,
                shift_effect=duration_effect,
            )

            # If no main sleep episode was generated, all episode fields stay blank.
            if duration is None:
                rows.append({
                    "worker_id": worker_id,
                    "sleep_date": sleep_date.date().isoformat(),
                    "linked_shift": linked_shift,
                    "linked_shift_date": (linked_shift_date.date().isoformat() if linked_shift_date is not None
                                          else None),
                    "sleep_start": np.nan,
                    "sleep_end": np.nan,
                    "sleep_duration_hours": np.nan,
                    "sleep_midpoint": np.nan,
                    "no_main_sleep_episode": True,
                })
                
                truth_rows.append({
                    "worker_id": worker_id,
                    "sleep_date": sleep_date.date().isoformat(),
                    "duration_shift_effect_hours": duration_effect,
                    "duration_noise_hours": round(duration_noise, 4),    
                })
                
                continue
            
            
            if linked_shift == "early":
                shift_start_dt = pd.to_datetime(f"{assignment['date'].date()} {assignment['shift_start']}")
                early_timing_noise = rng.normal(0.0, 47.0)

                
                sleep_end_dt = shift_start_dt - timedelta(minutes=55) + timedelta(minutes=early_timing_noise)
                sleep_end_dt = min(sleep_end_dt, shift_start_dt)
                sleep_start_dt = sleep_end_dt - timedelta(hours=duration)
                midpoint_dt = sleep_start_dt + timedelta(hours=duration / 2.0)
            
                
            elif linked_shift == "late":
                previous_assignment = worker_roster.loc[i - 1]
                shift_end_dt = pd.to_datetime(f"{previous_assignment['date'].date()} {previous_assignment['shift_end']}")
                earliest_sleep_start = shift_end_dt + timedelta(minutes=55)
                target_sleep_start = sleep_date.normalize() + timedelta(hours=1, minutes=19)
                late_timing_noise = rng.normal(0.0, 43.0)
                
                sleep_start_dt = target_sleep_start + timedelta(minutes=late_timing_noise)
                sleep_start_dt = max(sleep_start_dt, earliest_sleep_start)
                sleep_end_dt = sleep_start_dt + timedelta(hours=duration)
                midpoint_dt = sleep_start_dt + timedelta(hours=duration / 2.0)
            
            elif linked_shift == "night":
                # Get the actual Night assignment from the previous roster day
                previous_assignment = worker_roster.loc[i - 1]
            
                # Get the actual end time of that Night shift
                shift_end_dt = pd.to_datetime(f"{previous_assignment['date'].date()} {previous_assignment['shift_end']}")
            
                # Night shifts cross midnight, so the end belongs to the next calendar day
                shift_end_dt = shift_end_dt + timedelta(days=1)
            
                # Earliest possible sleep start: 55 minutes after the Night shift ends
                earliest_sleep_start = shift_end_dt + timedelta(minutes=55)
            
                # Add individual/night-to-night variation around that timing
                night_timing_noise = rng.normal(0.0, 47.0)
                #timing_noise_minutes = night_timing_noise
                
                sleep_start_dt = earliest_sleep_start + timedelta(minutes=night_timing_noise)
            
                # Never allow sleep to start earlier than 55 minutes after the shift
                sleep_start_dt = max(sleep_start_dt, earliest_sleep_start)
            
                # Derive sleep end and midpoint from sleep start and generated duration
                sleep_end_dt = sleep_start_dt + timedelta(hours=duration)
                midpoint_dt = sleep_start_dt + timedelta(hours=duration / 2.0)
                
            else:  # off
                # Generate sleep timing around the worker's natural sleep midpoint
                midpoint_noise = rng.normal(0.0, midpoint_sd)
                #timing_noise_minutes = midpoint_noise * 60.0  # Convert hours to minutes
                midpoint_hours = latent_midpoint + midpoint_noise
            
                # Anchor the midpoint to the current sleep date
                midpoint_dt = sleep_date.normalize() + timedelta(hours=midpoint_hours)
            
                # Derive sleep start and end from midpoint and generated duration
                sleep_start_dt = midpoint_dt - timedelta(hours=duration / 2.0)
                sleep_end_dt = midpoint_dt + timedelta(hours=duration / 2.0)


            rows.append({
                "worker_id": worker_id,
                "sleep_date": sleep_date.date().isoformat(),
                "linked_shift": linked_shift,
                "linked_shift_date": (linked_shift_date.date().isoformat() if linked_shift_date is not None else None),
                "sleep_start": sleep_start_dt.isoformat(),
                "sleep_end": sleep_end_dt.isoformat(),
                "sleep_duration_hours": round(duration, 2),
                "sleep_midpoint": midpoint_dt.isoformat(),
                "no_main_sleep_episode": False,
            })
            
            truth_rows.append({
                "worker_id": worker_id,
                "sleep_date": sleep_date.date().isoformat(),
                "duration_shift_effect_hours": duration_effect,
                "duration_noise_hours": round(duration_noise, 4),    
            })

    sleep = pd.DataFrame(rows)
    sleep_truth_df = pd.DataFrame(truth_rows)

    output_path = data_dir / "historical_sleep.csv"
    output_path_truth = data_dir / "historical_sleep_ground_truth.csv"
    
    sleep.to_csv(output_path, index=False)
    sleep_truth_df.to_csv(output_path_truth, index=False)

    print("Historical sleep generated")
    print("--------------------------")
    print("Rows:", len(sleep))
    print("Workers:", sleep["worker_id"].nunique())
    print("Date range:", sleep["sleep_date"].min(), "to", sleep["sleep_date"].max())

    print("\nLinked shift counts:")
    print(sleep["linked_shift"].value_counts())

    print("\nSleep duration descriptives:")
    print(sleep["sleep_duration_hours"].describe())

    print("\nNo-main-sleep episodes:")
    print(int(sleep["no_main_sleep_episode"].sum()))

    print("\nMean generated duration by linked shift:")
    print(
        sleep.groupby("linked_shift")["sleep_duration_hours"]
        .mean()
        .round(2)
    )

    print("\nOutput:", output_path)


if __name__ == "__main__":
    main()
