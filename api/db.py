# -*- coding: utf-8 -*-
"""
Created on Thu Oct 22 12:12:07 2026

@author: irisv
"""

# api/db.py
from pathlib import Path
import os
import psycopg2
from dotenv import load_dotenv

# .env sits next to this file, in api/
load_dotenv(Path(__file__).resolve().parent / ".env")


DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "port": os.getenv("DB_PORT"),
}

def get_connection():
    return psycopg2.connect(**DB_CONFIG)