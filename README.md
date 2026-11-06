# Human-Centered Shift Scheduling (HCSS)

HCSS analyses how shift work affects sleep, per worker, as a basis for evaluating and later adjusting rosters with the individual worker in mind.

The project runs on a fully synthetic workforce. It is a portfolio project covering the full path from data generation to a tested API.

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
| Personalised roster evaluation | In progress — interim version in `evaluator/` and `validation/` |
| Constraint-based roster optimisation | Planned |



## Project structure

```text
human-centered-shift-scheduling/
├── .github/
│   └── workflows/
│       └── tests.yml           # GitHub Actions CI
├── api/
│   ├── main.py                 # FastAPI app: queries and endpoints
│   ├── db.py                   # shared database connection
│   ├── .env.example            # database settings template
│   └── sleep_metrics/
│       ├── calculate_sri.py    # Sleep Regularity Index
│       ├── summarize_sleep.py  # sleep statistics per linked shift
│       └── shift_analysis.py   # shift blocks, short sleep, difference vs Off
├── data/                       # generated CSV files (see "Data and reproducibility")
├── data_generation/
│   ├── generate_workers.py
│   ├── generate_historical_roster.py
│   ├── generate_historical_sleep.py
│   └── tests/
│       └── test_sleep_shift_overlap.py   # no sleep episode overlaps any scheduled shift
├── evaluator/                  # personalised roster evaluation (in progress)
├── schemas/
│   └── hcss_schema.sql         # PostgreSQL schema
├── tests/                      # unit tests (pytest)
├── validation/                 # checks of the evaluator against the generator's latent truth
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

The unit tests use small hand-made records with known answers and need no database. They cover the SRI input and calculation, the sleep summaries per shift, and the shift-block analysis, including the edge cases for nights without a main sleep episode.

`pytest -v` also runs a data test on the generated CSV files, which checks that no sleep episode overlaps any of the worker's scheduled shifts.

## License

MIT, see [LICENSE](LICENSE).
