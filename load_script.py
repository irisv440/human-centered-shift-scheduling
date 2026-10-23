# -*- coding: utf-8 -*-
"""
Created on Thu Oct 22 12:02:57 2026

@author: irisv
"""


from pathlib import Path

from psycopg2 import sql
from api.db import get_connection


# Paths relative to this script
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"




def load_csv(cursor, csv_path, table_name, columns):
    """
    Load a CSV file into a PostgreSQL table.

    Uses PostgreSQL COPY to import its contents.
    """
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    
    copy_query = sql.SQL(
        "COPY {} ({}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE)"
        ).format(
            sql.Identifier(table_name), # for SQL instructions on tables and column names
            sql.SQL(",").join(
                sql.Identifier(column) for column in columns
                )
            )
    
    with open(csv_path, "r", encoding="utf-8-sig") as file:
        cursor.copy_expert(copy_query.as_string(cursor), file)

    print(f"Loaded {csv_path.name} into {table_name}")

def main():
    """
    Load all HCSS CSV files in the correct order.
    """
    
    imports = [
        (
            "workers_with_teams.csv",
            "workers", # table name
            ["worker_id", "role", "contract_hours_week", "team"]
        ),
        (
            "worker_profiles.csv",
            "worker_profiles",
            ["worker_id", "sleep_need_hours"]
        ),
        (
            "historical_assignments.csv",
            "shift_assignments",
            [
                "shift_date", "worker_id", "team", "shift_type",
                "shift_start", "shift_end", "cycle_day"
            ]
        ),
        (
            "historical_sleep.csv",
            "historical_sleep",
            [
                "worker_id", "sleep_date", "linked_shift",
                "linked_shift_date", "sleep_start", "sleep_end",
                "sleep_duration_hours", "sleep_midpoint",
                "no_main_sleep_episode"
            ]
        )
    ]
    
    # Connect to the db:
    conn = get_connection()

    try:
        with conn.cursor() as cursor:

            # Safetycheck: stop if any target table already contains data
            for _, table_name, _ in imports:
                query = sql.SQL("SELECT COUNT(*) FROM {}").format( # make SQL template
                    sql.Identifier(table_name) # quote the table name safely
                )
                cursor.execute(query)

                if cursor.fetchone()[0] != 0:
                    raise ValueError(
                        f"Table {table_name} is not empty. "
                        "Import cancelled."
                    )

            # Import all CSV files in dependency order.
            for filename, table_name, columns in imports:
                load_csv(
                    cursor,
                    DATA_DIR / filename,
                    table_name,
                    columns
                )

        conn.commit()
        print("All files loaded successfully.")

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()
