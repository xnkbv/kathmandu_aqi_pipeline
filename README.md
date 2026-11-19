# Kathmandu Valley Air Quality Analysis

How polluted is Kathmandu really, where is it worst, and when?

This project collects hourly PM2.5 data from 50+ air quality monitoring stations across Kathmandu Valley, cleans it with Python and SQL, and visualises it in a three-page Power BI dashboard.

---

## Dashboard

### 1. Which area is worst?
![Which area is worst](05_assets/screenshots/Which%20area%20is%20worst.png)

### 2. When is it worst?
![When is it worst](05_assets/screenshots/when%20is%20it%20worst.png)

### 3. Is it getting worse?
![Is it getting worse](05_assets/screenshots/is%20it%20getting%20worse.png)

---

## Key findings

**Where** (42 stations, October 2025 – November 2026)
- The valley averages around **50 µg/m³ of PM2.5**, about **10 times** the WHO annual guideline of 5 µg/m³
- On more than **1 in 3 days**, the air is "Unhealthy" (AQI above 150)
- The most polluted areas are **Sifal, Sanepa, Kadhaghari, Tarakeswor and Gaushala Chowk**
- Almost every station is orange or red. Pollution is valley-wide, not limited to a few neighbourhoods

**When**
- Air is worst around **8 AM** (~73 µg/m³), with a second peak around **9 PM** (~60)
- The cleanest time of day is **1–3 PM** (~34), roughly half the morning level
- The worst day was **23 April 2026** (~175 µg/m³). Most of the 10 worst days fall in **January, March and April**
- **January–February** are the worst months (~90 µg/m³). **July–August** are the cleanest (~15), when monsoon rain clears the air

**Over time** (US Embassy reference monitor, Maharajgunj, 2023–2026)
- The same pattern repeats every year: high in winter, worst in April, clean in the monsoon
- April peaks reached ~120 µg/m³ in 2023 and ~100 in 2024
- Winters stay around 60–80 µg/m³ year after year
- There is no clear improvement yet. Early 2026 looks slightly lower, but it is too soon to call a trend

---

## Data

| Source | What it provides |
|---|---|
| [OpenAQ](https://explore.openaq.org) (API v3) | Hourly PM2.5 / PM10 with station coordinates: 2 reference monitors (US Embassy, via AirNow) and ~50 low-cost AirGradient sensors |
| [AirNow](https://www.airnow.gov/international/us-embassies-and-consulates/) (optional) | US Embassy hourly CSVs, placed in `01_data/raw/airnow/` |

An earlier version of this project used Open-Meteo, a modelled dataset with ~40 km grid cells. Every station in the valley fell into the same grid cell and received identical values, so it could not show differences between areas. It was replaced with measured station data.

---

## Pipeline

```
OpenAQ API ──► scrape_aqi.py ──► pipeline.py ──► run_sql.py ──► Power BI
               (raw hourly)      (clean + enrich)  (SQLite + queries)
```

**Cleaning rules (`pipeline.py`)**
- Every reading is aligned to a whole hour in Nepal time (UTC+05:45)
- Removed as invalid: negative values, PM2.5 above 1000 µg/m³, and stuck sensors (the same value for 6+ hours)
- Gaps of up to 3 hours are interpolated within each station; longer gaps stay empty
- US AQI is calculated with the EPA method (2024 PM2.5 breakpoints) from 24-hour averages
- Daily averages require at least 18 measured hours
- Data coverage is tracked for every station, and the dashboard only uses stations with at least 40% coverage

**Outputs (`01_data/processed/`)**

| File | Grain | Used for |
|---|---|---|
| `stations.csv` | 1 row per station | Map, station ranking, coverage |
| `daily_station_summary.csv` | station × day | Worst days, monthly and yearly trends |
| `kathmandu_aqi_clean.csv` | station × hour | Hour-of-day patterns |
| `pm25_heatmap_grid.csv` | ~400 m grid | Estimated PM2.5 surface across the valley (inverse-distance weighting) |

---

## How to run

```bash
pip install pandas requests

# Free API key from https://explore.openaq.org
# Paste it into openaq_api_key.txt in the project root (git-ignored)

python 03_scripts/scrape_aqi.py          # download station data
python 03_scripts/pipeline.py            # clean and build the Power BI tables
python 03_scripts/run_sql.py             # load SQLite and run the analysis queries
```

`python 03_scripts/scrape_aqi.py --list` shows every station available in the valley without downloading any data.

Open `04_powerbi/kathmandu_aqi.pbix` in Power BI Desktop and refresh to load the latest data.

---

## Limitations

- Most stations are low-cost sensors, which can read 20–30% differently from reference monitors. Treat values as good estimates, not official readings
- The low-cost network only started in late 2025, so station comparisons cover October 2025 – November 2026. Long-term trends rely on the US Embassy monitor, which has some months missing
- Government monitoring stations (e.g. Ratnapark, Pulchowk) are not available on OpenAQ and are not included

---

## Project structure

```
01_data/        raw and processed data (SQLite database is rebuilt, not committed)
02_sql/         schema.sql, analytical_queries.sql
03_scripts/     scrape_aqi.py, pipeline.py, run_sql.py
04_powerbi/     kathmandu_aqi.pbix
05_assets/      dashboard screenshots
```

**Tools:** Python (pandas, requests), SQLite, Power BI
