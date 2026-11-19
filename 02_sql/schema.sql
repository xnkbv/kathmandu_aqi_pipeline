-- Schema for Kathmandu AQI Analysis Pipeline
-- Three tables: stations (map), kathmandu_aqi (hourly), daily_station_summary (daily)

DROP TABLE IF EXISTS kathmandu_aqi;
DROP TABLE IF EXISTS daily_station_summary;
DROP TABLE IF EXISTS stations;

CREATE TABLE stations (
    station_id          TEXT PRIMARY KEY,
    station_name        TEXT NOT NULL,
    latitude            REAL NOT NULL,
    longitude           REAL NOT NULL,
    provider            TEXT,
    owner               TEXT,
    sensor_type         TEXT,      -- 'reference' or 'low-cost'
    source              TEXT,      -- 'OpenAQ' or 'AirNow'
    first_reading       TEXT,
    last_reading        TEXT,
    total_hours         INTEGER,
    measured_hours      INTEGER,
    valid_days          INTEGER,
    avg_daily_pm2_5     REAL,
    max_daily_pm2_5     REAL,
    pct_unhealthy_days  REAL,
    typical_peak_hour   INTEGER,
    coverage_pct        REAL,
    avg_aqi             INTEGER,
    avg_category        TEXT
);

CREATE TABLE kathmandu_aqi (
    station_id          TEXT NOT NULL REFERENCES stations(station_id),
    station_name        TEXT NOT NULL,
    datetime            TEXT NOT NULL,   -- Nepal local time (UTC+05:45)
    date                DATE NOT NULL,
    year                INTEGER NOT NULL,
    month_num           INTEGER NOT NULL,
    month_name          TEXT NOT NULL,
    hour                INTEGER NOT NULL,
    day_name            TEXT NOT NULL,
    day_type            TEXT NOT NULL,   -- Saturday = Weekend in Nepal
    season              TEXT NOT NULL,
    pm2_5               REAL,            -- hourly mean, µg/m³
    pm10                REAL,
    pm2_5_24h           REAL,            -- rolling 24h mean
    pm10_24h            REAL,
    us_aqi              INTEGER,         -- EPA AQI from 24h means
    aqi_category        TEXT,
    dominant_pollutant  TEXT,
    hourly_aqi_pm25     INTEGER,         -- indicative AQI of that single hour
    hourly_category     TEXT,
    is_measured         INTEGER,         -- 1 = real reading, 0 = gap
    is_imputed          INTEGER,         -- 1 = short gap filled by interpolation
    PRIMARY KEY (station_id, datetime)
);

CREATE TABLE daily_station_summary (
    station_id          TEXT NOT NULL REFERENCES stations(station_id),
    station_name        TEXT NOT NULL,
    date                DATE NOT NULL,
    measured_hours      INTEGER,
    daily_pm2_5         REAL,            -- NULL if fewer than 18 measured hours
    min_hour_pm2_5      REAL,
    peak_hour           INTEGER,
    peak_hour_pm2_5     REAL,
    daily_aqi           INTEGER,
    daily_category      TEXT,
    year                INTEGER,
    month_num           INTEGER,
    month_name          TEXT,
    day_name            TEXT,
    season              TEXT,
    worst_day_rank      INTEGER,
    PRIMARY KEY (station_id, date)
);

-- Indices for fast aggregations
CREATE INDEX idx_aqi_month_hour ON kathmandu_aqi(month_num, hour);
CREATE INDEX idx_aqi_date ON kathmandu_aqi(date);
CREATE INDEX idx_daily_pm ON daily_station_summary(daily_pm2_5);
