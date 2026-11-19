-- ====================================================================
-- QUERY 1: Station Ranking (for the map and the ranking bar chart)
-- ====================================================================
SELECT
    station_name,
    sensor_type,
    latitude,
    longitude,
    avg_daily_pm2_5,
    avg_aqi,
    avg_category,
    pct_unhealthy_days,
    typical_peak_hour,
    coverage_pct,
    valid_days
FROM stations
ORDER BY avg_daily_pm2_5 DESC;


-- ====================================================================
-- QUERY 2: Top 10 Most Polluted Days in the Valley
-- (average across stations reporting that day) and their peak hour
-- ====================================================================
WITH valley_days AS (
    SELECT
        date,
        ROUND(AVG(daily_pm2_5), 1) AS valley_pm2_5,
        COUNT(*)                   AS stations_reporting,
        MAX(peak_hour_pm2_5)       AS worst_hour_pm2_5
    FROM daily_station_summary
    WHERE daily_pm2_5 IS NOT NULL
    GROUP BY date
)
SELECT
    v.date,
    v.valley_pm2_5,
    v.stations_reporting,
    d.station_name      AS worst_station,
    printf('%02d:00', d.peak_hour) AS worst_hour,
    v.worst_hour_pm2_5
FROM valley_days v
JOIN daily_station_summary d
  ON d.date = v.date AND d.peak_hour_pm2_5 = v.worst_hour_pm2_5
ORDER BY v.valley_pm2_5 DESC
LIMIT 10;


-- ====================================================================
-- QUERY 3: Hour-by-Hour Profile on Very Polluted Days
-- "Very polluted" = days whose daily AQI is above 150 (Unhealthy or worse)
-- ====================================================================
SELECT
    a.station_name,
    a.hour,
    ROUND(AVG(a.pm2_5), 1) AS avg_pm2_5,
    COUNT(DISTINCT a.date) AS polluted_days
FROM kathmandu_aqi a
JOIN daily_station_summary d
  ON d.station_id = a.station_id AND d.date = a.date
WHERE d.daily_aqi > 150
  AND a.is_measured = 1
GROUP BY a.station_name, a.hour
ORDER BY a.station_name, a.hour;


-- ====================================================================
-- QUERY 4: Most Polluted Hour of Every Month (measured readings only)
-- ====================================================================
WITH ranked AS (
    SELECT
        month_num, month_name, date, day_name, hour, station_name, pm2_5, us_aqi,
        ROW_NUMBER() OVER (PARTITION BY month_num ORDER BY pm2_5 DESC) AS rnk
    FROM kathmandu_aqi
    WHERE is_measured = 1
)
SELECT
    month_name,
    date AS peak_date,
    day_name,
    printf('%02d:00', hour) AS peak_hour,
    station_name,
    pm2_5 AS max_pm2_5,
    us_aqi
FROM ranked
WHERE rnk = 1
ORDER BY month_num;


-- ====================================================================
-- QUERY 5: Diurnal Heatmap (Average PM2.5 by Month x Hour, per station)
-- ====================================================================
SELECT
    station_name,
    month_num,
    month_name,
    hour,
    ROUND(AVG(pm2_5), 1) AS avg_pm2_5,
    COUNT(*)             AS sample_count
FROM kathmandu_aqi
WHERE is_measured = 1
GROUP BY station_name, month_num, month_name, hour
ORDER BY station_name, month_num, hour;


-- ====================================================================
-- QUERY 6: Seasonal Comparison by Station
-- ====================================================================
SELECT
    station_name,
    season,
    ROUND(AVG(daily_pm2_5), 1) AS avg_pm2_5,
    ROUND(100.0 * SUM(CASE WHEN daily_aqi > 150 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_unhealthy_days,
    COUNT(*) AS days
FROM daily_station_summary
WHERE daily_pm2_5 IS NOT NULL
GROUP BY station_name, season
ORDER BY station_name,
    CASE season WHEN 'Winter' THEN 1 WHEN 'Pre-monsoon' THEN 2
                WHEN 'Monsoon' THEN 3 ELSE 4 END;


-- ====================================================================
-- QUERY 7: Weekday vs Weekend (Saturday is the weekend in Nepal)
-- ====================================================================
SELECT
    day_type,
    day_name,
    ROUND(AVG(pm2_5), 1) AS avg_pm2_5,
    COUNT(*)             AS hours
FROM kathmandu_aqi
WHERE is_measured = 1
GROUP BY day_type, day_name
ORDER BY avg_pm2_5 DESC;
