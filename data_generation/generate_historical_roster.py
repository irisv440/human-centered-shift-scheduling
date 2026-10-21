from pathlib import Path
from datetime import date, timedelta
import numpy as np
import pandas as pd

SEED = 42
START_DATE = date(2026, 5, 25)
N_DAYS = 84

TEAM_SIZES = {"A": 8, "B": 8, "C": 7, "D": 7}
TEAM_OFFSETS = {"A": 0, "B": 7, "C": 14, "D": 21}

SHIFT_TIMES = {
    "early": ("06:00", "14:00"),
    "late": ("14:00", "22:00"),
    "night": ("22:00", "06:00"),
    "off": (None, None),
}

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

def assign_teams(workers, rng):
    team_members = {team: [] for team in TEAM_SIZES}

    supervisors = workers.loc[workers["role"] == "supervisor", "worker_id"].to_numpy()
    seniors = workers.loc[workers["role"] == "senior_operator", "worker_id"].to_numpy()
    operators = workers.loc[workers["role"] == "operator", "worker_id"].to_numpy()

    rng.shuffle(supervisors)
    rng.shuffle(seniors)
    rng.shuffle(operators)

    for team, worker_id in zip(TEAM_SIZES, supervisors):
        team_members[team].append(worker_id)

    pos = 0
    for team in TEAM_SIZES:
        team_members[team].extend(seniors[pos:pos + 2])
        pos += 2

    pos = 0
    for team, target_size in TEAM_SIZES.items():
        places_left = target_size - len(team_members[team])
        team_members[team].extend(operators[pos:pos + places_left])
        pos += places_left

    worker_to_team = {
        worker_id: team
        for team, members in team_members.items()
        for worker_id in members
    }

    result = workers.copy()
    result["team"] = result["worker_id"].map(worker_to_team)
    return result.sort_values("worker_id").reset_index(drop=True)

def main():
    rng = np.random.default_rng(SEED)
    data_dir = Path("data")
    workers = pd.read_csv(data_dir / "workers.csv")
    workers_with_teams = assign_teams(workers, rng)

    rows = []
    for day_index in range(N_DAYS):
        current_date = START_DATE + timedelta(days=day_index)

        for team, offset in TEAM_OFFSETS.items():
            cycle_day = (day_index + offset) % 28
            shift_type = shift_for_cycle_day(cycle_day)
            start_time, end_time = SHIFT_TIMES[shift_type]

            members = workers_with_teams.loc[
                workers_with_teams["team"] == team, "worker_id"
            ]

            for worker_id in members:
                rows.append({
                    "date": current_date.isoformat(),
                    "worker_id": worker_id,
                    "team": team,
                    "shift_type": shift_type,
                    "shift_start": start_time,
                    "shift_end": end_time,
                    "cycle_day": cycle_day + 1,
                })

    assignments = pd.DataFrame(rows)
    workers_with_teams.to_csv(data_dir / "workers_with_teams.csv", index=False)
    assignments.to_csv(data_dir / "historical_assignments.csv", index=False)

    print(pd.crosstab(workers_with_teams["team"], workers_with_teams["role"]))
    print("\nRows:", len(assignments))
    print("Date range:", assignments["date"].min(), "to", assignments["date"].max())
    print("\nShift counts:")
    print(assignments["shift_type"].value_counts())

if __name__ == "__main__":
    main()
