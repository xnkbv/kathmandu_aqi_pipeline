# Kathmandu AQI Pipeline

Spatio-temporal analysis of air quality across the Kathmandu Valley: **which
areas are most polluted** (station map) and **which hours are worst on the most
polluted days**. Uses measured station data, pandas, SQLite and Power BI.

## Data sources

| Source | What it gives | How it's collected |
|---|---|---|
| [OpenAQ](https://explore.openaq.org) (v3 API) | Hourly PM2.5 / PM10 from reference monitors in the valley (Dept. of Environment, Nepal and others), with coordinates | `03_scripts/scrape_aqi.py` |
| [AirNow](https://www.airnow.gov/international/us-embassies-and-consulates/) – US Embassy Kathmandu | Hourly PM2.5 from the embassy monitor (optional, high quality) | Download the yearly CSVs manually into `01_data/raw/airnow/` |

Earlier versions used Open-Meteo, a modelled dataset with ~40 km grid cells.
Every station in the valley fell into the same cell and got identical values,
so it could not show differences between locations. It has been replaced with
measured data.

## How to run

```bash
pip install pandas requests

# 1. Free API key from https://explore.openaq.org, then either:
#    set OPENAQ_API_KEY=your_key          (Windows cmd)
#    $env:OPENAQ_API_KEY="your_key"       (PowerShell)
#    or paste it into openaq_api_key.txt in the project root (git-ignored)

python 03_scripts/scrape_aqi.py   # download station data   -> 01_data/raw/
python 03_scripts/pipeline.py     # clean + enrich          -> 01_data/processed/
python 03_scripts/run_sql.py      # load SQLite + run queries
```

Set `INCLUDE_LOW_COST=1` before running the scraper to also include low-cost
sensors (they are labelled `sensor_type = low-cost`; they tend to read higher
than reference monitors).

## Cleaning rules (`pipeline.py`)

- Every station gets a row for every hour, so gaps are visible.
- Removed as invalid: negative values, PM2.5 > 1000 µg/m³, and stuck sensors
  (same value 6+ hours in a row).
- Gaps of up to 3 hours are interpolated **within each station** (`is_imputed = 1`);
  longer gaps stay empty.
- **US AQI** is computed with the EPA method (2024 PM2.5 breakpoints) from 24-hour
  rolling means, requiring at least 18 measured hours.
- Daily averages need at least 18 measured hours; otherwise the day is left empty.
- Two stations closer than 300 m (e.g. the embassy monitor from both OpenAQ and
  AirNow) are merged, keeping the one with more data.
- Times are converted to Nepal time (UTC+05:45). Saturday = weekend.

## Outputs for Power BI (`01_data/processed/`)

| File | Grain | Use it for |
|---|---|---|
| `stations.csv` | 1 row per station | Map (latitude/longitude), station ranking, data coverage |
| `daily_station_summary.csv` | station × day | Worst days, daily AQI calendar, peak hour of each day |
| `kathmandu_aqi_clean.csv` | station × hour | Hourly profiles, month × hour heatmap |

Relate all three on `station_id` (stations = one side), and the hourly and daily
tables on `station_id` + `date`.

**Tip:** use `pm2_5` (hourly) for hour-by-hour visuals. `us_aqi` is a 24-hour
average and smooths out the daily peak.

## Project structure

```
01_data/        raw + processed data, SQLite database
02_sql/         schema.sql, analytical_queries.sql
03_scripts/     scrape_aqi.py, pipeline.py, run_sql.py
04_powerbi/     Power BI report
05_assets/      screenshots
```
