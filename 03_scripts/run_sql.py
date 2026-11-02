import os
import sqlite3
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "01_data", "kathmandu_aqi.db"))
CLEAN_CSV = os.path.abspath(os.path.join(BASE_DIR, "..", "01_data", "processed", "kathmandu_aqi_clean.csv"))
SCHEMA_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "02_sql", "schema.sql"))

def execute_pipeline_sql():
    if not os.path.exists(CLEAN_CSV):
        print(f"Error: Clean dataset not found at {CLEAN_CSV}")
        return

    conn = sqlite3.connect(DB_PATH)

    # 1. Load Processed CSV
    print("Loading clean CSV dataset...")
    df_clean = pd.read_csv(CLEAN_CSV)
    
    # Drop raw 'time' column if it exists to match clean SQL table structure
    if 'time' in df_clean.columns:
        df_clean = df_clean.drop(columns=['time'])

    # 2. Write directly to SQLite table (automatically creates matching schema)
    print("Writing data into SQLite table 'kathmandu_aqi'...")
    df_clean.to_sql("kathmandu_aqi", conn, if_exists="replace", index=False)
    conn.commit()
    print(f"Successfully loaded {len(df_clean):,} rows into SQLite.")

    # 3. Run Query 1: Most Polluted Day & Hour of Every Month
    print("\n" + "="*65)
    print("MOST POLLUTED DAY & HOUR OF EVERY MONTH")
    print("="*65)
    
    q1 = """
    WITH MonthlyRankedAQI AS (
        SELECT month_num, month_name, date, day_name, hour, station_name, us_aqi, pm2_5,
               ROW_NUMBER() OVER (PARTITION BY month_num ORDER BY us_aqi DESC, pm2_5 DESC) as rank
        FROM kathmandu_aqi
    )
    SELECT month_num, month_name, date as peak_date, day_name, 
           printf('%02d:00', hour) as peak_hour, station_name, us_aqi as max_us_aqi, pm2_5 as max_pm2_5
    FROM MonthlyRankedAQI WHERE rank = 1 ORDER BY month_num ASC;
    """
    df_q1 = pd.read_sql_query(q1, conn)
    print(df_q1.to_string(index=False))

    # 4. Run Query 2: Area Station Ranking & Heatmap Data Baseline
    print("\n" + "="*65)
    print("STATION AREA RANKINGS (HEATMAP BASELINE)")
    print("="*65)
    
    q2 = """
    SELECT station_name, 
           ROUND(AVG(us_aqi), 1) as avg_aqi, 
           MAX(us_aqi) as max_aqi,
           ROUND(AVG(pm2_5), 1) as avg_pm2_5,
           ROUND(100.0 * SUM(CASE WHEN us_aqi > 150 THEN 1 ELSE 0 END) / COUNT(*), 2) as pct_unhealthy_hours
    FROM kathmandu_aqi 
    GROUP BY station_name 
    ORDER BY avg_aqi DESC;
    """
    df_q2 = pd.read_sql_query(q2, conn)
    print(df_q2.to_string(index=False))

    conn.close()

if __name__ == "__main__":
    execute_pipeline_sql()