"""
02_get_historical_openaq.py
Pulls multi-year historical AQI/PM data for Kathmandu Valley stations
"""

import requests
import pandas as pd
import time

OPENAQ_API_KEY = "YOUR_OPENAQ_KEY_HERE"  # register at explore.openaq.org
BASE_URL = "https://api.openaq.org/v3"
HEADERS = {"X-API-Key": OPENAQ_API_KEY}


def get_locations(city_bbox: str) -> pd.DataFrame:
    # bbox format: lon_min,lat_min,lon_max,lat_max
    url = f"{BASE_URL}/locations?bbox={city_bbox}&limit=1000"
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    results = resp.json()["results"]

    locs = []
    for r in results:
        locs.append({
            "location_id": r["id"],
            "name": r["name"],
            "latitude": r["coordinates"]["latitude"],
            "longitude": r["coordinates"]["longitude"]
        })
    return pd.DataFrame(locs)


def get_measurements(location_id: int, date_from: str, date_to: str) -> pd.DataFrame:
    url = f"{BASE_URL}/locations/{location_id}/measurements"
    params = {
        "date_from": date_from,
        "date_to": date_to,
        "limit": 1000,
        "page": 1
    }
    all_rows = []
    while True:
        resp = requests.get(url, headers=HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()["results"]
        if not data:
            break
        all_rows.extend(data)
        params["page"] += 1
        time.sleep(0.5)
    return pd.DataFrame(all_rows)


if __name__ == "__main__":
    bbox = "85.20,27.60,85.45,27.80"
    locations = get_locations(bbox)
    locations.to_csv("01_data/raw/openaq_locations.csv", index=False)

    all_measurements = []
    for _, row in locations.iterrows():
        print(f"Pulling {row['name']}...")
        df = get_measurements(row["location_id"], "2022-01-01", "2025-12-31")
        df["location_name"] = row["name"]
        all_measurements.append(df)

    full_df = pd.concat(all_measurements, ignore_index=True)
    full_df.to_csv("01_data/raw/ktmaqi_openaq.csv", index=False)
    print(f"Saved {len(full_df)} rows")