
"""
Created on Oct 17 20:42:23 2026

uvicorn main:app --reload

@author: irisv
"""

import os # os.getenv() haalt 1 vd waarden van de variabelen op in python (van .env)
import psycopg2
from psycopg2.extras import RealDictCursor # Omdat jij RealDictCursor gebruikt:is ieder element in die lijst een dictionary-achtig RealDictRow:
from fastapi import FastAPI, HTTPException
from db import get_connection

import numpy as np
from datetime import datetime, timedelta, time
from sleep_metrics.calculate_sri import calculate_sri, build_sri_input
from sleep_metrics.summarize_sleep import summarize_by_linked_shift
from sleep_metrics.shift_analysis import build_sleep_by_shift, summarize_by_day_in_block, count_short_sleep, compute_diff_vs_off

# load_dotenv()


# Sleep shorter than this threshold (in hours) counts as short sleep.
SHORT_SLEEP_THRESHOLD_HOURS = 6

# FastAPI
app = FastAPI()


@app.get("/")
def root():
    return{"message": "API is running."}

@app.get("/workers/{worker_id}")
def get_worker(worker_id: str):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor) #RealDictCursor geeft diezelfde PostgreSQL-rij terug mét de kolomnamen:
    
    try:
        cur.execute(
            "SELECT worker_id, role, contract_hours_week, team FROM workers WHERE worker_id = %s",
            (worker_id,)
        )
        
        worker = cur.fetchone()
        
        if worker is None:
            raise HTTPException(status_code=404, detail='Worker not found.')
            
        return worker
    
    finally:
        cur.close()
        conn.close()
    

    
@app.get("/workers")
def get_workers():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cur.execute(
            "SELECT worker_id, role, contract_hours_week, team FROM workers"
        )
        
        workers = cur.fetchall()

        return workers
    
    finally:
        cur.close()
        conn.close()

@app.get("/sleep/{worker_id}")
def get_sleep(worker_id: str):
    conn = get_connection()
    cur = conn.cursor(cursor_factory = RealDictCursor)
    
    try:
        cur.execute(
        "SELECT worker_id FROM workers WHERE worker_id = %s",
        (worker_id,)
        
        )
        
        worker = cur.fetchone()
        
        if worker is None: # Check whether worker_id exists before trying to fetch it's sleep
            raise HTTPException(status_code=404, detail='Worker not found.')
        
        # Fetch sleep records from worker
        cur.execute(
            """
            SELECT worker_id, sleep_date, linked_shift, linked_shift_date, sleep_start, sleep_end, 
            sleep_duration_hours, sleep_midpoint, no_main_sleep_episode FROM historical_sleep 
            WHERE worker_id = %s
            ORDER BY sleep_date
            """,
            (worker_id,)
        )
        
        sleep_records = cur.fetchall()
        return sleep_records
    
    finally:
    
        cur.close()
        conn.close()
    
@app.get("/roster/{worker_id}")
def get_roster(worker_id: str):
    conn = get_connection()
    cur = conn.cursor(cursor_factory = RealDictCursor)
    
    try:
        cur.execute(
        "SELECT worker_id FROM workers WHERE worker_id = %s",
        (worker_id,)
        )
        
        worker = cur.fetchone()
        
        if worker is None:
            raise HTTPException(status_code=404, detail='Worker not found.')
        
        # Fetch schedule records of a certain worker
        cur.execute(
            "SELECT worker_id, shift_date, shift_type, shift_start, shift_end, team, cycle_day FROM shift_assignments WHERE worker_id = %s ORDER BY shift_date",
            (worker_id,)
        )
        roster_records = cur.fetchall()
        return roster_records
    
    finally: # always close the connection
        
        cur.close()
        conn.close()
        
@app.get("/sleep-summary/{worker_id}")
def get_sleep_summary(worker_id: str):
    conn = get_connection()
    cur = conn.cursor(cursor_factory = RealDictCursor)
    
    try:
        cur.execute(
        "SELECT worker_id FROM workers WHERE worker_id = %s",
        (worker_id,)
        )
        
        worker = cur.fetchone()
        
        if worker is None:
            raise HTTPException(status_code=404, detail='Worker not found.')
        
        # Fetch sleep records of the current worker:
        cur.execute(
        "SELECT sleep_duration_hours, no_main_sleep_episode FROM historical_sleep WHERE worker_id = %s",
        (worker_id,)
        )
        
        sleep_records = cur.fetchall()
        
        # Empty list to store sleep durations
        sleep_durations=[]
        # Counter to count nights without sleep episode
        num_no_main_sleep_episodes = 0
        
        for record in sleep_records:
            if record["no_main_sleep_episode"]:
                # Observed night without main sleep: count it, no duration
                num_no_main_sleep_episodes += 1
            else:
                sleep_durations.append(record["sleep_duration_hours"])

        num_nights = len(sleep_records)
        

        # Every night was without a main sleep episode: no duration statistics possible
        if len(sleep_durations) == 0:
            return {
                "worker_id": worker_id,
                "num_nights": num_nights,
                "num_valid_sleep_episodes": 0,
                "num_no_main_sleep_episodes": num_no_main_sleep_episodes,
                "mean_duration": None,
                "min_sleep_duration": None,
                "max_sleep_duration": None,
            }
        

        return {
            "worker_id": worker_id,
            "num_nights": num_nights,
            "num_valid_sleep_episodes": len(sleep_durations),
            "num_no_main_sleep_episodes": num_no_main_sleep_episodes,
            "mean_duration": np.mean(sleep_durations),
            "min_sleep_duration": np.min(sleep_durations),
            "max_sleep_duration": np.max(sleep_durations),
        }
    
    finally:
        cur.close()
        conn.close()
        
@app.get("/sleep-summary-by-shift/{worker_id}")
def get_sleep_summary_by_shift(worker_id: str):
    conn = get_connection()
    cur = conn.cursor(cursor_factory = RealDictCursor)
    
    try:
        cur.execute(
        
            "SELECT worker_id FROM workers WHERE worker_id = %s",
            (worker_id,)        
            )
        
        worker = cur.fetchone()
        
        if worker is None:
            raise HTTPException(status_code=404, detail='Worker not found.')
        
        # Fetch sleep records of the current worker:
        cur.execute(
            "SELECT linked_shift, sleep_duration_hours, no_main_sleep_episode FROM historical_sleep WHERE worker_id = %s",
            (worker_id,)
            )    
        # Fetch all sleep records   
        sleep_records = cur.fetchall()
        
        # Call summary_by_linked_shift with the records argument, get smmary_by_shift in return
        summary_by_shift = summarize_by_linked_shift(sleep_records) # Strtegy B (num no main sleep counted separately)

        return summary_by_shift
         
    finally:
        cur.close()
        conn.close()

@app.get("/shift-sleep/{worker_id}")
def get_shift_sleep(worker_id: str):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
    
        cur.execute(
            "SELECT worker_id FROM workers WHERE worker_id = %s",
            (worker_id,)
            
            )
        
        worker = cur.fetchone()
        
        if worker is None:
            raise HTTPException(status_code=404, detail='Worker not found.')
        
        # Fetch shift-sleep records of the current worker:
        cur.execute(
            """
            SELECT s.worker_id, s.shift_date, s.shift_type, h.sleep_date, h.sleep_duration_hours, h.sleep_midpoint
            FROM shift_assignments AS s
            INNER JOIN historical_sleep AS h
            ON s.worker_id=h.worker_id
                AND s.shift_date=h.linked_shift_date
            WHERE s.worker_id = %s
            ORDER BY s.shift_date ASC;
            """
            ,
            (worker_id,)
            
            )
        
        shift_sleep_records = cur.fetchall()
        
        return shift_sleep_records

    finally:
        cur.close()
        conn.close()
        
@app.get("/shift-sleep-analysis/{worker_id}")
def shift_sleep_analyses(worker_id: str): 
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
    
        cur.execute(
            "SELECT worker_id FROM workers WHERE worker_id = %s",
            (worker_id,)
            
            )
        
        worker = cur.fetchone()
        
        if worker is None:
            raise HTTPException(status_code=404, detail='Worker not found.')
    
        
        # ============================================================
        # Query 1 - shifts joined with their linked sleep
        #         (early/late/night only, ordered by shift_date)
        # ============================================================
            # Fetch shift-sleep records of the current worker:
        cur.execute(
            """
            SELECT s.worker_id, s.shift_date, s.shift_type, h.sleep_date, h.sleep_duration_hours, h.sleep_midpoint, h.no_main_sleep_episode
            FROM shift_assignments AS s
            INNER JOIN historical_sleep AS h
            ON s.worker_id=h.worker_id
                AND s.shift_date=h.linked_shift_date
            WHERE s.worker_id = %s AND s.shift_type != 'off'
            ORDER BY s.shift_date ASC;
            """
            ,
            (worker_id,)
            
            )
        
        shift_sleep_records = cur.fetchall() 
        
        # ============================================================
        # STEP 3: Build sleep_by_shift - entries per shift type,
        #         with day_in_shift_block (n-th day in a row)
        # TODO (censoring): blocks at the edges of the data window may be
        #   incomplete. A block already running on the first day gets wrong
        #   day numbers (e.g. W005 night 25-28 May = real days 4-7, labelled 1-4).
        #   Decide later: exclude these blocks, or generate a longer history
        #   so that dropping them matters less. See commented code below.
        # ============================================================
        sleep_by_shift = build_sleep_by_shift(shift_sleep_records)
        
        # ============================================================
        # Mean sleep duration per day in shift block
        #    Note: it handles nights without main sleep by counting them, but not including them in mean (strategy B)
        # ============================================================
        
        mean_sleep_by_day_in_block = summarize_by_day_in_block(sleep_by_shift)
        
        # ============================================================
        # Short sleep (< 6 h) per shift type
        # Note: night without main sleep counts as short sleep
        # ============================================================

        short_sleep_by_shift = count_short_sleep(sleep_by_shift, SHORT_SLEEP_THRESHOLD_HOURS)                  
        
        # ============================================================
        # Query 2 - mean sleep duration per linked shift (incl. off)
        # ============================================================
        cur.execute(
        """
        SELECT linked_shift, sleep_duration_hours, no_main_sleep_episode
        FROM historical_sleep
        WHERE worker_id = %s
        """,
        (worker_id,)
        )
        
        sleep_records = cur.fetchall()
        
        # Call function to get the summarized results
        summary_by_linked_shift = summarize_by_linked_shift(sleep_records) # Strategy B (num no main sleep counted separately)
        
        # Call function to compute the relative differences between sleep on shift days versus on off-days
        duration_diff_vs_off = compute_diff_vs_off(summary_by_linked_shift)
        
        # ============================================================
        # RETURN: results
        # ============================================================       
        return {
            "sleep_by_shift": sleep_by_shift,
            "mean_sleep_by_day_in_block": mean_sleep_by_day_in_block,
            "short_sleep_by_shift": short_sleep_by_shift,
            "mean_sleep_by_shift": summary_by_linked_shift,
            "duration_diff_vs_off": duration_diff_vs_off
        }
    
    
    
    finally:
        cur.close()
        conn.close()
        

@app.get("/sleep-regularity/{worker_id}")
def sleep_regularity(worker_id: str):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
    
        cur.execute(
            """
            SELECT sleep_date, sleep_start, sleep_end, no_main_sleep_episode
            FROM historical_sleep
            WHERE worker_id = %s
            ORDER BY sleep_date
            """,
            (worker_id,)
        )

        # Fetch the list 'sleep_records'
        sleep_records = cur.fetchall()
        
        if not sleep_records:
            raise HTTPException(status_code=404,detail=f"No sleep records found for worker {worker_id}"
            )                
        
        # Convert sleep records to minute-indexed episodes (see build_sri_input)
        episodes, total_days = build_sri_input(sleep_records)

        # Calculate the overall SRI and the SRI for each pair of consecutive days.
        try:
            sri_full_signal, daily_sri = calculate_sri(episodes, total_days=total_days)
        except ValueError as e:
            # Catch the calculation error and raise an HTTP error instead
            raise HTTPException(status_code=422, detail=str(e))
        
        return {
            "worker_id": worker_id,
            "sri_score": round(sri_full_signal, 1),
            "daily_sri": [round(float(score),1) for score in daily_sri]
        }
    
    finally:
        cur.close()
        conn.close()
        
        
@app.get("/db-test")
def test_database():
    conn = get_connection()
    conn.close()
    return {"message": "Database connection succeeded!"}


