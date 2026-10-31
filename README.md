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
| Docker Compose (PostgreSQL + FastAPI) | Done — local setup tested |
| Automatic database initialization | Planned |
| Personalised roster evaluation | Next |
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
├── schemas/
│   └── hcss_schema.sql         # PostgreSQL schema
├── tests/                      # unit tests (pytest)
├── Dockerfile                  # FastAPI Docker image (Python 3.10)
├── compose.yaml                # PostgreSQL + FastAPI services
├── load_script.py              # loads the CSV files into PostgreSQL
├── requirements.txt
└── pytest.ini
```

## Installation and configuration

Choose either a local Python/PostgreSQL setup or Docker Compose. Both use the same database schema and CSV data.

Create `api/.env` from `api/.env.example` and supply your own database settings. Do not commit `api/.env` (it contains credentials).

For a **local API**, use the hostname and port of your PostgreSQL instance. For a **Docker Compose setup**, keep `DB_HOST=localhost` and set `DB_PORT=5433` in `api/.env` when running the data-loading script *from your computer*. Compose overrides these values for the API container, which connects to `db:5432`. The `DB_USER` and `DB_PASSWORD` values must match the database credentials; with the current Compose configuration, use `DB_USER=postgres`.

### Option A — Run with Docker Compose

**Requirements:** Docker Desktop (or Docker Engine with Docker Compose). Python 3.10 is also needed on your computer for the current manual CSV-loading step.

From the project root, start PostgreSQL and FastAPI:

```bash
docker compose --env-file api/.env up -d --build
```

Docker Compose starts two services: `db` (PostgreSQL 18, exposed on host port 5433) and `api` (FastAPI, exposed on host port 8000). Once the database has been populated, Swagger is available at <http://localhost:8000/docs>.

**Fresh installation:** automatic schema creation and CSV loading are **not yet implemented**. Starting Compose with a new volume creates the `shift_scheduling` database, but not its HCSS tables or records. Follow [Loading the data](#loading-the-data) below to create the schema and import the CSV files. Until then, endpoints that query those tables will not work.

**Existing local database volume:** the setup was tested using an existing Docker volume through a Git-ignored `compose.local.yaml` override. That file is specific to the developer's machine and is not needed for a fresh installation. If you already have a compatible volume and a local override, use:

```bash
docker compose --env-file api/.env -f compose.yaml -f compose.local.yaml up -d --build
```

Stop the services with `docker compose --env-file api/.env down` (include the two `-f` options above when using the local override). `down` does not delete named database volumes unless explicitly requested with `-v`.

### Option B — Run locally without Docker Compose

**Requirements:** Python 3.10 and a running PostgreSQL instance.

From the project root, install the Python dependencies:

```bash
pip install -r requirements.txt
```

Create a PostgreSQL database named `shift_scheduling` (or configure another name in `api/.env`), then create the tables and load the data as described below. Start FastAPI using the instructions in [Running the API](#running-the-api).

## Loading the data

The CSV files in `data/` are already generated. First create the tables in your empty `shift_scheduling` database using `schemas/hcss_schema.sql`.

For example, with PostgreSQL's `psql` client installed on your computer:

```bash
# Docker Compose database (host port 5433)
psql -h localhost -p 5433 -U postgres -d shift_scheduling -f schemas/hcss_schema.sql
```

For a locally installed PostgreSQL server, use its actual host and port instead.

Then load the CSV files from the project root (requires the Python dependencies and valid settings in `api/.env`):

```bash
python load_script.py
```

The script reads the database settings from `api/.env`, loads the four CSV files with PostgreSQL `COPY`, and runs everything in one transaction. It stops without changes if any target table already contains data.

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
