# Human-Centered Shift Scheduling (HCSS)

HCSS analyses how shift work affects sleep, per worker, and uses those estimates to evaluate rosters and to optimise them with the individual worker in mind.

The project runs on a fully synthetic workforce. It is a portfolio project covering the full path from data generation and a tested API to a personalised sleep model and an optimised roster.

## Status

| Component | Status |
|---|---|
| Synthetic data generation (workers, roster, sleep) | Done |
| PostgreSQL database | Done |
| Load script | Done |
| FastAPI with sleep and shift analyses | Done |
| Unit tests for the analysis functions | Done |
| GitHub Actions CI (pytest) | Done |
| Docker Compose (PostgreSQL + FastAPI) | Done — tested locally |
| Automatic database initialization | Done — tested locally |
| Personalised roster evaluation | Done (v1) — `evaluator/`, checked in `validation/` |
| Constraint-based roster optimisation | Done (v1) — CPMpy model in `scheduler/` with labour rules, off requests and a tuned objective; candidate roster compared with the historical roster (see [Roster optimisation](#roster-optimisation)) |



## Project structure

```text
human-centered-shift-scheduling/
├── .github/
│   └── workflows/
│       └── tests.yml           # GitHub Actions CI
├── api/
│   ├── main.py                 # FastAPI app: queries and endpoints
│   ├── db.py                   # shared database connection
│   ├── roster_table.py         # text table of the historical and candidate roster, for GET /roster-comparison/table
│   ├── .env.example            # database settings template
│   └── sleep_metrics/
│       ├── calculate_sri.py    # Sleep Regularity Index
│       ├── summarize_sleep.py  # sleep statistics per linked shift
│       └── shift_analysis.py   # shift blocks, short sleep, difference vs Off
├── data/                       # generated CSV files (see "Data and reproducibility") and roster_comparison.json
├── data_generation/
│   ├── generate_workers.py
│   ├── generate_historical_roster.py
│   ├── generate_historical_sleep.py
│   └── tests/
│       └── test_sleep_shift_overlap.py   # no sleep episode overlaps any scheduled shift
├── evaluator/                  # personalised roster evaluation
│   ├── estimate.py             # per-worker sleep estimates per linked shift (plain averages, no pooling)
│   ├── estimate_lmm.py         # per-worker sleep estimates per linked shift (linear mixed model)
│   ├── linkage.py              # links each night's sleep to a shift
│   ├── objective.py            # objective of a roster (sleep loss + penalty on short nights)
│   ├── roster_score.py         # scores one worker's roster
│   ├── score_all_workers.py    # scores a full roster, per worker
│   ├── short_sleep.py          # probability of a short night, given a main sleep episode
│   └── validity.py             # flags patterns that never occur in the historical roster
├── schemas/
│   └── hcss_schema.sql         # PostgreSQL schema
├── scheduler/                  # CPMpy roster model
│   ├── requirements_config.py  # teams, shifts, labour rules and objective settings
│   ├── cost_table.py           # per-worker cost tables for the solver (whole numbers)
│   └── model.py                # CPMpy model: constraints, linkage and objective
├── tests/                      # unit tests (pytest)
├── validation/                 # checks of the evaluator and the solver; scripts, not unit tests
│   ├── compare_rosters.py      # historical roster versus the candidate roster of the model
│   ├── export_roster_comparison.py  # writes data/roster_comparison.json for GET /roster-comparison
│   ├── tune_parameters.py      # sensitivity analysis of the objective threshold and weight
│   ├── validate_linkage.py     # linkage of the evaluator versus the generator's linked shifts
│   └── validate_recovery.py    # estimated versus true (latent) sleep parameters
├── Dockerfile                  # Python image for API and CSV seeding
├── compose.yaml                # PostgreSQL, seed and API services
├── load_script.py              # loads CSV data; skips already populated databases
├── requirements.txt
└── pytest.ini
```

## Installation and configuration

Choose either a local Python/PostgreSQL setup or Docker Compose. Both use the same database schema and CSV data.

Create `api/.env` from `api/.env.example` and supply your database settings. Do not commit `api/.env`, as it contains credentials.

For Docker Compose, use `DB_NAME=shift_scheduling` and `DB_USER=postgres`, with a password of your choice. Compose configures the API and seed containers to connect to PostgreSQL at `db:5432`.

For a local Python setup, configure `DB_HOST` and `DB_PORT` to match the PostgreSQL instance you want to connect to.

### Option A — Run with Docker Compose

**Requirements:** Docker Desktop (or Docker Engine with Docker Compose). No separate local Python or PostgreSQL installation is required.

From the project root, run:

```bash
docker compose --env-file api/.env up -d --build
```

Docker Compose manages three services:

- `db`: PostgreSQL 18, exposed on host port 5433.
- `seed`: loads the CSV data into PostgreSQL and exits after successful completion.
- `api`: FastAPI, exposed on host port 8000.

**Fresh installation:** On first startup with an empty PostgreSQL data volume, the database is created and `schemas/hcss_schema.sql` automatically creates the four HCSS tables. The `seed` service then imports the CSV files from `data/`. FastAPI starts only after the import completes successfully.

**Subsequent startups:** When all four tables already contain data, the load script skips the import without raising an error. Existing database data are preserved.

Once the API is running, Swagger is available at http://localhost:8000/docs.

**Existing developer database volume:** A Git-ignored `compose.local.yaml` can be used to reference an existing PostgreSQL Docker volume:

```bash
docker compose --env-file api/.env -f compose.yaml -f compose.local.yaml up -d --build
```

Stop the services with `docker compose --env-file api/.env down` (include the additional `-f` options when using the local override). Named database volumes are preserved unless explicitly removed, for example using `down -v`.

### Option B — Run locally without Docker Compose

**Requirements:** Python 3.10 and a running PostgreSQL instance.

From the project root, install the Python dependencies:

```bash
pip install -r requirements.txt
```

Create a PostgreSQL database named `shift_scheduling` (or configure another name in `api/.env`), then create the tables and load the data as described below. Start FastAPI using the instructions in [Running the API](#running-the-api).

## Loading the data

**With Docker Compose, schema creation and CSV loading are automatic.** The following manual instructions are intended for a local PostgreSQL setup or for development and troubleshooting.

The CSV files in `data/` are already generated. First create the HCSS tables in an empty PostgreSQL database using `schemas/hcss_schema.sql`.

For example, with PostgreSQL's `psql` client installed:

```bash
psql -h localhost -p 5432 -U postgres -d shift_scheduling -f schemas/hcss_schema.sql
```

Adjust the hostname, port, username and database name to match your local PostgreSQL configuration.

Then load the CSV files from the project root:

```bash
python load_script.py
```

The script uses the database settings from `api/.env` and imports all four CSV files using PostgreSQL `COPY`, within a single transaction.

Before importing, the script checks the four target tables:

- **All tables empty:** perform the import.
- **All tables populated:** skip the import successfully.
- **Only some tables populated:** abort the import with an error.

This check detects empty versus populated tables; it does not validate whether every expected record is present.

The script loads the files in this order, because the other tables refer to `workers`:

| CSV file | Table | Note |
|---|---|---|
| `workers_with_teams.csv` | `workers` | |
| `worker_profiles.csv` | `worker_profiles` | |
| `historical_assignments.csv` | `shift_assignments` | The CSV column `date` maps to `shift_date`.|
| `historical_sleep.csv` | `historical_sleep` | empty values are `NULL` |

Not loaded into the database:
- `workers.csv`: intermediate output of the worker generator (without teams).
- `latent_sleep_profiles.csv` and `historical_sleep_ground_truth.csv`: the latent "truth" of the generator. These are kept for validation only (see "Data and reproducibility").


## Running the API

If using Docker Compose, the API is already started by Compose. For a local Python setup, run the following from the `api/` folder:

```
uvicorn main:app --reload
```

Interactive documentation is then available at `http://127.0.0.1:8000/docs`.

| Endpoint | Returns |
|---|---|
| `GET /workers`, `GET /workers/{worker_id}` | worker data (role, contract hours, team) |
| `GET /sleep/{worker_id}` | all sleep records, ordered by date |
| `GET /roster/{worker_id}` | all shifts, ordered by date |
| `GET /sleep-summary/{worker_id}` | overall sleep duration statistics |
| `GET /sleep-summary-by-shift/{worker_id}` | sleep duration statistics per linked shift (early, late, night, off) |
| `GET /shift-sleep/{worker_id}` | shifts joined with the sleep they affect |
| `GET /shift-sleep-analysis/{worker_id}` | sleep per day in a shift block, short sleep per shift type, and difference vs Off |
| `GET /sleep-regularity/{worker_id}` | Sleep Regularity Index (overall and per pair of consecutive days) |
| `GET /roster-comparison` | historical roster (cycle 1) versus the candidate roster of the solver: both rosters, scores per worker, the difference, and how the result was computed (precomputed, see below) |
| `GET /roster-comparison/table` | the same two rosters as a plain-text table: one letter per day, the historical roster above the candidate roster, and `^` under each day the solver changed |

**`/roster-comparison` (version 1).** The endpoint serves a precomputed comparison of the historical roster and the candidate roster of the solver. Sending your own data is not implemented yet: the comparison is computed once by `python -m validation.export_roster_comparison` (solving takes one to two minutes) and saved as `data/roster_comparison.json`. The file records when and with which settings it was computed (solver status and time, threshold, weight, request penalty, machine). After a change in `scheduler/requirements_config.py`, run the script again.

**`/roster-comparison/table`.** The same file, shown as a text table that can be opened directly in a browser (http://localhost:8000/roster-comparison/table). E = early, L = late, N = night, . = off. It shows at a glance what the solver changed: days off stay the same, and only shifts on working days are moved.

**Planned for version 2.** Users can send their own roster in a request, and get it scored and compared with the historical roster.

## Modelling choices

**Linking sleep to shifts.** Each night has a `sleep_date` and a `linked_shift`: the shift that most affects that sleep. Sleep before an early shift is linked to that shift on the same date. Sleep after a late or night shift is linked to the shift of the previous day. Otherwise the night counts as Off.

**Nights without a main sleep episode** (`no_main_sleep_episode = True`) are treated as observed nights, not as missing data:
- they are excluded from mean, minimum and maximum duration, and counted separately;
- they count as short sleep;
- in the SRI, that day counts as awake. With real wearable data, a blank night could also mean the device was not worn; this choice would then lower the SRI incorrectly.

**Short sleep** is defined as a main sleep episode shorter than 6 hours (`SHORT_SLEEP_THRESHOLD_HOURS`). Observed nights without a main sleep episode are also counted as short sleep, but reported separately.

**Sleep Regularity Index (SRI).** Sleep and wake states are compared minute by minute, 24 hours apart. The timeline starts at 00:00 on the day before the first `sleep_date` (a context day), so that sleep starting the evening before the first analysis day is included. The SRI needs at least two days; with fewer, the endpoint returns a 422.

**Difference vs Off** (`duration_diff_vs_off`). Per worker and shift type, this is the computed difference between mean sleep duration after that shift type and mean sleep duration on Off nights. It is reported together with the number of nights behind each mean. No standard error is reported, because consecutive nights of one worker are not independent.

**Shift blocks** (`day_in_shift_block`). Consecutive shifts of the same type form a block, numbered day 1, 2, 3 and so on. Known limitation: blocks at the start or end of the data window may be truncated, so their day numbers can be too low.

## Roster optimisation

**From sleep data to a roster.** A linear mixed model (`evaluator/estimate_lmm.py`) estimates, per worker, how long they sleep after each linked shift type, and how much that varies from night to night. From these estimates, `scheduler/cost_table.py` builds two tables per worker and shift type:

- the difference in sleep versus the worker's own Off nights, in minutes;
- the probability of a short night (under 6 hours), times 1000.

**Objective.** The objective adds the total sleep loss of all workers (in minutes) to a penalty for each worker whose expected number of short nights exceeds a threshold. This part is the same in the evaluator (`evaluator/objective.py`) and in the solver (`make_objective` in `scheduler/model.py`). The solver adds one more term: a penalty for each violated off request (see Off requests), which the evaluator does not score. This is the difference between the two: the evaluator measures what a roster does to sleep, the solver plans a roster and also weighs the workers' requests. The threshold and weight are set in `scheduler/requirements_config.py` (`objective_threshold_thousandths = 10000`, i.e. 10 expected short nights per worker per cycle; `objective_weight = 36`). A sensitivity analysis (`validation/tune_parameters.py`: thresholds 7.5, 10 and 12.5 × weights 18, 36 and 72) showed that the threshold matters and the weight hardly does. A threshold of 12.5 lowers total sleep loss slightly, but raises the number of workers above 10 expected short nights from 1 to 8, so the threshold stays at 10. The solver needs whole numbers, so its sleep-related objective is the evaluator's objective multiplied by 100 (up to rounding per table cell).

**Constraints.** Rest of at least 11 hours between shifts, at most 7 consecutive working days, 2 days off after 7 working days, at most 168 hours per 28-day cycle, staffing per team and role, and consistency between a worker's shift and assigned team.

**Off requests.** Workers can ask not to work a given shift type (-1/-2/-3) or not to work at all (-4) on a given day (`requests` in `scheduler/requirements_config.py`). Requests are soft: each violated request adds a penalty to the objective (`request_penalty_minutes`). Shift-type requests are granted by moving the worker to another team. Day-off requests on a working day of the home team cannot be granted: total demand (630 shifts per cycle) equals total capacity (30 workers × 21 shifts under the 168-hour cap), so there is no one to fill in.

**Running.** From the project root:

```
python -m scheduler.model
python -m validation.compare_rosters
python -m validation.export_roster_comparison
```

`scheduler.model` solves the model and prints the candidate roster and its objective. `validation.compare_rosters` scores the historical roster (first 28-day cycle) and the candidate roster on the same route, checks the candidate against the historical patterns, and prints both objectives. `validation.export_roster_comparison` writes the same comparison to `data/roster_comparison.json`, which `GET /roster-comparison` serves. Solving takes about one to two minutes.

**First result.** The candidate roster has a 28.6 % lower objective than the historical roster (51 534 versus 72 222). About two thirds of that gain comes from the penalty: the solver spreads the expected short nights more evenly across workers, while total sleep loss drops by 13 %. 18 of the 55 off requests are violated; 9 of these are day-off requests that cannot be granted (see Off requests). The solver's own objective is higher (52 602) because it also includes the penalty for violated requests, which the evaluator does not score.

**Uneven shift-type mix.** The solver specialises. Every shift type has to be covered, so the solver gives night shifts to the workers for whom nights cost the least sleep compared with other workers, and does the same for early shifts. Some workers get a single shift type for the whole cycle (for example W012 only night shifts, W002 only early shifts; see `GET /roster-comparison/table`). A fair spread of shift types across workers is not part of the objective in version 1.

**Known limitation.** The historical roster follows a single fixed pattern: every work block lasts exactly 7 days, and every change of shift type goes through days off. The candidate roster breaks that pattern for 17 of the 30 workers (shorter blocks, and changes such as late to night without a day off). For those patterns the score is an extrapolation: the sleep model has never seen them. Planned for v2: a second run restricted to the historical transitions, so that every change of shift type goes through a day off (a switch in `scheduler/requirements_config.py`), for comparison with the unrestricted run. If most of the gain remains, it comes from which worker gets which shift, not from new transitions such as early to late without a day off. Block lengths stay unrestricted, so shorter blocks remain an extrapolation. Forward rotation (early → late → night) is generally recommended in the shift-work literature, so the restricted run is a comparison, not a correction.

## Data and reproducibility

All data is synthetic: 30 workers in 4 teams on a 28-day rotating early/late/night/off cycle, with 84 days of history.

The generators run in this order, from the project root:

```
python data_generation/generate_workers.py
python data_generation/generate_historical_roster.py
python data_generation/generate_historical_sleep.py
```

Reproducibility. The generators use fixed random seeds (SEED = 42 for worker and roster generation; SEED = 43 for sleep generation) to support reproducibility. The generated data have been checked for consistency with the existing dataset (the CSV files in data/) and PostgreSQL records. 

**Latent versus observable.** The generator draws each night from latent worker parameters (sleep need, variability, individual shift effects). The API only uses observable data: what a sleep tracker and a roster would provide. The latent values are stored separately (`latent_sleep_profiles.csv`, `historical_sleep_ground_truth.csv`) so that results can later be validated against the truth, without the analysis ever seeing it.

Note: in the generator, Off nights have their own effect on sleep duration. The difference vs Off is therefore a relative measure, not the full latent shift effect.

## Tests

From the project root:

```
pytest -v
```

The unit tests use small hand-made records with known answers and need no database. They cover the SRI input and calculation, the sleep summaries per shift, and the shift-block analysis, including the edge cases for nights without a main sleep episode. They also cover the evaluator: the per-worker estimates (including recovery of known parameters from simulated data for the mixed model), the linkage of sleep to shifts, the probability of a short night, the roster score and the validity check.

`pytest -v` also runs a data test on the generated CSV files, which checks that no sleep episode overlaps any of the worker's scheduled shifts.

## License

MIT, see [LICENSE](LICENSE).
