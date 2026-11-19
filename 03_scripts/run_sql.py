"""
Load the processed CSVs into SQLite (using 02_sql/schema.sql) and run every
query in 02_sql/analytical_queries.sql, printing the results.
"""
import os
import re
import sqlite3

import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))
DB_PATH = os.path.join(PROJECT_DIR, "01_data", "kathmandu_aqi.db")
PROCESSED_DIR = os.path.join(PROJECT_DIR, "01_data", "processed")
SCHEMA_PATH = os.path.join(PROJECT_DIR, "02_sql", "schema.sql")
QUERIES_PATH = os.path.join(PROJECT_DIR, "02_sql", "analytical_queries.sql")

TABLES = {
    "stations": "stations.csv",
    "kathmandu_aqi": "kathmandu_aqi_clean.csv",
    "daily_station_summary": "daily_station_summary.csv",
}


def load_tables(conn):
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())
    for table, filename in TABLES.items():
        path = os.path.join(PROCESSED_DIR, filename)
        if not os.path.exists(path):
            raise SystemExit(f"Missing {path} - run pipeline.py first.")
        df = pd.read_csv(path)
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
        df = df[[c for c in cols if c in df.columns]]
        for c in ("is_measured", "is_imputed"):
            if c in df.columns:
                df[c] = df[c].astype(int)
        df.to_sql(table, conn, if_exists="append", index=False)
        print(f"Loaded {len(df):,} rows into '{table}'")
    conn.commit()


def run_queries(conn):
    with open(QUERIES_PATH, encoding="utf-8") as f:
        text = f.read()
    # Each query starts with a "-- QUERY n: title" header
    blocks = re.split(r"--\s*=+\s*\n--\s*(QUERY[^\n]*)\n", text)
    pd.set_option("display.width", 200)
    for title, body in zip(blocks[1::2], blocks[2::2]):
        sql = "\n".join(l for l in body.splitlines() if not l.strip().startswith("--")).strip()
        if not sql:
            continue
        print("\n" + "=" * 70 + f"\n{title}\n" + "=" * 70)
        df = pd.read_sql_query(sql, conn)
        print(df.head(40).to_string(index=False))
        if len(df) > 40:
            print(f"... ({len(df):,} rows total)")


def execute_pipeline_sql():
    conn = sqlite3.connect(DB_PATH)
    try:
        load_tables(conn)
        run_queries(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    execute_pipeline_sql()
