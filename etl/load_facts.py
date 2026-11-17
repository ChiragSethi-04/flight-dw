"""Loads the two fact tables, in the brief's locked order: weather
first (fact_flight needs its weather band), then flights.
"""
import sys
import uuid
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy.engine import Engine

from etl.conform import build_station_daily_weather
from etl.db import get_engine

# (natural_key_column, dim_table, dim_key_column, dim_natural_column, exception_type)
UNMATCHED_CODE_CHECKS = [
    ("Origin", "dim_airport", "airport_key", "iata_code", "UNKNOWN_AIRPORT_CODE"),
    ("Dest", "dim_airport", "airport_key", "iata_code", "UNKNOWN_AIRPORT_CODE"),
    ("Reporting_Airline", "dim_carrier", "carrier_key", "carrier_code", "UNKNOWN_CARRIER_CODE"),
]


def log_exceptions(engine: Engine, load_id: str) -> int:
    """Brief section 4, problem 4: a code with no match gets the Unknown
    member AND is written to an exception report, never just silently
    resolved. One row per distinct unmatched code (not per flight row),
    with the affected row count in the detail, since what matters here
    is which codes are missing, not a repeat per occurrence.

    Groups each column down to its few hundred distinct values first,
    then compares that small set in Python, the same fix Phase 2's
    stalled NOT IN query and Phase 4's territory investigation both
    needed: a LEFT JOIN ... WHERE IS NULL directly against 7 million
    rows is the anti-pattern to avoid here, not a hypothetical one.
    """
    total = 0
    with engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM exception_log WHERE load_id = %s", (load_id,))
        for source_col, dim_table, dim_key, dim_col, exc_type in UNMATCHED_CODE_CHECKS:
            code_counts = conn.exec_driver_sql(
                f"SELECT {source_col}, COUNT(*) AS n FROM stg_bts_flights GROUP BY {source_col}"
            ).fetchall()
            known_codes = {
                row[0] for row in conn.exec_driver_sql(f"SELECT {dim_col} FROM {dim_table} WHERE {dim_key} <> -1")
            }
            for code, n in code_counts:
                if code in known_codes:
                    continue
                conn.exec_driver_sql(
                    """
                    INSERT INTO exception_log (load_id, source_table, natural_key, exception_type, detail, logged_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        load_id, "stg_bts_flights", code, exc_type,
                        f"{n} flight row(s) reference this code; resolved to the Unknown member (-1)",
                        datetime.now(timezone.utc),
                    ),
                )
                total += 1
    log(f"exception_log: {total} distinct unmatched code(s) logged")
    return total


def log(msg: str) -> None:
    print(msg, flush=True)


def load_fact_airport_weather_daily(engine: Engine) -> int:
    daily = build_station_daily_weather(engine)
    with engine.connect() as conn:
        station_map = pd.read_sql(
            "SELECT airport_key, station_id, distance_km AS station_distance_km FROM airport_station_map",
            conn,
        )
        weather_cond = pd.read_sql(
            "SELECT weather_condition_key, precip_band, snow_band, wind_band, temp_band "
            "FROM dim_weather_condition WHERE weather_condition_key <> -1",
            conn,
        )

    merged = daily.merge(station_map, on="station_id", how="inner")
    merged = merged.merge(weather_cond, on=["precip_band", "snow_band", "wind_band", "temp_band"], how="left")
    merged["weather_condition_key"] = merged["weather_condition_key"].fillna(-1).astype(int)
    merged["date_key"] = merged["obs_date"].astype(int)

    rows = merged[
        [
            "date_key", "airport_key", "weather_condition_key",
            "precip_mm", "snowfall_mm", "snow_depth_mm", "avg_wind_ms", "tmax_c", "tmin_c",
            "station_distance_km",
        ]
    ].drop_duplicates(subset=["date_key", "airport_key"])

    with engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM fact_airport_weather_daily")
        rows.to_sql("fact_airport_weather_daily", conn, if_exists="append", index=False, chunksize=10_000)
    log(f"fact_airport_weather_daily: {len(rows)} rows")
    return len(rows)


def _cause_case_sql(column: str) -> str:
    """Mirrors etl.clean.cause_minutes exactly: NULL for cancelled,
    0 for non-cancelled with arr_delay < 15, cast through otherwise.
    """
    return f"""CASE
        WHEN b.cancelled_flag THEN NULL
        WHEN b.arr_delay_val IS NOT NULL AND b.arr_delay_val < 15 THEN 0
        WHEN b.{column} = '' THEN NULL
        ELSE CAST(b.{column} AS DECIMAL(10,2))
    END"""


FACT_FLIGHT_INSERT_SQL = f"""
INSERT INTO fact_flight (
    date_key, dep_time_key, origin_airport_key, dest_airport_key, carrier_key, route_key,
    flight_status_key, origin_weather_key, dest_weather_key, flight_number, tail_number,
    scheduled_dep_time, dep_delay_min, arr_delay_min, carrier_delay_min, weather_delay_min,
    nas_delay_min, security_delay_min, late_aircraft_delay_min, taxi_out_min, taxi_in_min,
    distance_miles, flight_count, on_time_flag, is_outlier_delay
)
WITH base AS (
    SELECT
        s.FlightDate, s.Reporting_Airline, s.Origin, s.Dest, s.CRSDepTime,
        s.Flight_Number_Reporting_Airline AS flight_number, s.Tail_Number AS tail_number,
        s.DepDelay, s.ArrDelay, s.CarrierDelay, s.WeatherDelay, s.NASDelay,
        s.SecurityDelay, s.LateAircraftDelay, s.TaxiOut, s.TaxiIn, s.Distance,
        s.CancellationCode,
        (s.Cancelled = '1.00') AS cancelled_flag,
        (s.Diverted = '1.00') AS diverted_flag,
        NULLIF(TRIM(s.CancellationCode), '') AS cancellation_reason_code,
        CAST(REPLACE(s.FlightDate, '-', '') AS UNSIGNED) AS flight_date_key,
        CAST(s.FlightDate AS DATE) AS flight_date_d,
        CASE WHEN s.ArrDelay = '' THEN NULL ELSE CAST(s.ArrDelay AS DECIMAL(10,2)) END AS arr_delay_val,
        CASE WHEN s.CRSDepTime = '2400' THEN 0 ELSE CAST(s.CRSDepTime AS UNSIGNED) END AS sched_dep_time_val
    FROM stg_bts_flights s
),
base2 AS (
    SELECT b.*,
        CASE
            WHEN b.cancelled_flag THEN 'cancelled'
            WHEN b.diverted_flag THEN 'diverted'
            WHEN b.arr_delay_val IS NULL THEN 'Unknown'
            WHEN b.arr_delay_val < 15 THEN 'on_time'
            WHEN b.arr_delay_val <= 180 THEN 'minor_delay'
            ELSE 'major_delay'
        END AS computed_delay_class
    FROM base b
),
resolved AS (
    SELECT b.*,
        COALESCE(oa.airport_key, -1) AS resolved_origin_airport_key,
        COALESCE(da.airport_key, -1) AS resolved_dest_airport_key,
        COALESCE(dc.carrier_key, -1) AS resolved_carrier_key,
        COALESCE(dr.route_key, -1) AS resolved_route_key,
        COALESCE(dfs.flight_status_key, -1) AS resolved_flight_status_key
    FROM base2 b
    LEFT JOIN dim_airport oa ON oa.iata_code = b.Origin AND oa.airport_key <> -1
    LEFT JOIN dim_airport da ON da.iata_code = b.Dest AND da.airport_key <> -1
    LEFT JOIN dim_carrier dc ON dc.carrier_code = b.Reporting_Airline
        AND dc.carrier_key <> -1
        AND b.flight_date_d >= dc.effective_from
        AND (dc.effective_to IS NULL OR b.flight_date_d <= dc.effective_to)
    LEFT JOIN dim_route dr ON dr.origin_iata = b.Origin AND dr.dest_iata = b.Dest AND dr.route_key <> -1
    LEFT JOIN dim_flight_status dfs
        ON dfs.cancelled_flag = b.cancelled_flag
        AND dfs.cancellation_reason_code <=> b.cancellation_reason_code
        AND dfs.diverted_flag = b.diverted_flag
        AND dfs.delay_class = b.computed_delay_class
        AND dfs.flight_status_key <> -1
)
SELECT
    b.flight_date_key,
    COALESCE(tod.time_key, -1),
    b.resolved_origin_airport_key,
    b.resolved_dest_airport_key,
    b.resolved_carrier_key,
    b.resolved_route_key,
    b.resolved_flight_status_key,
    COALESCE(oww.weather_condition_key, -1),
    COALESCE(dww.weather_condition_key, -1),
    b.flight_number,
    NULLIF(b.tail_number, ''),
    b.sched_dep_time_val,
    CASE WHEN b.DepDelay = '' THEN NULL ELSE CAST(b.DepDelay AS DECIMAL(10,2)) END,
    b.arr_delay_val,
    {_cause_case_sql("CarrierDelay")},
    {_cause_case_sql("WeatherDelay")},
    {_cause_case_sql("NASDelay")},
    {_cause_case_sql("SecurityDelay")},
    {_cause_case_sql("LateAircraftDelay")},
    CASE WHEN b.TaxiOut = '' THEN NULL ELSE CAST(b.TaxiOut AS DECIMAL(10,2)) END,
    CASE WHEN b.TaxiIn = '' THEN NULL ELSE CAST(b.TaxiIn AS DECIMAL(10,2)) END,
    CASE WHEN b.Distance = '' THEN NULL ELSE CAST(b.Distance AS DECIMAL(6,1)) END,
    1,
    CASE
        WHEN b.cancelled_flag THEN NULL
        WHEN b.arr_delay_val IS NULL THEN NULL
        ELSE (b.arr_delay_val < 15)
    END,
    CASE WHEN b.arr_delay_val IS NULL THEN NULL ELSE (b.arr_delay_val > 180) END
FROM resolved b
LEFT JOIN dim_time_of_day tod ON tod.hour_of_day = (b.sched_dep_time_val DIV 100)
LEFT JOIN fact_airport_weather_daily oww
    ON oww.date_key = b.flight_date_key AND oww.airport_key = b.resolved_origin_airport_key
LEFT JOIN fact_airport_weather_daily dww
    ON dww.date_key = b.flight_date_key AND dww.airport_key = b.resolved_dest_airport_key
"""


def load_fact_flight(engine: Engine, load_id: str = None) -> int:
    load_id = load_id or str(uuid.uuid4())
    with engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM fact_flight")
        result = conn.exec_driver_sql(FACT_FLIGHT_INSERT_SQL)
        inserted = result.rowcount
    log(f"fact_flight: {inserted} rows")
    log_exceptions(engine, load_id)
    return inserted


def main() -> int:
    engine = get_engine()
    load_fact_airport_weather_daily(engine)
    load_fact_flight(engine)
    return 0


if __name__ == "__main__":
    sys.exit(main())
