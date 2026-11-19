"""
Fetch measured hourly PM2.5 / PM10 for real monitoring stations in the
Kathmandu Valley from the OpenAQ v3 API.

Outputs (both overwritten on every run):
  01_data/raw/stations.csv   one row per station (id, name, lat/lon, provider, type)
  01_data/raw/ktm_aqi.csv    long format: one row per station / hour / parameter

API key: set the OPENAQ_API_KEY environment variable, or paste the key into
a file called `openaq_api_key.txt` in the project root (it is git-ignored).
Get a free key at https://explore.openaq.org
"""
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))
RAW_DIR = os.path.join(PROJECT_DIR, "01_data", "raw")
OUTPUT_RAW_PATH = os.path.join(RAW_DIR, "ktm_aqi.csv")
OUTPUT_STATIONS_PATH = os.path.join(RAW_DIR, "stations.csv")
KEY_FILE = os.path.join(PROJECT_DIR, "openaq_api_key.txt")

API = "https://api.openaq.org/v3"

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
# Kathmandu Valley bounding box: min_lon, min_lat, max_lon, max_lat
VALLEY_BBOX = (85.18, 27.58, 85.52, 27.82)

START_DATE = "2023-01-01"
END_DATE = None  # None = up to today

PARAMETERS = {"pm25", "pm10"}

# False = reference monitors AND low-cost sensors (AirGradient etc.).
#         In the valley, OpenAQ has only 2 reference monitors (US Embassy), so the
#         low-cost network is what makes a station map possible. Low-cost sensors
#         are labelled sensor_type="low-cost" so they can be shown separately.
# True  = reference monitors only.
MONITORS_ONLY = False

# Skip stations with fewer than this many days of PM2.5 data in the period
MIN_DAYS_OF_DATA = 60

PAGE_LIMIT = 1000
REQUEST_PAUSE_S = 1.1  # stay under the free tier's 60 requests/minute


def load_api_key():
    key = os.environ.get("OPENAQ_API_KEY", "").strip()
    if not key and os.path.exists(KEY_FILE):
        with open(KEY_FILE, encoding="utf-8") as f:
            key = f.read().strip()
    if not key:
        sys.exit(
            "No OpenAQ API key found.\n"
            "Get a free key at https://explore.openaq.org, then either:\n"
            "  - set the OPENAQ_API_KEY environment variable, or\n"
            f"  - paste it into {KEY_FILE}"
        )
    return key


def get(session, path, params=None, retries=5):
    """GET with polite pacing and retry on rate limits / transient errors."""
    url = f"{API}{path}"
    for attempt in range(retries):
        time.sleep(REQUEST_PAUSE_S)
        try:
            r = session.get(url, params=params, timeout=60)
        except requests.RequestException as e:
            wait = 5 * (attempt + 1)
            print(f"   network error ({e}); retrying in {wait}s")
            time.sleep(wait)
            continue
        if r.status_code == 200:
            return r.json()
        if r.status_code in (408, 429, 500, 502, 503, 504):
            wait = int(r.headers.get("x-ratelimit-reset", 0) or 0) or 10 * (attempt + 1)
            print(f"   HTTP {r.status_code}; waiting {wait}s before retry")
            time.sleep(wait)
            continue
        if r.status_code == 401:
            sys.exit("OpenAQ rejected the API key (HTTP 401). Check the key and try again.")
        r.raise_for_status()
    raise RuntimeError(f"Giving up on {url} after {retries} attempts")


def find_stations(session, monitors_only=MONITORS_ONLY):
    params = {
        "bbox": ",".join(str(v) for v in VALLEY_BBOX),
        "limit": PAGE_LIMIT,
        "page": 1,
    }
    if monitors_only:
        params["monitor"] = "true"

    locations = []
    while True:
        data = get(session, "/locations", params)
        results = data.get("results", [])
        locations.extend(results)
        if len(results) < PAGE_LIMIT:
            break
        params["page"] += 1

    stations, sensors = [], []
    for loc in locations:
        if loc.get("isMobile"):
            continue
        coords = loc.get("coordinates") or {}
        loc_sensors = [
            s for s in loc.get("sensors", [])
            if (s.get("parameter") or {}).get("name") in PARAMETERS
        ]
        if not loc_sensors or coords.get("latitude") is None:
            continue
        stations.append({
            "station_id": loc["id"],
            "station_name": clean_name(loc.get("name") or f"Station {loc['id']}"),
            "latitude": coords["latitude"],
            "longitude": coords["longitude"],
            "provider": (loc.get("provider") or {}).get("name"),
            "owner": (loc.get("owner") or {}).get("name"),
            "sensor_type": "reference" if loc.get("isMonitor") else "low-cost",
            "first_seen_utc": (loc.get("datetimeFirst") or {}).get("utc"),
            "last_seen_utc": (loc.get("datetimeLast") or {}).get("utc"),
        })
        for s in loc_sensors:
            sensors.append({
                "station_id": loc["id"],
                "sensor_id": s["id"],
                "parameter": s["parameter"]["name"],
            })
    stations = pd.DataFrame(stations)
    if not stations.empty:
        stations = stations.sort_values(["sensor_type", "station_id"], ascending=[False, True])
        stations["station_name"] = make_unique(stations["station_name"].tolist())
    return stations, pd.DataFrame(sensors)


def clean_name(name):
    """'Lagankhel (SC - 05) - GD Labs' -> 'Lagankhel',
    'CEN-SR-25: Patako Chowk, Patan Durbar Square' -> 'Patako Chowk, Patan Durbar Square',
    'Phora Durbar Kathman' -> 'Phora Durbar'."""
    n = name.replace("_", " ")
    n = re.sub(r"^\s*CEN-SR-\d+\s*:\s*", "", n)                 # CEN-SR-25: prefix
    n = re.sub(r"[-\s]*GD\s*labs\s*$", "", n, flags=re.I)        # GD Labs suffix
    n = re.sub(r"\(\s*SC\s*-?\s*\d+\s*\)", "", n, flags=re.I)    # (SC - 05)
    n = re.sub(r"\s+Kathman(du)?$", "", n)                       # trailing 'Kathmandu'
    n = " ".join(n.split()).strip(" -,")
    return NAME_OVERRIDES.get(n, n) or name


# Clearer names for the two US Embassy monitors
NAME_OVERRIDES = {
    "Embassy": "US Embassy (Maharajgunj)",
    "Phora Durbar": "US Embassy (Phora Durbar)",
}


def make_unique(names):
    """Give repeated names a number so each station stays separate in Power BI."""
    seen, out = {}, []
    for n in names:
        seen[n] = seen.get(n, 0) + 1
        out.append(n if seen[n] == 1 else f"{n} {seen[n]}")
    return out


def to_utc(value):
    ts = pd.Timestamp(value)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    return ts.to_pydatetime()


def month_windows(start, end):
    """Split the date range into ~1 month chunks: at most 744 hours, so each
    request fits in a single page and doesn't time out."""
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=31), end)
        yield cur, nxt
        cur = nxt


def fetch_sensor_hours(session, sensor_id, start, end, first_seen=None, last_seen=None):
    rows = []
    # Only ask for the period this sensor actually has data for
    if first_seen:
        start = max(start, to_utc(first_seen))
    if last_seen:
        end = min(end, to_utc(last_seen) + timedelta(hours=1))
    windows = list(month_windows(start, end))
    for i, (w_start, w_end) in enumerate(windows, 1):
        print(f"   month {i}/{len(windows)}", end="\r")
        page = 1
        while True:
            data = get(session, f"/sensors/{sensor_id}/hours", {
                "datetime_from": w_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "datetime_to": w_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "limit": PAGE_LIMIT,
                "page": page,
            })
            results = data.get("results", [])
            for m in results:
                period = m.get("period") or {}
                dt_from = (period.get("datetimeFrom") or {}).get("utc")
                coverage = (m.get("coverage") or {}).get("percentComplete")
                if dt_from is None or m.get("value") is None:
                    continue
                rows.append((dt_from, m["value"], coverage))
            if len(results) < PAGE_LIMIT:
                break
            page += 1
    return rows


def list_all_stations():
    """Print every station OpenAQ has in the valley (reference and low-cost),
    with the period each has data for. Downloads no measurements."""
    session = requests.Session()
    session.headers.update({"X-API-Key": load_api_key(), "Accept": "application/json"})
    stations, sensors = find_stations(session, monitors_only=False)
    if stations.empty:
        sys.exit("OpenAQ has no stations with PM sensors in the valley bounding box.")
    params = sensors.groupby("station_id").parameter.apply(lambda p: ",".join(sorted(set(p))))
    stations["params"] = stations.station_id.map(params)
    stations["from"] = stations.first_seen_utc.astype(str).str[:10]
    stations["to"] = stations.last_seen_utc.astype(str).str[:10]
    stations = stations.sort_values(["sensor_type", "to"], ascending=[False, False])
    pd.set_option("display.width", 200)
    pd.set_option("display.max_rows", 500)
    print(stations[["station_id", "station_name", "sensor_type", "provider",
                    "params", "from", "to"]].to_string(index=False))
    print(f"\n{len(stations)} stations: "
          f"{(stations.sensor_type == 'reference').sum()} reference, "
          f"{(stations.sensor_type == 'low-cost').sum()} low-cost")


def fetch_multi_station_aqi():
    print("Starting Kathmandu Valley station data extraction (OpenAQ v3)...")
    session = requests.Session()
    session.headers.update({"X-API-Key": load_api_key(), "Accept": "application/json"})

    start = datetime.fromisoformat(START_DATE).replace(tzinfo=timezone.utc)
    end = (datetime.fromisoformat(END_DATE).replace(tzinfo=timezone.utc)
           if END_DATE else datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0))

    stations, sensors = find_stations(session)
    if stations.empty:
        sys.exit("No stations found in the valley bounding box. Check VALLEY_BBOX / MONITORS_ONLY.")

    # Skip stations that never reported, or stopped before / started after the period
    last = pd.to_datetime(stations.last_seen_utc, utc=True, errors="coerce")
    first = pd.to_datetime(stations.first_seen_utc, utc=True, errors="coerce")
    active = last.notna() & first.notna() & (last >= pd.Timestamp(start)) & (first <= pd.Timestamp(end))
    if (~active).any():
        print(f"Skipping {(~active).sum()} station(s) with no data in the period: "
              f"{stations.loc[~active, 'station_name'].tolist()}")
    stations = stations[active]
    sensors = sensors[sensors.station_id.isin(stations.station_id)]
    print(f"Found {len(stations)} stations with PM sensors:")
    for _, s in stations.iterrows():
        print(f"  - {s.station_name} ({s.sensor_type}, {s.provider})")

    all_rows = []
    for _, sen in sensors.iterrows():
        st = stations.loc[stations.station_id == sen.station_id].iloc[0]
        print(f"Fetching {sen.parameter} for {st.station_name} (sensor {sen.sensor_id})...")
        rows = fetch_sensor_hours(session, sen.sensor_id, start, end,
                                  st.first_seen_utc if pd.notna(st.first_seen_utc) else None,
                                  st.last_seen_utc if pd.notna(st.last_seen_utc) else None)
        print(f"   {len(rows):,} hourly values")
        for dt_utc, value, coverage in rows:
            all_rows.append({
                "station_id": sen.station_id,
                "station_name": st.station_name,
                "datetime_utc": dt_utc,
                "parameter": sen.parameter,
                "value": value,
                "coverage_pct": coverage,
                "source": "OpenAQ",
            })

    df = pd.DataFrame(all_rows)
    if df.empty:
        sys.exit("No measurements returned for the selected period.")

    # Drop stations with too little data to be meaningful
    days = (df[df.parameter == "pm25"]
            .assign(day=lambda d: d.datetime_utc.str[:10])
            .groupby("station_id").day.nunique())
    keep = days[days >= MIN_DAYS_OF_DATA].index
    dropped = set(stations.station_id) - set(keep)
    if dropped:
        names = stations.loc[stations.station_id.isin(dropped), "station_name"].tolist()
        print(f"Skipping {len(dropped)} station(s) with < {MIN_DAYS_OF_DATA} days of PM2.5: {names}")
    df = df[df.station_id.isin(keep)]
    stations = stations[stations.station_id.isin(keep)].copy()
    stations["source"] = "OpenAQ"

    os.makedirs(RAW_DIR, exist_ok=True)
    df.to_csv(OUTPUT_RAW_PATH, index=False)
    stations.to_csv(OUTPUT_STATIONS_PATH, index=False)
    print(f"\nSaved {len(df):,} rows for {len(stations)} stations to:\n  {OUTPUT_RAW_PATH}\n  {OUTPUT_STATIONS_PATH}")


if __name__ == "__main__":
    if "--list" in sys.argv:
        list_all_stations()
    else:
        fetch_multi_station_aqi()
