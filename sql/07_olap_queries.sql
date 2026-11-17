-- 07_olap_queries.sql
--
-- Phase 6: the six business questions from brief section 8, plus the
-- five reporting views behind the five dashboard pages (overview KPIs,
-- routes and carriers, delay causes, weather impact, time patterns).
-- Every query here is read-only and re-runnable against the warehouse
-- built by Phases 3-5; nothing here writes to a table.
--
-- Non-cancelled / on-time definitions follow CLAUDE.md exactly:
--   on-time rate = on_time_flag=TRUE / non-cancelled flights
--   cancellation rate = cancelled / all scheduled flights
--   weather delay share = SUM(weather) / SUM(all five causes)
--   late-aircraft share = SUM(late_aircraft) / SUM(all five causes)
--   plain means (arr delay, dep delay, taxi-out) over non-cancelled flights
--
-- The -1 Unknown row of every joined dimension is excluded from grouping
-- keys with "<> -1" guards, the same pattern used in sql/06 and
-- etl/load_facts.py, so Unknown doesn't show up as a spurious category
-- in business-facing output.

USE flight_dw;

-- ---------------------------------------------------------------------
-- Q1: worst routes and carriers. Top 10 routes by lowest on-time rate
-- with a minimum flight-count floor (avoids small-sample routes flown
-- a handful of times), ranked with DENSE_RANK. Q1b slices the same
-- idea by carrier so the dashboard can show which carrier drives a
-- route's bad number.
-- ---------------------------------------------------------------------

-- Q1a: worst 10 routes overall
WITH route_stats AS (
    SELECT
        r.route_key, r.origin_iata, r.dest_iata, r.distance_band,
        COUNT(*) AS flight_count,
        SUM(CASE WHEN fs.cancelled_flag = FALSE THEN 1 ELSE 0 END) AS non_cancelled_count,
        SUM(CASE WHEN f.on_time_flag = TRUE THEN 1 ELSE 0 END) AS on_time_count
    FROM fact_flight f
    JOIN dim_route r ON r.route_key = f.route_key AND r.route_key <> -1
    JOIN dim_flight_status fs ON fs.flight_status_key = f.flight_status_key
    GROUP BY r.route_key, r.origin_iata, r.dest_iata, r.distance_band
),
route_ranked AS (
    SELECT
        origin_iata, dest_iata, distance_band, flight_count, non_cancelled_count, on_time_count,
        on_time_count / non_cancelled_count AS on_time_rate,
        DENSE_RANK() OVER (ORDER BY on_time_count / non_cancelled_count ASC) AS worst_rank
    FROM route_stats
    WHERE flight_count >= 500 AND non_cancelled_count > 0
)
SELECT * FROM route_ranked WHERE worst_rank <= 10 ORDER BY worst_rank, origin_iata, dest_iata;

-- Q1b: per-carrier on-time rate on those same worst 10 routes
WITH route_stats AS (
    SELECT
        r.route_key,
        COUNT(*) AS flight_count,
        SUM(CASE WHEN fs.cancelled_flag = FALSE THEN 1 ELSE 0 END) AS non_cancelled_count,
        SUM(CASE WHEN f.on_time_flag = TRUE THEN 1 ELSE 0 END) AS on_time_count
    FROM fact_flight f
    JOIN dim_route r ON r.route_key = f.route_key AND r.route_key <> -1
    JOIN dim_flight_status fs ON fs.flight_status_key = f.flight_status_key
    GROUP BY r.route_key
),
worst_10_routes AS (
    SELECT route_key FROM route_stats
    WHERE flight_count >= 500 AND non_cancelled_count > 0
    ORDER BY on_time_count / non_cancelled_count ASC
    LIMIT 10
)
SELECT
    r.origin_iata, r.dest_iata, c.carrier_code,
    COUNT(*) AS flight_count,
    SUM(CASE WHEN fs.cancelled_flag = FALSE THEN 1 ELSE 0 END) AS non_cancelled_count,
    SUM(CASE WHEN f.on_time_flag = TRUE THEN 1 ELSE 0 END) / SUM(CASE WHEN fs.cancelled_flag = FALSE THEN 1 ELSE 0 END) AS on_time_rate
FROM fact_flight f
JOIN worst_10_routes w10 ON w10.route_key = f.route_key
JOIN dim_route r ON r.route_key = f.route_key
JOIN dim_carrier c ON c.carrier_key = f.carrier_key AND c.carrier_key <> -1
JOIN dim_flight_status fs ON fs.flight_status_key = f.flight_status_key
GROUP BY r.origin_iata, r.dest_iata, c.carrier_code
HAVING non_cancelled_count >= 20
ORDER BY r.origin_iata, r.dest_iata, on_time_rate ASC;

-- ---------------------------------------------------------------------
-- Q2: delay causes. Minutes by cause per month, rolled up month to
-- quarter to year with GROUP BY ... WITH ROLLUP. Only rows where the
-- cause breakdown exists (non-cancelled, arr_delay_min >= 15, see
-- hard rule 4's cause-NULL convention in etl/clean.py) are included,
-- since cancelled and on-time rows have no cause minutes to sum.
-- ---------------------------------------------------------------------

SELECT
    d.year, d.quarter, d.month_num,
    SUM(f.carrier_delay_min) AS carrier_delay_min,
    SUM(f.weather_delay_min) AS weather_delay_min,
    SUM(f.nas_delay_min) AS nas_delay_min,
    SUM(f.security_delay_min) AS security_delay_min,
    SUM(f.late_aircraft_delay_min) AS late_aircraft_delay_min,
    SUM(f.carrier_delay_min + f.weather_delay_min + f.nas_delay_min + f.security_delay_min + f.late_aircraft_delay_min) AS total_delay_min
FROM fact_flight f
JOIN dim_date d ON d.date_key = f.date_key AND d.date_key <> -1
WHERE f.carrier_delay_min IS NOT NULL
GROUP BY d.year, d.quarter, d.month_num WITH ROLLUP;

-- ---------------------------------------------------------------------
-- Q3: weather impact. Average arrival delay and cancellation rate by
-- precipitation, snow and wind band at the origin airport (brief's
-- exact slice: temp_band exists in dim_weather_condition but is not
-- part of this particular question).
-- ---------------------------------------------------------------------

SELECT
    w.precip_band, w.snow_band, w.wind_band,
    COUNT(*) AS flight_count,
    SUM(CASE WHEN fs.cancelled_flag = TRUE THEN 1 ELSE 0 END) / COUNT(*) AS cancellation_rate,
    AVG(CASE WHEN fs.cancelled_flag = FALSE THEN f.arr_delay_min END) AS avg_arr_delay_min
FROM fact_flight f
JOIN dim_weather_condition w ON w.weather_condition_key = f.origin_weather_key
JOIN dim_flight_status fs ON fs.flight_status_key = f.flight_status_key
GROUP BY w.precip_band, w.snow_band, w.wind_band
ORDER BY avg_arr_delay_min DESC;

-- ---------------------------------------------------------------------
-- Q4: riskiest airports and times. Q4a is the airport x departure-band
-- on-time-rate matrix (heat map), limited to the 20 busiest origin
-- airports so the matrix stays readable. Q4b is the GROUP BY WITH
-- ROLLUP drill-down from year down to weekday.
-- ---------------------------------------------------------------------

-- Q4a: airport x departure-band on-time rate matrix, busiest 20 airports
WITH busiest_20 AS (
    SELECT origin_airport_key FROM fact_flight
    WHERE origin_airport_key <> -1
    GROUP BY origin_airport_key
    ORDER BY COUNT(*) DESC
    LIMIT 20
)
SELECT
    a.iata_code AS airport,
    t.departure_band,
    COUNT(*) AS flight_count,
    SUM(CASE WHEN f.on_time_flag = TRUE THEN 1 ELSE 0 END) / SUM(CASE WHEN fs.cancelled_flag = FALSE THEN 1 ELSE 0 END) AS on_time_rate
FROM fact_flight f
JOIN busiest_20 b ON b.origin_airport_key = f.origin_airport_key
JOIN dim_airport a ON a.airport_key = f.origin_airport_key
JOIN dim_time_of_day t ON t.time_key = f.dep_time_key AND t.time_key <> -1
JOIN dim_flight_status fs ON fs.flight_status_key = f.flight_status_key
GROUP BY a.iata_code, t.departure_band
ORDER BY airport, departure_band;

-- Q4b: on-time rate rollup, year -> quarter -> month -> day of week
SELECT
    d.year, d.quarter, d.month_num, d.day_of_week_name,
    COUNT(*) AS flight_count,
    SUM(CASE WHEN f.on_time_flag = TRUE THEN 1 ELSE 0 END) / SUM(CASE WHEN fs.cancelled_flag = FALSE THEN 1 ELSE 0 END) AS on_time_rate
FROM fact_flight f
JOIN dim_date d ON d.date_key = f.date_key AND d.date_key <> -1
JOIN dim_flight_status fs ON fs.flight_status_key = f.flight_status_key
GROUP BY d.year, d.quarter, d.month_num, d.day_of_week_name WITH ROLLUP;

-- ---------------------------------------------------------------------
-- Q5: delay propagation. Late-aircraft delay share by hour of day, for
-- the 10 busiest origin airports (dicing by airport and time band).
-- ---------------------------------------------------------------------

WITH busiest_10 AS (
    SELECT origin_airport_key FROM fact_flight
    WHERE origin_airport_key <> -1
    GROUP BY origin_airport_key
    ORDER BY COUNT(*) DESC
    LIMIT 10
)
SELECT
    a.iata_code AS airport,
    t.hour_of_day,
    SUM(f.late_aircraft_delay_min) AS late_aircraft_delay_min,
    SUM(f.carrier_delay_min + f.weather_delay_min + f.nas_delay_min + f.security_delay_min + f.late_aircraft_delay_min) AS total_cause_delay_min,
    SUM(f.late_aircraft_delay_min) / SUM(f.carrier_delay_min + f.weather_delay_min + f.nas_delay_min + f.security_delay_min + f.late_aircraft_delay_min) AS late_aircraft_share
FROM fact_flight f
JOIN busiest_10 b ON b.origin_airport_key = f.origin_airport_key
JOIN dim_airport a ON a.airport_key = f.origin_airport_key
JOIN dim_time_of_day t ON t.time_key = f.dep_time_key AND t.time_key <> -1
WHERE f.carrier_delay_min IS NOT NULL
GROUP BY a.iata_code, t.hour_of_day
ORDER BY airport, hour_of_day;

-- ---------------------------------------------------------------------
-- Q6: carrier comparison. Each carrier's average arrival delay minus
-- the route's own average, restricted to routes flown by 2 or more
-- carriers, using AVG() OVER (PARTITION BY route). The carrier count
-- per route is computed first with a plain GROUP BY (MySQL 8 does not
-- allow COUNT(DISTINCT ...) as a window function), then only that
-- smaller multi-carrier set is carried into the window computation.
-- ---------------------------------------------------------------------

WITH route_carrier_list AS (
    SELECT DISTINCT route_key, carrier_key
    FROM fact_flight
    WHERE route_key <> -1 AND carrier_key <> -1
),
multi_carrier_routes AS (
    SELECT route_key FROM route_carrier_list
    GROUP BY route_key
    HAVING COUNT(*) >= 2
),
flight_avgs AS (
    SELECT
        f.route_key, f.carrier_key,
        AVG(f.arr_delay_min) OVER (PARTITION BY f.route_key, f.carrier_key) AS carrier_avg_delay,
        AVG(f.arr_delay_min) OVER (PARTITION BY f.route_key) AS route_avg_delay,
        COUNT(*) OVER (PARTITION BY f.route_key, f.carrier_key) AS carrier_flight_count
    FROM fact_flight f
    JOIN dim_flight_status fs ON fs.flight_status_key = f.flight_status_key
    JOIN multi_carrier_routes mcr ON mcr.route_key = f.route_key
    WHERE fs.cancelled_flag = FALSE
)
SELECT DISTINCT
    r.origin_iata, r.dest_iata, c.carrier_code,
    fa.carrier_flight_count, fa.carrier_avg_delay, fa.route_avg_delay,
    fa.carrier_avg_delay - fa.route_avg_delay AS delay_vs_route_avg
FROM flight_avgs fa
JOIN dim_route r ON r.route_key = fa.route_key
JOIN dim_carrier c ON c.carrier_key = fa.carrier_key
WHERE fa.carrier_flight_count >= 20
ORDER BY delay_vs_route_avg DESC;

-- ---------------------------------------------------------------------
-- Reporting views: one per dashboard page. Each is the clean,
-- pre-aggregated source a BI tool (or the CSV fallback) reads from
-- directly, so the dashboard never has to re-derive a KPI definition.
-- ---------------------------------------------------------------------

-- Page 1: overview KPIs, one row per month
CREATE OR REPLACE VIEW vw_kpi_overview AS
SELECT
    d.year, d.month_num, d.month_name,
    COUNT(*) AS total_flights,
    SUM(CASE WHEN fs.cancelled_flag = TRUE THEN 1 ELSE 0 END) AS cancelled_flights,
    SUM(CASE WHEN fs.diverted_flag = TRUE THEN 1 ELSE 0 END) AS diverted_flights,
    SUM(CASE WHEN fs.cancelled_flag = FALSE THEN 1 ELSE 0 END) AS non_cancelled_flights,
    SUM(CASE WHEN f.on_time_flag = TRUE THEN 1 ELSE 0 END) AS on_time_flights,
    SUM(CASE WHEN f.on_time_flag = TRUE THEN 1 ELSE 0 END) / SUM(CASE WHEN fs.cancelled_flag = FALSE THEN 1 ELSE 0 END) AS on_time_rate,
    SUM(CASE WHEN fs.cancelled_flag = TRUE THEN 1 ELSE 0 END) / COUNT(*) AS cancellation_rate,
    AVG(CASE WHEN fs.cancelled_flag = FALSE THEN f.arr_delay_min END) AS avg_arr_delay_min,
    AVG(CASE WHEN fs.cancelled_flag = FALSE THEN f.dep_delay_min END) AS avg_dep_delay_min,
    AVG(CASE WHEN fs.cancelled_flag = FALSE THEN f.taxi_out_min END) AS avg_taxi_out_min,
    SUM(f.weather_delay_min) / SUM(f.carrier_delay_min + f.weather_delay_min + f.nas_delay_min + f.security_delay_min + f.late_aircraft_delay_min) AS weather_delay_share,
    SUM(f.late_aircraft_delay_min) / SUM(f.carrier_delay_min + f.weather_delay_min + f.nas_delay_min + f.security_delay_min + f.late_aircraft_delay_min) AS late_aircraft_share
FROM fact_flight f
JOIN dim_date d ON d.date_key = f.date_key AND d.date_key <> -1
JOIN dim_flight_status fs ON fs.flight_status_key = f.flight_status_key
GROUP BY d.year, d.month_num, d.month_name;

-- Page 2: routes and carriers
CREATE OR REPLACE VIEW vw_routes_carriers AS
SELECT
    r.origin_iata, r.dest_iata, r.distance_miles, r.distance_band,
    c.carrier_code,
    COUNT(*) AS flight_count,
    SUM(CASE WHEN fs.cancelled_flag = TRUE THEN 1 ELSE 0 END) / COUNT(*) AS cancellation_rate,
    SUM(CASE WHEN f.on_time_flag = TRUE THEN 1 ELSE 0 END) / SUM(CASE WHEN fs.cancelled_flag = FALSE THEN 1 ELSE 0 END) AS on_time_rate,
    AVG(CASE WHEN fs.cancelled_flag = FALSE THEN f.arr_delay_min END) AS avg_arr_delay_min
FROM fact_flight f
JOIN dim_route r ON r.route_key = f.route_key AND r.route_key <> -1
JOIN dim_carrier c ON c.carrier_key = f.carrier_key AND c.carrier_key <> -1
JOIN dim_flight_status fs ON fs.flight_status_key = f.flight_status_key
GROUP BY r.origin_iata, r.dest_iata, r.distance_miles, r.distance_band, c.carrier_code;

-- Page 3: delay causes, one row per month
CREATE OR REPLACE VIEW vw_delay_causes AS
SELECT
    d.year, d.month_num, d.month_name,
    SUM(f.carrier_delay_min) AS carrier_delay_min,
    SUM(f.weather_delay_min) AS weather_delay_min,
    SUM(f.nas_delay_min) AS nas_delay_min,
    SUM(f.security_delay_min) AS security_delay_min,
    SUM(f.late_aircraft_delay_min) AS late_aircraft_delay_min,
    SUM(f.carrier_delay_min + f.weather_delay_min + f.nas_delay_min + f.security_delay_min + f.late_aircraft_delay_min) AS total_delay_min
FROM fact_flight f
JOIN dim_date d ON d.date_key = f.date_key AND d.date_key <> -1
WHERE f.carrier_delay_min IS NOT NULL
GROUP BY d.year, d.month_num, d.month_name;

-- Page 4: weather impact
CREATE OR REPLACE VIEW vw_weather_impact AS
SELECT
    w.precip_band, w.snow_band, w.wind_band, w.temp_band,
    COUNT(*) AS flight_count,
    SUM(CASE WHEN fs.cancelled_flag = TRUE THEN 1 ELSE 0 END) / COUNT(*) AS cancellation_rate,
    AVG(CASE WHEN fs.cancelled_flag = FALSE THEN f.arr_delay_min END) AS avg_arr_delay_min
FROM fact_flight f
JOIN dim_weather_condition w ON w.weather_condition_key = f.origin_weather_key
JOIN dim_flight_status fs ON fs.flight_status_key = f.flight_status_key
GROUP BY w.precip_band, w.snow_band, w.wind_band, w.temp_band;

-- Page 5: time patterns
CREATE OR REPLACE VIEW vw_time_patterns AS
SELECT
    a.iata_code AS airport,
    t.departure_band, t.hour_of_day, d.day_of_week_name,
    COUNT(*) AS flight_count,
    SUM(CASE WHEN f.on_time_flag = TRUE THEN 1 ELSE 0 END) / SUM(CASE WHEN fs.cancelled_flag = FALSE THEN 1 ELSE 0 END) AS on_time_rate,
    SUM(f.late_aircraft_delay_min) / SUM(f.carrier_delay_min + f.weather_delay_min + f.nas_delay_min + f.security_delay_min + f.late_aircraft_delay_min) AS late_aircraft_share
FROM fact_flight f
JOIN dim_airport a ON a.airport_key = f.origin_airport_key AND a.airport_key <> -1
JOIN dim_time_of_day t ON t.time_key = f.dep_time_key AND t.time_key <> -1
JOIN dim_date d ON d.date_key = f.date_key AND d.date_key <> -1
JOIN dim_flight_status fs ON fs.flight_status_key = f.flight_status_key
GROUP BY a.iata_code, t.departure_band, t.hour_of_day, d.day_of_week_name;
