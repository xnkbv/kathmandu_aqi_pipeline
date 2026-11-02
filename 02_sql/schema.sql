-- Schema for Kathmandu AQI Analysis Pipeline
DROP TABLE IF EXISTS kathmandu_aqi;

CREATE TABLE kathmandu_aqi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    station_name TEXT NOT NULL,
    datetime TEXT NOT NULL,
    date DATE NOT NULL,
    year INTEGER NOT NULL,
    month_num INTEGER NOT NULL,
    month_name TEXT NOT NULL,
    hour INTEGER NOT NULL,
    day_name TEXT NOT NULL,
    pm2_5 REAL,
    pm10 REAL,
    us_aqi INTEGER,
    aqi_category TEXT
);

-- Indices for fast aggregations in Power BI and SQL
CREATE INDEX idx_station_datetime ON kathmandu_aqi(station_name, datetime);
CREATE INDEX idx_month_hour ON kathmandu_aqi(month_num, hour);
CREATE INDEX idx_aqi ON kathmandu_aqi(us_aqi);