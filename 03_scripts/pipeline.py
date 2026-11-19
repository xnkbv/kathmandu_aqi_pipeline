"""
Clean and enrich the raw station data.

Inputs
  01_data/raw/ktm_aqi.csv      hourly station data from scrape_aqi.py (OpenAQ)
  01_data/raw/stations.csv     station metadata from scrape_aqi.py
  01_data/raw/airnow/*.csv     optional: US Embassy hourly files downloaded from
                               AirNow.gov (US Embassies and Consulates > Kathmandu
                               > Historical Data)

Outputs (01_data/processed/) - ready for Power BI
  kathmandu_aqi_clean.csv      one row per station per hour
  daily_station_summary.csv    one row per station per day (worst days, peak hour)
  stations.csv                 one row per station (map: lat/lon, averages, coverage)
"""
import glob
import os

import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "01_data"))
RAW_CSV_PATH = os.path.join(DATA_DIR, "raw", "ktm_aqi.csv")
RAW_STATIONS_PATH = os.path.join(DATA_DIR, "raw", "stations.csv")
AIRNOW_DIR = os.path.join(DATA_DIR, "raw", "airnow")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
PROCESSED_CSV_PATH = os.path.join(PROCESSED_DIR, "kathmandu_aqi_clean.csv")
DAILY_CSV_PATH = os.path.join(PROCESSED_DIR, "daily_station_summary.csv")
STATIONS_CSV_PATH = os.path.join(PROCESSED_DIR, "stations.csv")

# Nepal is UTC+05:45 all year (no daylight saving), so a fixed offset is exact.
NEPAL_OFFSET = pd.Timedelta(hours=5, minutes=45)

# US Embassy monitor (AirNow). Coordinates of the Maharajgunj embassy compound.
AIRNOW_STATION = {
    "station_id": "airnow_us_embassy",
    "station_name": "US Embassy (Maharajgunj)",
    "latitude": 27.7365,
    "longitude": 85.3308,
    "provider": "AirNow (US Department of State)",
    "owner": "US Embassy Kathmandu",
    "sensor_type": "reference",
    "source": "AirNow",
}

# --- Quality control settings ----------------------------------------------
MAX_VALID = {"pm2_5": 1000.0, "pm10": 2000.0}   # physically implausible above this
FLATLINE_HOURS = 6        # identical value for this many hours in a row = stuck sensor
MAX_GAP_TO_FILL = 3       # interpolate gaps up to 3 hours; longer gaps stay empty
MIN_HOURS_FOR_DAILY = 18  # a day needs 18 measured hours to get a daily average
MIN_HOURS_FOR_24H = 18    # same rule for the rolling 24-hour average behind AQI
DUPLICATE_RADIUS_M = 300  # two stations closer than this are treated as one

# --- US EPA AQI breakpoints (PM2.5 revised in 2024) -------------------------
PM25_BREAKPOINTS = [
    (0.0, 9.0, 0, 50), (9.1, 35.4, 51, 100), (35.5, 55.4, 101, 150),
    (55.5, 125.4, 151, 200), (125.5, 225.4, 201, 300), (225.5, 325.4, 301, 500),
]
PM10_BREAKPOINTS = [
    (0, 54, 0, 50), (55, 154, 51, 100), (155, 254, 101, 150),
    (255, 354, 151, 200), (355, 424, 201, 300), (425, 604, 301, 500),
]

SEASONS = {12: "Winter", 1: "Winter", 2: "Winter",
           3: "Pre-monsoon", 4: "Pre-monsoon", 5: "Pre-monsoon",
           6: "Monsoon", 7: "Monsoon", 8: "Monsoon", 9: "Monsoon",
           10: "Post-monsoon", 11: "Post-monsoon"}


def aqi_from_conc(conc, breakpoints, decimals):
    """Vectorised EPA AQI from a concentration series."""
    c = np.floor(conc * 10**decimals) / 10**decimals  # EPA truncates, not rounds
    out = pd.Series(np.nan, index=conc.index)
    for c_lo, c_hi, i_lo, i_hi in breakpoints:
        mask = (c >= c_lo) & (c <= c_hi)
        out[mask] = (i_hi - i_lo) / (c_hi - c_lo) * (c[mask] - c_lo) + i_lo
    out[c > breakpoints[-1][1]] = 500
    return out.round()


def categorize_aqi(aqi):
    if pd.isna(aqi):
        return "No data"
    if aqi <= 50:
        return "Good"
    if aqi <= 100:
        return "Moderate"
    if aqi <= 150:
        return "Unhealthy for Sensitive Groups"
    if aqi <= 200:
        return "Unhealthy"
    if aqi <= 300:
        return "Very Unhealthy"
    return "Hazardous"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_openaq():
    if not os.path.exists(RAW_CSV_PATH) or not os.path.exists(RAW_STATIONS_PATH):
        print("No OpenAQ data found - run scrape_aqi.py first.")
        return pd.DataFrame(), pd.DataFrame()
    raw = pd.read_csv(RAW_CSV_PATH)
    required = {"station_id", "datetime_utc", "parameter", "value"}
    if not required.issubset(raw.columns):
        raise SystemExit(
            f"{RAW_CSV_PATH} is in the old Open-Meteo format. "
            "Run scrape_aqi.py to download station data first."
        )
    stations = pd.read_csv(RAW_STATIONS_PATH)
    raw["datetime_utc"] = pd.to_datetime(raw["datetime_utc"], utc=True).dt.tz_localize(None)
    raw["parameter"] = raw["parameter"].map({"pm25": "pm2_5", "pm10": "pm10"})
    wide = (raw.dropna(subset=["parameter"])
               .pivot_table(index=["station_id", "datetime_utc"], columns="parameter",
                            values="value", aggfunc="mean")
               .reset_index())
    wide.columns.name = None
    wide["station_id"] = wide["station_id"].astype(str)
    stations["station_id"] = stations["station_id"].astype(str)
    print(f"OpenAQ: {len(wide):,} station-hours from {wide.station_id.nunique()} stations")
    return wide, stations


def load_airnow():
    files = sorted(glob.glob(os.path.join(AIRNOW_DIR, "*.csv")))
    if not files:
        return pd.DataFrame(), pd.DataFrame()
    frames = []
    for f in files:
        d = pd.read_csv(f)
        d.columns = [c.strip() for c in d.columns]
        if "Raw Conc." not in d.columns or "Date (LT)" not in d.columns:
            print(f"  skipping {os.path.basename(f)} (not an AirNow hourly file)")
            continue
        if "Parameter" in d.columns:
            d = d[d["Parameter"].astype(str).str.upper().str.contains("PM2.5")]
        if "QC Name" in d.columns:
            d = d[d["QC Name"].astype(str).str.strip().str.lower() == "valid"]
        d = d[d["Raw Conc."] > -999]
        local = pd.to_datetime(d["Date (LT)"], errors="coerce")
        frames.append(pd.DataFrame({
            "station_id": AIRNOW_STATION["station_id"],
            "datetime_utc": local - NEPAL_OFFSET,
            "pm2_5": d["Raw Conc."].astype(float),
        }).dropna(subset=["datetime_utc"]))
    if not frames:
        return pd.DataFrame(), pd.DataFrame()
    df = (pd.concat(frames)
            .drop_duplicates(subset=["station_id", "datetime_utc"])
            .sort_values("datetime_utc"))
    df["pm10"] = np.nan
    print(f"AirNow: {len(df):,} station-hours from {len(files)} file(s)")
    return df, pd.DataFrame([AIRNOW_STATION])


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def drop_duplicate_stations(df, stations):
    """The same monitor can appear in both OpenAQ and AirNow files. Keep the one
    with more data. Neighbouring sensors from the same source are all kept."""
    counts = df.groupby("station_id").pm2_5.count()
    stations = stations.assign(n=stations.station_id.map(counts).fillna(0)).sort_values("n", ascending=False)
    kept = []
    for _, s in stations.iterrows():
        if any(k.source != s.source and
               haversine_m(s.latitude, s.longitude, k.latitude, k.longitude) < DUPLICATE_RADIUS_M
               for k in kept):
            print(f"  '{s.station_name}' duplicates a nearby station with more data - dropped")
            continue
        kept.append(s)
    stations = pd.DataFrame(kept).drop(columns="n")
    return df[df.station_id.isin(stations.station_id)], stations


# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------
def quality_control(g):
    """Applied to one station at a time."""
    for col in ("pm2_5", "pm10"):
        s = g[col]
        bad = (s < 0) | (s > MAX_VALID[col])
        # stuck sensor: the same value repeated for FLATLINE_HOURS+ consecutive hours
        run_id = (s != s.shift()).cumsum()
        run_len = s.groupby(run_id).transform("size")
        bad |= s.notna() & (run_len >= FLATLINE_HOURS)
        g.loc[bad, col] = np.nan
    return g


def complete_hours(g):
    """Give each station a row for every hour between its first and last reading,
    so gaps are visible, then fill only short gaps."""
    sid = g.station_id.iloc[0]
    g = g.set_index("datetime_utc").sort_index()
    g = g[~g.index.duplicated()]
    full = pd.date_range(g.index.min(), g.index.max(), freq="h")
    g = g.reindex(full)
    g.index.name = "datetime_utc"
    g["station_id"] = sid
    g = quality_control(g)
    g["is_measured"] = g["pm2_5"].notna()
    for col in ("pm2_5", "pm10"):
        g[col] = g[col].interpolate(limit=MAX_GAP_TO_FILL, limit_area="inside")
    g["is_imputed"] = ~g["is_measured"] & g["pm2_5"].notna()
    # 24-hour rolling means (what the US AQI is based on), using measured hours only
    for col in ("pm2_5", "pm10"):
        measured = g[col].where(g["is_measured"])
        g[f"{col}_24h"] = measured.rolling(24, min_periods=MIN_HOURS_FOR_24H).mean().round(1)
    return g.reset_index()


def run_pipeline():
    print("Starting Data Pipeline...")
    oa, oa_st = load_openaq()
    an, an_st = load_airnow()
    df = pd.concat([x for x in (oa, an) if not x.empty], ignore_index=True) if not (oa.empty and an.empty) else None
    if df is None:
        raise SystemExit("No input data. Run scrape_aqi.py and/or add AirNow files to 01_data/raw/airnow/.")
    stations = pd.concat([x for x in (oa_st, an_st) if not x.empty], ignore_index=True)
    stations["station_id"] = stations["station_id"].astype(str)
    df["station_id"] = df["station_id"].astype(str)
    if "pm10" not in df:
        df["pm10"] = np.nan

    df, stations = drop_duplicate_stations(df, stations)

    # Put every reading on a whole Nepal-time hour. Some feeds report at :00 UTC
    # and others at :15 UTC (= :45 / :00 Nepal time); without this, readings fall
    # between hourly slots and are lost. Readings in the same hour are averaged.
    df["datetime_utc"] = (df["datetime_utc"] + NEPAL_OFFSET).dt.floor("h") - NEPAL_OFFSET
    df = df.groupby(["station_id", "datetime_utc"], as_index=False)[["pm2_5", "pm10"]].mean()

    df = (df.groupby("station_id", group_keys=False)[["station_id", "datetime_utc", "pm2_5", "pm10"]]
            .apply(complete_hours))

    # Time attributes in Nepal local time
    df["datetime"] = df["datetime_utc"] + NEPAL_OFFSET
    df["date"] = df["datetime"].dt.date
    df["year"] = df["datetime"].dt.year
    df["month_num"] = df["datetime"].dt.month
    df["month_name"] = df["datetime"].dt.month_name()
    df["hour"] = df["datetime"].dt.hour
    df["day_name"] = df["datetime"].dt.day_name()
    df["day_type"] = np.where(df["day_name"] == "Saturday", "Weekend", "Weekday")
    df["season"] = df["month_num"].map(SEASONS)

    # AQI: 24-hour average, the higher of PM2.5 and PM10 (official EPA method)
    aqi25 = aqi_from_conc(df["pm2_5_24h"], PM25_BREAKPOINTS, 1)
    aqi10 = aqi_from_conc(df["pm10_24h"], PM10_BREAKPOINTS, 0)
    df["us_aqi"] = pd.concat([aqi25, aqi10], axis=1).max(axis=1)
    df["dominant_pollutant"] = np.where(aqi10.fillna(-1) > aqi25.fillna(-1), "PM10", "PM2.5")
    df.loc[df["us_aqi"].isna(), "dominant_pollutant"] = None
    df["aqi_category"] = df["us_aqi"].apply(categorize_aqi)
    # Hourly AQI from the hourly PM2.5 value: use for hour-by-hour visuals only
    df["hourly_aqi_pm25"] = aqi_from_conc(df["pm2_5"], PM25_BREAKPOINTS, 1)
    df["hourly_category"] = df["hourly_aqi_pm25"].apply(categorize_aqi)

    df = df.merge(stations[["station_id", "station_name"]], on="station_id", how="left")
    hourly_cols = ["station_id", "station_name", "datetime", "date", "year", "month_num",
                   "month_name", "hour", "day_name", "day_type", "season",
                   "pm2_5", "pm10", "pm2_5_24h", "pm10_24h", "us_aqi", "aqi_category",
                   "dominant_pollutant", "hourly_aqi_pm25", "hourly_category",
                   "is_measured", "is_imputed"]
    df = df[hourly_cols].sort_values(["station_name", "datetime"])

    # ----- Daily summary per station ---------------------------------------
    m = df[df["is_measured"]]
    idx_peak = m.groupby(["station_id", "date"])["pm2_5"].idxmax()
    peak = m.loc[idx_peak, ["station_id", "date", "hour", "pm2_5"]].rename(
        columns={"hour": "peak_hour", "pm2_5": "peak_hour_pm2_5"})
    daily = (m.groupby(["station_id", "station_name", "date"])
               .agg(measured_hours=("pm2_5", "size"),
                    daily_pm2_5=("pm2_5", "mean"),
                    min_hour_pm2_5=("pm2_5", "min"))
               .reset_index()
               .merge(peak, on=["station_id", "date"], how="left"))
    daily.loc[daily.measured_hours < MIN_HOURS_FOR_DAILY, "daily_pm2_5"] = np.nan
    daily["daily_pm2_5"] = daily["daily_pm2_5"].round(1)
    daily["daily_aqi"] = aqi_from_conc(daily["daily_pm2_5"], PM25_BREAKPOINTS, 1)
    daily["daily_category"] = daily["daily_aqi"].apply(categorize_aqi)
    d = pd.to_datetime(daily["date"])
    daily["year"], daily["month_num"] = d.dt.year, d.dt.month
    daily["month_name"], daily["day_name"] = d.dt.month_name(), d.dt.day_name()
    daily["season"] = daily["month_num"].map(SEASONS)
    # Rank of each day within its station (1 = worst day on record for that station)
    daily["worst_day_rank"] = daily.groupby("station_id")["daily_pm2_5"].rank(ascending=False, method="min")

    # ----- Station table (for the map) -------------------------------------
    span = df.groupby("station_id").agg(first_reading=("datetime", "min"),
                                        last_reading=("datetime", "max"),
                                        total_hours=("datetime", "size"),
                                        measured_hours=("is_measured", "sum"))
    full_days = daily.dropna(subset=["daily_pm2_5"])
    stats = full_days.groupby("station_id").agg(
        valid_days=("daily_pm2_5", "size"),
        avg_daily_pm2_5=("daily_pm2_5", "mean"),
        max_daily_pm2_5=("daily_pm2_5", "max"),
        pct_unhealthy_days=("daily_aqi", lambda s: 100 * (s > 150).mean()),
    )
    peak_hour = (m.groupby(["station_id", "hour"]).pm2_5.mean()
                  .groupby("station_id").idxmax().map(lambda t: t[1]).rename("typical_peak_hour"))
    st = (stations.set_index("station_id")
                  .join(span).join(stats).join(peak_hour).reset_index())
    st["coverage_pct"] = (100 * st["measured_hours"] / st["total_hours"]).round(1)
    st["avg_daily_pm2_5"] = st["avg_daily_pm2_5"].round(1)
    st["pct_unhealthy_days"] = st["pct_unhealthy_days"].round(1)
    st["avg_aqi"] = aqi_from_conc(st["avg_daily_pm2_5"], PM25_BREAKPOINTS, 1)
    st["avg_category"] = st["avg_aqi"].apply(categorize_aqi)
    st = st.drop(columns=[c for c in ("first_seen_utc", "last_seen_utc") if c in st.columns])

    os.makedirs(PROCESSED_DIR, exist_ok=True)
    df.to_csv(PROCESSED_CSV_PATH, index=False)
    daily.to_csv(DAILY_CSV_PATH, index=False)
    st.to_csv(STATIONS_CSV_PATH, index=False)

    print("\nStation coverage:")
    print(st[["station_name", "sensor_type", "first_reading", "last_reading",
              "coverage_pct", "avg_daily_pm2_5"]].to_string(index=False))
    print(f"\nPipeline Complete! Saved to {PROCESSED_DIR}:")
    print(f"  kathmandu_aqi_clean.csv     {len(df):,} station-hours")
    print(f"  daily_station_summary.csv   {len(daily):,} station-days")
    print(f"  stations.csv                {len(st)} stations")


if __name__ == "__main__":
    run_pipeline()
