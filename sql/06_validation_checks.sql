-- 06_validation_checks.sql
--
-- The six checks from brief section 6. Each is a standalone,
-- re-runnable SELECT; its own result is the evidence, not a separate
-- report. Run through etl/audit.py's run_validation_checks(), which
-- saves the real output to logs/validation_<timestamp>.txt and
-- docs/evidence/, rather than by hand, so the saved evidence is
-- exactly what MySQL returned.

USE flight_dw;

-- Check 1: row reconciliation. Source rows = loaded rows + rejected
-- rows, per month. Phase 1's download/extract already confirmed each
-- month's staged row count against its own CSV line count (see
-- docs/walkthrough/phase1.md); this check confirms the next link in
-- the chain, that every staged row became exactly one fact row or one
-- reject, with nothing silently lost in between.
SELECT
    'check1_row_reconciliation' AS check_name,
    (SELECT COUNT(*) FROM stg_bts_flights) AS staged_rows,
    (SELECT COUNT(*) FROM fact_flight) AS fact_rows,
    (SELECT COUNT(*) FROM reject_flights) AS rejected_rows,
    (SELECT COUNT(*) FROM fact_flight) + (SELECT COUNT(*) FROM reject_flights) AS fact_plus_rejected,
    CASE WHEN (SELECT COUNT(*) FROM stg_bts_flights) = (SELECT COUNT(*) FROM fact_flight) + (SELECT COUNT(*) FROM reject_flights)
         THEN 'PASS' ELSE 'FAIL' END AS result;

-- Check 2: orphan keys. Every fact_flight foreign key should resolve to
-- a real row in its dimension (InnoDB's FOREIGN KEY constraints make
-- this structurally impossible to violate; this check demonstrates
-- that directly rather than only trusting the constraint exists).
SELECT 'check2_orphan_keys' AS check_name, 'date_key' AS fk_column,
       COUNT(*) AS orphan_count
FROM fact_flight f LEFT JOIN dim_date d ON d.date_key = f.date_key WHERE d.date_key IS NULL
UNION ALL
SELECT 'check2_orphan_keys', 'dep_time_key', COUNT(*)
FROM fact_flight f LEFT JOIN dim_time_of_day d ON d.time_key = f.dep_time_key WHERE d.time_key IS NULL
UNION ALL
SELECT 'check2_orphan_keys', 'origin_airport_key', COUNT(*)
FROM fact_flight f LEFT JOIN dim_airport d ON d.airport_key = f.origin_airport_key WHERE d.airport_key IS NULL
UNION ALL
SELECT 'check2_orphan_keys', 'dest_airport_key', COUNT(*)
FROM fact_flight f LEFT JOIN dim_airport d ON d.airport_key = f.dest_airport_key WHERE d.airport_key IS NULL
UNION ALL
SELECT 'check2_orphan_keys', 'carrier_key', COUNT(*)
FROM fact_flight f LEFT JOIN dim_carrier d ON d.carrier_key = f.carrier_key WHERE d.carrier_key IS NULL
UNION ALL
SELECT 'check2_orphan_keys', 'route_key', COUNT(*)
FROM fact_flight f LEFT JOIN dim_route d ON d.route_key = f.route_key WHERE d.route_key IS NULL
UNION ALL
SELECT 'check2_orphan_keys', 'flight_status_key', COUNT(*)
FROM fact_flight f LEFT JOIN dim_flight_status d ON d.flight_status_key = f.flight_status_key WHERE d.flight_status_key IS NULL
UNION ALL
SELECT 'check2_orphan_keys', 'origin_weather_key', COUNT(*)
FROM fact_flight f LEFT JOIN dim_weather_condition d ON d.weather_condition_key = f.origin_weather_key WHERE d.weather_condition_key IS NULL
UNION ALL
SELECT 'check2_orphan_keys', 'dest_weather_key', COUNT(*)
FROM fact_flight f LEFT JOIN dim_weather_condition d ON d.weather_condition_key = f.dest_weather_key WHERE d.weather_condition_key IS NULL;

-- Check 3: uniqueness. Zero duplicate business keys in fact_flight
-- (the UNIQUE KEY makes this structurally impossible too; same reason
-- for checking directly as check 2).
SELECT 'check3_uniqueness' AS check_name,
       COUNT(*) AS duplicate_business_key_groups
FROM (
    SELECT date_key, carrier_key, flight_number, origin_airport_key, dest_airport_key, scheduled_dep_time
    FROM fact_flight
    GROUP BY date_key, carrier_key, flight_number, origin_airport_key, dest_airport_key, scheduled_dep_time
    HAVING COUNT(*) > 1
) dupes;

-- Check 4: cause totals. For every non-cancelled flight with an
-- arrival delay of 15 minutes or more, the five delay-cause measures
-- should sum to arr_delay_min. Mismatches are reported, not hidden.
SELECT
    'check4_cause_totals' AS check_name,
    COUNT(*) AS qualifying_rows,
    SUM(CASE WHEN arr_delay_min <> (carrier_delay_min + weather_delay_min + nas_delay_min + security_delay_min + late_aircraft_delay_min)
             THEN 1 ELSE 0 END) AS mismatch_count
FROM fact_flight
WHERE arr_delay_min IS NOT NULL AND arr_delay_min >= 15
  AND carrier_delay_min IS NOT NULL AND weather_delay_min IS NOT NULL
  AND nas_delay_min IS NOT NULL AND security_delay_min IS NOT NULL AND late_aircraft_delay_min IS NOT NULL;

-- Check 5: dimension counts. Distinct source codes should equal real
-- dimension rows (excluding -1) plus however many distinct codes were
-- unmatched (logged to exception_log, not silently dropped).
SELECT 'check5_dimension_counts' AS check_name, 'dim_carrier' AS dim_table,
       (SELECT COUNT(DISTINCT Reporting_Airline) FROM stg_bts_flights) AS distinct_source_codes,
       (SELECT COUNT(*) FROM dim_carrier WHERE carrier_key <> -1) AS dim_rows,
       (SELECT COUNT(DISTINCT natural_key) FROM exception_log WHERE exception_type = 'UNKNOWN_CARRIER_CODE') AS distinct_unmatched_codes
UNION ALL
SELECT 'check5_dimension_counts', 'dim_airport',
       (SELECT COUNT(DISTINCT code) FROM (
            SELECT Origin AS code FROM stg_bts_flights UNION SELECT Dest AS code FROM stg_bts_flights
        ) t),
       (SELECT COUNT(*) FROM dim_airport WHERE airport_key <> -1),
       (SELECT COUNT(DISTINCT natural_key) FROM exception_log WHERE exception_type = 'UNKNOWN_AIRPORT_CODE');

-- Check 6: re-run test. Not a query against a single run: run
-- `python run_all.py` twice and diff the row counts of every table.
-- etl/audit.py's run_validation_checks() records the current counts
-- here each time it runs, so two runs of this file (one per run_all.py
-- execution) can be diffed directly.
SELECT 'check6_rerun_snapshot' AS check_name,
       (SELECT COUNT(*) FROM dim_date) AS dim_date_rows,
       (SELECT COUNT(*) FROM dim_time_of_day) AS dim_time_of_day_rows,
       (SELECT COUNT(*) FROM dim_airport) AS dim_airport_rows,
       (SELECT COUNT(*) FROM dim_carrier) AS dim_carrier_rows,
       (SELECT COUNT(*) FROM dim_route) AS dim_route_rows,
       (SELECT COUNT(*) FROM dim_flight_status) AS dim_flight_status_rows,
       (SELECT COUNT(*) FROM dim_weather_condition) AS dim_weather_condition_rows,
       (SELECT COUNT(*) FROM airport_station_map) AS airport_station_map_rows,
       (SELECT COUNT(*) FROM fact_airport_weather_daily) AS fact_airport_weather_daily_rows,
       (SELECT COUNT(*) FROM fact_flight) AS fact_flight_rows;
