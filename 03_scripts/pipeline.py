import os 
import sqlite3
import numpy as np 
import pandas as pd 


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_CSV_PATH = os.path.join(BASE_DIR, "../01_data/raw/ktm_aqi.csv")
DB_PATH = os.path.join(BASE_DIR, "../01_data/kathmandu_aqi.db")
PROCESSED_CSV_PATH = os.path.join(BASE_DIR, "../01_data/processed/kathmandu_aqi_clean.csv")

#Database Ingestion and SQL Querying 
print()
conn = sqlite3.connect(DB_PATH)

df_raw = pd.read_csv(
    RAW_CSV_PATH,
    on_bad_lines='skip',
    engine='python'
)
df_raw.to_sql("raw_aqi_data", conn, if_exists="replace", index=False)
print("Raw CSV loaded into SQLite database")

# Extract data back out using Standard SQL 
sql_query = "SELECT * FROM raw_aqi_data;"
df = pd.read_sql_query(sql_query, conn)
conn.close()

#Data Cleaning and Feature Engineering 
print()
time_col = [col for col in df.columns if 'time' in col.lower() or 'date' in col.lower()][0]
df['datetime'] = pd.to_datetime(df[time_col])

#extract time dimension for power BI analysis 
df['year'] = df['datetime'].dt.year
df['month_num'] = df['datetime'].dt.month
df['month_name'] = df['datetime'].dt.month_name()
df['hour'] = df['datetime'].dt.hour
df['day_name'] = df['datetime'].dt.day_name()
df['date'] = df['datetime'].dt.date

numeric_cols = df.select_dtypes(include=[np.number]).columns
df[numeric_cols] = df[numeric_cols].ffill().bfill()


aqi_col = [col for col in df.columns if 'aqi' in col.lower() or 'pm2' in col.lower()][0]

conditions = [
    (df[aqi_col] <= 50),
    (df[aqi_col] > 50) & (df[aqi_col] <= 100),
    (df[aqi_col] > 100) & (df[aqi_col] <= 150),
    (df[aqi_col] > 150) & (df[aqi_col] <= 200),
    (df[aqi_col] > 200)
]
categories = ["Good", "Moderate", "Unhealthy for Sensitive Groups", "Unhealthy", "Hazardous"]
df['aqi_category'] = np.select(conditions, categories, default="Unknown")

#Export Clean Dataset 
print()
os.makedirs(os.path.dirname(PROCESSED_CSV_PATH), exist_ok=True)
df.to_csv(PROCESSED_CSV_PATH, index=False)
print(f"Pipeline Complete! Processed data saved at: {PROCESSED_CSV_PATH}")