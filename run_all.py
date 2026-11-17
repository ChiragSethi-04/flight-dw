"""Pipeline orchestrator for the flight-dw warehouse.

One script, numbered steps, run in order (hard rule 4). Every step is
idempotent: staging is truncate-and-reload, dimensions and facts are
deleted-and-reinserted by this same script, so running it twice gives
identical counts.

Usage:
    python run_all.py              # run every step for DATA_YEAR in .env
    python run_all.py --check-db   # only verify the MySQL connection (Phase 0)
    python run_all.py --status     # show which steps exist without running them
"""
import argparse
import os
import sys
import uuid
from pathlib import Path

from etl.audit import stage
from etl.db import get_engine

ROOT_DIR = Path(__file__).resolve().parent
RAW_DIR = ROOT_DIR / "data" / "raw"


def check_db() -> None:
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.exec_driver_sql("SELECT 1").scalar()
        print(f"MySQL connection OK, SELECT 1 returned: {result}")


STEP_NAMES = [
    "01_create_schemas",
    "02_create_staging",
    "03_create_warehouse",
    "extract_s1_bts",
    "extract_s3_airports",
    "load_dim_date",
    "load_dim_time_of_day",
    "load_dim_airport_and_station_map",
    "download_s2_noaa_daily_by_year",
    "extract_s2_noaa_daily",
    "load_dim_carrier",
    "load_dim_route",
    "load_dim_flight_status",
    "load_dim_weather_condition",
    "load_fact_airport_weather_daily",
    "load_fact_flight",
]


def run_all(year: int) -> int:
    from data.download_sources import download_s2_noaa_daily_by_year
    from etl.extract import extract_s1_bts, extract_s2_noaa_daily, extract_s3_airports, run_sql_file
    from etl.load_dims import (
        load_dim_airport_and_station_map,
        load_dim_carrier,
        load_dim_date,
        load_dim_flight_status,
        load_dim_route,
        load_dim_time_of_day,
        load_dim_weather_condition,
    )
    from etl.load_facts import load_fact_airport_weather_daily, load_fact_flight

    engine = get_engine(local_infile=True)
    load_id = str(uuid.uuid4())
    print(f"run_all starting, load_id={load_id}, year={year}")

    # Not wrapped in stage(): these three create audit_log itself, so
    # there is nowhere to log a failure of them to until they succeed.
    sql_dir = ROOT_DIR / "sql"
    print("Applying sql/01_create_schemas.sql, sql/02_create_staging.sql, sql/03_create_warehouse.sql")
    run_sql_file(engine, sql_dir / "01_create_schemas.sql")
    run_sql_file(engine, sql_dir / "02_create_staging.sql")
    run_sql_file(engine, sql_dir / "03_create_warehouse.sql")

    with stage(engine, load_id, "extract_s1_bts") as s:
        extract_s1_bts(engine, load_id)
    with stage(engine, load_id, "extract_s3_airports") as s:
        extract_s3_airports(engine, load_id)

    with stage(engine, load_id, "load_dim_date") as s:
        s.rows_out = load_dim_date(engine, year)
    with stage(engine, load_id, "load_dim_time_of_day") as s:
        s.rows_out = load_dim_time_of_day(engine)
    with stage(engine, load_id, "load_dim_airport_and_station_map") as s:
        s.rows_out = load_dim_airport_and_station_map(engine, RAW_DIR)

    with stage(engine, load_id, "download_s2_noaa_daily_by_year") as s:
        download_s2_noaa_daily_by_year(year, force=False)
    with stage(engine, load_id, "extract_s2_noaa_daily") as s:
        extract_s2_noaa_daily(engine, load_id, year)

    with stage(engine, load_id, "load_dim_carrier") as s:
        s.rows_out = load_dim_carrier(engine)
    with stage(engine, load_id, "load_dim_route") as s:
        s.rows_out = load_dim_route(engine)
    with stage(engine, load_id, "load_dim_flight_status") as s:
        s.rows_out = load_dim_flight_status(engine)
    with stage(engine, load_id, "load_dim_weather_condition") as s:
        s.rows_out = load_dim_weather_condition(engine)

    with stage(engine, load_id, "load_fact_airport_weather_daily") as s:
        s.rows_out = load_fact_airport_weather_daily(engine)
    with stage(engine, load_id, "load_fact_flight") as s:
        s.rows_out = load_fact_flight(engine)

    print(f"run_all finished, load_id={load_id}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-db", action="store_true", help="only verify the MySQL connection")
    parser.add_argument("--status", action="store_true", help="show step names without running them")
    env_year = os.environ.get("DATA_YEAR")
    parser.add_argument("--year", type=int, default=int(env_year) if env_year else None)
    args = parser.parse_args()

    if args.check_db:
        check_db()
        return 0

    if args.status:
        print("flight-dw pipeline steps, in order:")
        for name in STEP_NAMES:
            print(f"  {name}")
        return 0

    if args.year is None:
        print("No data year given. Set DATA_YEAR in .env or pass --year.", file=sys.stderr)
        return 2

    return run_all(args.year)


if __name__ == "__main__":
    sys.exit(main())
