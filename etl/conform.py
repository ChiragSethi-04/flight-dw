"""Cross-cutting derivation logic shared by load_dims.py and
load_facts.py: turning stg_noaa_daily's long format (one row per
station/date/element) into the wide, banded form both the
dim_weather_condition junk dimension and fact_airport_weather_daily
need, computed once so the two callers agree.
"""
from datetime import date
from typing import List, Optional, TypedDict

import pandas as pd
from sqlalchemy.engine import Engine

from etl.clean import noaa_value, precip_band, snow_band, temp_band, wind_band


class CarrierVersion(TypedDict):
    carrier_key: int
    carrier_code: str
    effective_from: date
    effective_to: Optional[date]


def resolve_carrier_key(versions: List[CarrierVersion], carrier_code: str, flight_date: date) -> Optional[int]:
    """The SCD Type 2 lookup etl/load_facts.py's set-based SQL
    implements directly as a JOIN (dc.carrier_code = ... AND
    flight_date BETWEEN effective_from AND effective_to). This pure
    Python version exists only so the lookup *logic* can be unit
    tested in isolation, per open decision 6: one year of 2025 BTS
    data shows no carrier with more than one version (see
    docs/DECISIONS.md), so this is exercised here on a synthetic,
    clearly labelled multi-version case, never on real data.
    """
    for version in versions:
        if version["carrier_code"] != carrier_code:
            continue
        if flight_date < version["effective_from"]:
            continue
        if version["effective_to"] is not None and flight_date > version["effective_to"]:
            continue
        return version["carrier_key"]
    return None

ELEMENT_COLUMNS = {
    "PRCP": "precip_raw",
    "SNOW": "snowfall_raw",
    "SNWD": "snow_depth_raw",
    "AWND": "avg_wind_raw",
    "TMAX": "tmax_raw",
    "TMIN": "tmin_raw",
}


def build_station_daily_weather(engine: Engine) -> pd.DataFrame:
    """One row per (station_id, obs_date) actually present in
    stg_noaa_daily, with each element pivoted from long to wide, NOAA's
    tenths-to-units and -9999-to-NULL rules applied, and the four
    weather bands computed. obs_date stays as the raw 'YYYYMMDD' text
    NOAA uses; callers convert to a date_key themselves.
    """
    case_clauses = ",\n            ".join(
        f"MAX(CASE WHEN element = '{element}' THEN raw_value END) AS {col}"
        for element, col in ELEMENT_COLUMNS.items()
    )
    sql = f"""
        SELECT station_id, obs_date,
            {case_clauses}
        FROM stg_noaa_daily
        GROUP BY station_id, obs_date
    """
    df = pd.read_sql(sql, engine)

    df["precip_mm"] = df["precip_raw"].apply(noaa_value)
    df["snowfall_mm"] = df["snowfall_raw"].apply(noaa_value)
    df["snow_depth_mm"] = df["snow_depth_raw"].apply(noaa_value)
    df["avg_wind_ms"] = df["avg_wind_raw"].apply(noaa_value)
    df["tmax_c"] = df["tmax_raw"].apply(noaa_value)
    df["tmin_c"] = df["tmin_raw"].apply(noaa_value)

    df["precip_band"] = df["precip_mm"].apply(precip_band)
    df["snow_band"] = df["snowfall_mm"].apply(snow_band)
    df["wind_band"] = df["avg_wind_ms"].apply(wind_band)
    df["temp_band"] = df["tmin_c"].apply(temp_band)

    return df[
        [
            "station_id", "obs_date",
            "precip_mm", "snowfall_mm", "snow_depth_mm", "avg_wind_ms", "tmax_c", "tmin_c",
            "precip_band", "snow_band", "wind_band", "temp_band",
        ]
    ]
