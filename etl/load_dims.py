"""Loads the seven dimensions and airport_station_map, in the brief's
locked order (section 6):

1. dim_date, dim_time_of_day (generated)
2. dim_airport, airport_station_map (needs stg_airports + NOAA station list)
3. dim_carrier (SCD2), dim_route, dim_flight_status, dim_weather_condition
   (dim_weather_condition additionally needs stg_noaa_daily, staged by
   etl/extract.py's NOAA step, which itself needs airport_station_map
   to know which stations to keep; see data/download_sources.py and
   etl/extract.py for that staging step)

All loads are idempotent: each function deletes the real (non -1) rows
it owns and reinserts, so re-running gives identical counts (hard rule 4).
"""
import math
import sys
from datetime import date, timedelta
from typing import Dict, List, Optional

import holidays
import numpy as np
import pandas as pd
from sqlalchemy.engine import Engine

from etl.clean import departure_band, distance_band
from etl.conform import build_station_daily_weather
from etl.db import get_engine

EARTH_RADIUS_KM = 6371.0
STATION_DISTANCE_THRESHOLD_KM = 75.0  # open decision 5, resolved in Phase 4 planning


def log(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# dim_date, dim_time_of_day
# ---------------------------------------------------------------------------

SEASON_BY_MONTH = {
    12: "Winter", 1: "Winter", 2: "Winter",
    3: "Spring", 4: "Spring", 5: "Spring",
    6: "Summer", 7: "Summer", 8: "Summer",
    9: "Fall", 10: "Fall", 11: "Fall",
}


def generate_dim_date_rows(year: int) -> List[dict]:
    us_holidays = holidays.US(years=year)
    rows = []
    d = date(year, 1, 1)
    end = date(year, 12, 31)
    while d <= end:
        iso_weekday = d.isoweekday()  # 1=Monday .. 7=Sunday
        rows.append({
            "date_key": int(d.strftime("%Y%m%d")),
            "full_date": d,
            "day_of_month": d.day,
            "day_of_week_num": iso_weekday,
            "day_of_week_name": d.strftime("%A"),
            "week_of_year": d.isocalendar()[1],
            "month_num": d.month,
            "month_name": d.strftime("%B"),
            "quarter": (d.month - 1) // 3 + 1,
            "year": d.year,
            "is_weekend": iso_weekday in (6, 7),
            "is_us_holiday": d in us_holidays,
            "holiday_name": us_holidays.get(d),
            "season": SEASON_BY_MONTH[d.month],
        })
        d += timedelta(days=1)
    return rows


def load_dim_date(engine: Engine, year: int) -> int:
    rows = generate_dim_date_rows(year)
    with engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM dim_date WHERE date_key <> -1")
        df = pd.DataFrame(rows)
        df.to_sql("dim_date", conn, if_exists="append", index=False)
    log(f"dim_date: {len(rows)} rows for {year}")
    return len(rows)


def generate_dim_time_of_day_rows() -> List[dict]:
    return [
        {"time_key": h, "hour_of_day": h, "departure_band": departure_band(h)}
        for h in range(24)
    ]


def load_dim_time_of_day(engine: Engine) -> int:
    rows = generate_dim_time_of_day_rows()
    with engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM dim_time_of_day WHERE time_key <> -1")
        pd.DataFrame(rows).to_sql("dim_time_of_day", conn, if_exists="append", index=False)
    log(f"dim_time_of_day: {len(rows)} rows")
    return len(rows)


# ---------------------------------------------------------------------------
# dim_airport, airport_station_map
# ---------------------------------------------------------------------------

def haversine_km_vectorized(lat1, lon1, lat2_arr: np.ndarray, lon2_arr: np.ndarray) -> np.ndarray:
    """Same method proven in etl/profile.py's distance histogram."""
    phi1 = math.radians(lat1)
    phi2 = np.radians(lat2_arr)
    dphi = np.radians(lat2_arr - lat1)
    dlambda = np.radians(lon2_arr - lon1)
    a = np.sin(dphi / 2) ** 2 + math.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


# Verified in Phase 2 (docs/profiling/summary.md, problem 10): these two
# OpenFlights rows claim country == "United States" but their real
# location (per latitude/longitude) is Hungary and Russia. Zero real
# flights reference either code. Excluded here for the same reason.
MISLABELED_COUNTRY_IATA = {"TZR", "OEL"}


def load_dim_airport_and_station_map(engine: Engine, raw_dir) -> int:
    airports = pd.read_csv(
        raw_dir / "openflights" / "airports.dat",
        header=None,
        names=[
            "airport_id", "name", "city", "country", "iata", "icao",
            "latitude", "longitude", "altitude", "tz_offset", "dst",
            "tz_database_name", "airport_type", "source",
        ],
        na_values=["\\N"],
    )
    # BTS "Reporting Carrier On-Time Performance" treats US territories
    # as domestic (they appear as real Origin/Dest codes in the 2025
    # data), but OpenFlights' country field uses each territory's own
    # name rather than "United States". Confirmed by checking the real
    # unmatched codes after the first load attempt: SJU, STT, BQN, STX,
    # GUM, PSE, SPN, PPG all turned out to be exactly this, 71,418 +
    # 10,087 + ... real flight-row mentions that a "country == United
    # States" filter alone had wrongly dropped. XWA and EAR are the
    # two still-unmatched codes from Phase 2 (docs/profiling/summary.md,
    # problem 4): genuinely absent from OpenFlights, not a filter bug.
    US_DOMESTIC_COUNTRIES = {
        "United States", "Puerto Rico", "Virgin Islands", "Guam",
        "American Samoa", "Northern Mariana Islands",
    }
    airports = airports[airports["country"].isin(US_DOMESTIC_COUNTRIES)]
    airports = airports.dropna(subset=["iata", "latitude", "longitude"])
    airports = airports[airports["iata"] != ""]
    airports = airports[~airports["iata"].isin(MISLABELED_COUNTRY_IATA)]
    airports = airports.drop_duplicates(subset=["iata"], keep="first")

    # US state: OpenFlights has no state field; pull it from the BTS
    # staging data instead (Origin/OriginState, Dest/DestState), per
    # docs/source_to_target_mapping.md.
    with engine.connect() as conn:
        state_rows = conn.exec_driver_sql(
            """
            SELECT code, state FROM (
                SELECT Origin AS code, OriginState AS state FROM stg_bts_flights
                UNION
                SELECT Dest AS code, DestState AS state FROM stg_bts_flights
            ) t
            WHERE state IS NOT NULL AND state <> ''
            """
        ).fetchall()
    state_by_code: Dict[str, str] = {code: state for code, state in state_rows}

    stations = pd.read_fwf(
        raw_dir / "noaa" / "ghcnd-stations.txt",
        colspecs=[(0, 11), (12, 20), (21, 30), (31, 37), (38, 40), (41, 71)],
        names=["id", "latitude", "longitude", "elevation", "state", "name"],
    )
    us_stations = stations[stations["id"].str.startswith("US")]
    station_lats = us_stations["latitude"].to_numpy()
    station_lons = us_stations["longitude"].to_numpy()
    station_ids = us_stations["id"].to_numpy()

    airport_rows = []
    station_map_rows = []
    for _, a in airports.iterrows():
        distances = haversine_km_vectorized(a["latitude"], a["longitude"], station_lats, station_lons)
        nearest_idx = int(np.argmin(distances))
        nearest_station = str(station_ids[nearest_idx])
        nearest_distance = round(float(distances[nearest_idx]), 2)
        airport_rows.append({
            "iata_code": a["iata"],
            "icao_code": a["icao"] if pd.notna(a["icao"]) else None,
            "name": a["name"],
            "city": a["city"] if pd.notna(a["city"]) else None,
            "state": state_by_code.get(a["iata"]),
            "country": a["country"],
            "latitude": round(float(a["latitude"]), 6),
            "longitude": round(float(a["longitude"]), 6),
            "tz_database_name": a["tz_database_name"] if pd.notna(a["tz_database_name"]) else None,
            "nearest_station_id": nearest_station,
            "traffic_tier": None,  # set after fact_flight loads; see load_facts.py
        })
        station_map_rows.append({
            "iata_code": a["iata"],
            "station_id": nearest_station,
            "distance_km": nearest_distance,
            "within_threshold": nearest_distance <= STATION_DISTANCE_THRESHOLD_KM,
        })

    with engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM airport_station_map")
        conn.exec_driver_sql("DELETE FROM dim_airport WHERE airport_key <> -1")
        airport_df = pd.DataFrame(airport_rows)
        airport_df.to_sql("dim_airport", conn, if_exists="append", index=False)

        key_rows = conn.exec_driver_sql(
            "SELECT airport_key, iata_code FROM dim_airport WHERE airport_key <> -1"
        ).fetchall()
        key_by_iata = {iata: key for key, iata in key_rows}

        station_map_df = pd.DataFrame(station_map_rows)
        station_map_df["airport_key"] = station_map_df["iata_code"].map(key_by_iata)
        station_map_df = station_map_df.drop(columns=["iata_code"])
        station_map_df.to_sql("airport_station_map", conn, if_exists="append", index=False)

    beyond_threshold = sum(1 for r in station_map_rows if not r["within_threshold"])
    log(
        f"dim_airport: {len(airport_rows)} rows, airport_station_map: "
        f"{len(station_map_rows)} rows ({beyond_threshold} beyond "
        f"{STATION_DISTANCE_THRESHOLD_KM}km threshold)"
    )
    return len(airport_rows)


# ---------------------------------------------------------------------------
# dim_carrier (SCD Type 2)
# ---------------------------------------------------------------------------

def load_dim_carrier(engine: Engine) -> int:
    """One version per carrier code for now: S4 (carrier names) is
    blocked (docs/DECISIONS.md, item B1), so carrier_name falls back to
    the raw code, and there is only one calendar year of BTS data to
    check for a real mid-year change, so effective_to is NULL and
    is_current is true for every row. The SCD2 *lookup* used when
    loading fact_flight (etl/load_facts.py) still joins on the full
    effective_from/effective_to range, not just the code, so it would
    resolve correctly the day a second version is ever added; see
    tests/test_conform.py for a synthetic, clearly labelled case that
    exercises that with more than one version (open decision 6).
    """
    with engine.connect() as conn:
        rows = conn.exec_driver_sql(
            """
            SELECT Reporting_Airline AS carrier_code, MIN(FlightDate) AS first_seen
            FROM stg_bts_flights
            GROUP BY Reporting_Airline
            """
        ).fetchall()
    carrier_rows = [
        {
            "carrier_code": code,
            "carrier_name": code,  # placeholder until S4 is unblocked
            "effective_from": first_seen,
            "effective_to": None,
            "is_current": True,
        }
        for code, first_seen in rows
    ]
    with engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM dim_carrier WHERE carrier_key <> -1")
        pd.DataFrame(carrier_rows).to_sql("dim_carrier", conn, if_exists="append", index=False)
    log(f"dim_carrier: {len(carrier_rows)} rows (one version each; carrier_name is a placeholder, S4 blocked)")
    return len(carrier_rows)


# ---------------------------------------------------------------------------
# dim_route
# ---------------------------------------------------------------------------

def load_dim_route(engine: Engine) -> int:
    with engine.connect() as conn:
        rows = conn.exec_driver_sql(
            """
            SELECT Origin, Dest, MIN(CAST(Distance AS DECIMAL(8,2))) AS distance_miles
            FROM stg_bts_flights
            WHERE Distance <> ''
            GROUP BY Origin, Dest
            """
        ).fetchall()
    route_rows = [
        {
            "origin_iata": origin,
            "dest_iata": dest,
            "distance_miles": float(miles) if miles is not None else None,
            "distance_band": distance_band(float(miles) if miles is not None else None),
        }
        for origin, dest, miles in rows
    ]
    with engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM dim_route WHERE route_key <> -1")
        pd.DataFrame(route_rows).to_sql("dim_route", conn, if_exists="append", index=False)
    log(f"dim_route: {len(route_rows)} rows")
    return len(route_rows)


# ---------------------------------------------------------------------------
# dim_flight_status (junk dimension)
# ---------------------------------------------------------------------------

# Mirrors etl.clean.delay_class exactly, but as SQL so the distinct-combo
# scan runs as one set-based query against 7 million rows instead of
# pulling them into Python.
DELAY_CLASS_SQL = """
    CASE
        WHEN Cancelled = '1.00' THEN 'cancelled'
        WHEN Diverted = '1.00' THEN 'diverted'
        WHEN ArrDelay = '' THEN 'Unknown'
        WHEN CAST(ArrDelay AS DECIMAL(10,2)) < 15 THEN 'on_time'
        WHEN CAST(ArrDelay AS DECIMAL(10,2)) <= 180 THEN 'minor_delay'
        ELSE 'major_delay'
    END
"""


def load_dim_flight_status(engine: Engine) -> int:
    with engine.connect() as conn:
        rows = conn.exec_driver_sql(
            f"""
            SELECT DISTINCT
                Cancelled = '1.00' AS cancelled_flag,
                NULLIF(TRIM(CancellationCode), '') AS cancellation_reason_code,
                Diverted = '1.00' AS diverted_flag,
                {DELAY_CLASS_SQL} AS delay_class
            FROM stg_bts_flights
            """
        ).fetchall()
    status_rows = [
        {
            "cancelled_flag": bool(cancelled),
            "cancellation_reason_code": reason,
            "diverted_flag": bool(diverted),
            "delay_class": cls,
        }
        for cancelled, reason, diverted, cls in rows
    ]
    with engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM dim_flight_status WHERE flight_status_key <> -1")
        pd.DataFrame(status_rows).to_sql("dim_flight_status", conn, if_exists="append", index=False)
    log(f"dim_flight_status: {len(status_rows)} distinct combinations found in the real data")
    return len(status_rows)


# ---------------------------------------------------------------------------
# dim_weather_condition (junk dimension, derived from S2)
# ---------------------------------------------------------------------------

def load_dim_weather_condition(engine: Engine) -> int:
    daily = build_station_daily_weather(engine)
    combos = daily[["precip_band", "snow_band", "wind_band", "temp_band"]].drop_duplicates()
    rows = combos.to_dict("records")
    with engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM dim_weather_condition WHERE weather_condition_key <> -1")
        pd.DataFrame(rows).to_sql("dim_weather_condition", conn, if_exists="append", index=False)
    log(f"dim_weather_condition: {len(rows)} distinct band combinations found in the real data")
    return len(rows)
