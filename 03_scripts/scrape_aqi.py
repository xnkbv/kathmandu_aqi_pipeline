import os
import requests
import pandas as pd

# Define path to output raw data
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_RAW_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "01_data", "raw", "ktm_aqi.csv"))

# Micro-coordinates for targeted stations in Kathmandu Valley
STATIONS = {
    "Ratnapark": {"lat": 27.7064, "lon": 85.3157},
    "Khumaltar": {"lat": 27.6558, "lon": 85.3253},
    "Bhaisepati": {"lat": 27.6586, "lon": 85.3045},
    "US_Embassy_Maharajgunj": {"lat": 27.7365, "lon": 85.3308}
}

def fetch_multi_station_aqi():
    print("Starting Multi-Station AQI Data Extraction...")
    station_dfs = []

    for station_name, coords in STATIONS.items():
        print(f"Fetching 3-year history for station: {station_name}...")
        url = (
            f"https://air-quality-api.open-meteo.com/v1/air-quality?"
            f"latitude={coords['lat']}&longitude={coords['lon']}"
            f"&hourly=pm10,pm2_5,us_aqi"
            f"&start_date=2023-01-01&end_date=2026-08-01"
            f"&timezone=Asia%2FKathmandu"
        )
        
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            df_temp = pd.DataFrame(data['hourly'])
            df_temp['station_name'] = station_name
            station_dfs.append(df_temp)
        else:
            print(f"Failed to fetch data for {station_name}. Status code: {response.status_code}")

    if station_dfs:
        # Combine all station logs into a single master raw file
        df_master = pd.concat(station_dfs, ignore_index=True)
        
        # Ensure raw folder exists and save CSV
        os.makedirs(os.path.dirname(OUTPUT_RAW_PATH), exist_ok=True)
        df_master.to_csv(OUTPUT_RAW_PATH, index=False)
        print(f"Extraction Complete! Saved {len(df_master):,} total rows across {len(STATIONS)} stations to:\n  {OUTPUT_RAW_PATH}")

if __name__ == "__main__":
    fetch_multi_station_aqi()