import os
import sqlite3
import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_CSV_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "01_data", "raw", "ktm_aqi.csv"))
DB_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "01_data", "kathmandu_aqi.db"))
PROCESSED_CSV_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "01_data", "processed", "kathmandu_aqi_clean.csv"))

def categorize_aqi(aqi):
    if pd.isna(aqi):
        return "Unknown"
    elif aqi <= 50:
        return "Good"
    elif aqi <= 100:
        return "Moderate"
    elif aqi <= 150:
        return "Unhealthy for Sensitive Groups"
    elif aqi <= 200:
        return "Unhealthy"
    elif aqi <= 300:
        return "Very Unhealthy"
    else:
        return "Hazardous"

def run_pipeline():
    print("Starting Data Pipeline...")
    
    if not os.path.exists(RAW_CSV_PATH):
        print(f"Error: Raw CSV not found at {RAW_CSV_PATH}")
        return
        
    df_raw = pd.read_csv(RAW_CSV_PATH)
    print(f"Loaded {len(df_raw):,} rows from raw CSV.")

    conn = sqlite3.connect(DB_PATH)
    df_raw.to_sql("raw_aqi_data", conn, if_exists="replace", index=False)

    sql_query = "SELECT * FROM raw_aqi_data;"
    df = pd.read_sql_query(sql_query, conn)
    conn.close()

    time_cols = [col for col in df.columns if 'time' in col.lower() or 'date' in col.lower()]
    time_col = time_cols[0]
    
    df['datetime'] = pd.to_datetime(df[time_col])
    
    df['year'] = df['datetime'].dt.year
    df['month_num'] = df['datetime'].dt.month
    df['month_name'] = df['datetime'].dt.month_name()
    df['hour'] = df['datetime'].dt.hour
    df['day_name'] = df['datetime'].dt.day_name()
    df['date'] = df['datetime'].dt.date

    # Fill missing values for numerical metric columns
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    df[numeric_cols] = df[numeric_cols].ffill().bfill()

    # Recalculate AQI categories with non-null values
    df['aqi_category'] = df['us_aqi'].apply(categorize_aqi)

    os.makedirs(os.path.dirname(PROCESSED_CSV_PATH), exist_ok=True)
    df.to_csv(PROCESSED_CSV_PATH, index=False)
    print(f"Pipeline Complete! Saved clean dataset to:\n  {PROCESSED_CSV_PATH}")

if __name__ == "__main__":
    run_pipeline()