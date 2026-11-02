-- ====================================================================
-- QUERY 1: Most Polluted Day & Time of Every Month (Peak Single Hour)
-- ====================================================================
WITH MonthlyRankedAQI AS (
    SELECT 
        month_num,
        month_name,
        date,
        day_name,
        hour,
        station_name,
        us_aqi,
        pm2_5,
        ROW_NUMBER() OVER (
            PARTITION BY month_num 
            ORDER BY us_aqi DESC, pm2_5 DESC
        ) as rank
    FROM raw_aqi_data
)
SELECT 
    month_num,
    month_name,
    date as peak_date,
    day_name,
    printf('%02d:00', hour) as peak_hour,
    station_name,
    us_aqi as max_us_aqi,
    pm2_5 as max_pm2_5
FROM MonthlyRankedAQI
WHERE rank = 1
ORDER BY month_num ASC;


-- ====================================================================
-- QUERY 2: Diurnal Heatmap Data (Average AQI by Month vs. Hour of Day)
-- ====================================================================
SELECT 
    month_num,
    month_name,
    hour,
    ROUND(AVG(us_aqi), 1) as avg_us_aqi,
    ROUND(AVG(pm2_5), 1) as avg_pm2_5,
    COUNT(*) as sample_count
FROM raw_aqi_data
GROUP BY month_num, month_name, hour
ORDER BY month_num ASC, hour ASC;


-- ====================================================================
-- QUERY 3: Station Area Ranking & Spatial Heatmap Baseline
-- ====================================================================
SELECT 
    station_name,
    ROUND(AVG(us_aqi), 1) as overall_avg_aqi,
    MAX(us_aqi) as max_recorded_aqi,
    ROUND(AVG(pm2_5), 1) as avg_pm2_5,
    SUM(CASE WHEN us_aqi > 150 THEN 1 ELSE 0 END) as unhealthy_hours_count,
    ROUND(100.0 * SUM(CASE WHEN us_aqi > 150 THEN 1 ELSE 0 END) / COUNT(*), 2) as pct_unhealthy_hours
FROM raw_aqi_data
GROUP BY station_name
ORDER BY overall_avg_aqi DESC;


-- ====================================================================
-- QUERY 4: Day of the Week Comparison (Weekday vs Weekend Traffic)
-- ====================================================================
SELECT 
    day_name,
    CASE 
        WHEN day_name = 'Saturday' THEN 'Weekend'
        ELSE 'Weekday'
    END as day_type,
    ROUND(AVG(us_aqi), 1) as avg_us_aqi,
    ROUND(AVG(pm2_5), 1) as avg_pm2_5
FROM raw_aqi_data
GROUP BY day_name
ORDER BY avg_us_aqi DESC;