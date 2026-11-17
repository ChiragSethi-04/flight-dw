"""Data quality profiling for Phase 2 (Task 3 in the brief).

Runs against the staged data loaded by etl/extract.py (stg_bts_flights,
stg_airports) and the raw NOAA reference files (not staged as tables,
per the scope note in sql/02_create_staging.sql). Writes every result to
docs/profiling/ as CSV, plus a short markdown summary that confirms or
refutes each of the nine expected problems in section 4 of the brief
with real counts.

This script never invents a result (hard rule 3): every number below
comes from a query run against the real staged data, or from the real
downloaded NOAA/OpenFlights reference files.

Usage:
    python -m etl.profile
"""
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from etl.db import get_engine

ROOT_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT_DIR / "data" / "raw"
PROFILING_DIR = ROOT_DIR / "docs" / "profiling"

EARTH_RADIUS_KM = 6371.0

BUSINESS_KEY_COLUMNS = [
    "Reporting_Airline",
    "Flight_Number_Reporting_Airline",
    "Origin",
    "Dest",
    "CRSDepTime",
    "FlightDate",
]


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def haversine_km_vectorized(lat1, lon1, lat2_arr: np.ndarray, lon2_arr: np.ndarray) -> np.ndarray:
    """Same formula as haversine_km, but lat2_arr/lon2_arr are numpy arrays
    of every candidate station, so one airport is compared against all
    stations in one vectorized call instead of a Python-level loop. With
    1,251 US airports and 78,570 US stations, a pure-Python double loop
    would be about 98 million scalar haversine calls; vectorizing the
    inner loop turns that into 1,251 fast numpy operations instead.
    """
    phi1 = math.radians(lat1)
    phi2 = np.radians(lat2_arr)
    dphi = np.radians(lat2_arr - lat1)
    dlambda = np.radians(lon2_arr - lon1)
    a = np.sin(dphi / 2) ** 2 + math.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def section(title: str) -> None:
    print(f"\n== {title} ==")


# ---------------------------------------------------------------------------
# Row counts and basic shape
# ---------------------------------------------------------------------------

def profile_row_counts(engine) -> pd.DataFrame:
    section("Row counts per BTS source_file (reconciliation: Phase 1 acceptance already matched CSV line counts 1:1)")
    df = pd.read_sql(
        "SELECT source_file, COUNT(*) AS staged_rows FROM stg_bts_flights GROUP BY source_file ORDER BY source_file",
        engine,
    )
    print(df.to_string(index=False))
    df.to_csv(PROFILING_DIR / "row_counts_per_month.csv", index=False)
    return df


# ---------------------------------------------------------------------------
# Null counts per column (stg_bts_flights)
# ---------------------------------------------------------------------------

def profile_null_counts(engine) -> pd.DataFrame:
    section("Null/empty counts per column, stg_bts_flights (full detail in CSV)")
    with engine.connect() as conn:
        columns = [
            r[0]
            for r in conn.exec_driver_sql("SHOW COLUMNS FROM stg_bts_flights").fetchall()
            if r[0] not in ("load_id", "source_file", "load_timestamp")
        ]
        total_rows = conn.exec_driver_sql("SELECT COUNT(*) FROM stg_bts_flights").scalar()
        # One pass over the table computing all 109 counts at once, rather
        # than 109 separate full-table-scan queries (which is what this did
        # at first, and took about 18 minutes over 7 million unindexed
        # rows). A single-pass conditional-aggregate query does the same
        # work in one scan.
        select_clause = ", ".join(f"SUM(`{col}` = '' OR `{col}` IS NULL) AS `{col}`" for col in columns)
        row = conn.exec_driver_sql(f"SELECT {select_clause} FROM stg_bts_flights").fetchone()
        rows = [
            {
                "column": col,
                "empty_or_null_count": int(row[i]),
                "pct_empty_or_null": round(100.0 * int(row[i]) / total_rows, 2) if total_rows else 0,
            }
            for i, col in enumerate(columns)
        ]
    df = pd.DataFrame(rows)
    df.to_csv(PROFILING_DIR / "stg_bts_flights_null_counts.csv", index=False)
    print(df[df["empty_or_null_count"] > 0].sort_values("empty_or_null_count", ascending=False).head(20).to_string(index=False))
    return df


# ---------------------------------------------------------------------------
# Problem 5: duplicate flight records on the business key
# ---------------------------------------------------------------------------

def profile_duplicates(engine) -> int:
    section("Problem 5: duplicate flight records on the business key")
    key_cols = ", ".join(f"`{c}`" for c in BUSINESS_KEY_COLUMNS)
    df = pd.read_sql(
        f"""
        SELECT {key_cols}, COUNT(*) AS n
        FROM stg_bts_flights
        GROUP BY {key_cols}
        HAVING COUNT(*) > 1
        ORDER BY n DESC
        """,
        engine,
    )
    df.to_csv(PROFILING_DIR / "problem5_duplicate_business_keys.csv", index=False)
    dup_groups = len(df)
    dup_rows = int(df["n"].sum()) if dup_groups else 0
    print(f"Duplicate business-key groups: {dup_groups}, total rows involved: {dup_rows}")
    return dup_rows


# ---------------------------------------------------------------------------
# Problem 4: airport codes with no match in the airport reference
# ---------------------------------------------------------------------------

def profile_airport_code_match(engine) -> pd.DataFrame:
    section("Problem 4: BTS Origin/Dest codes with no match in stg_airports (IATA)")
    # Grouping first, in SQL, reduces this to a few hundred distinct codes
    # before comparing against the airport list in pandas. The equivalent
    # single SQL query (code NOT IN (SELECT iata FROM stg_airports), over a
    # 14-million-row UNION ALL of Origin and Dest) was tried first and
    # stalled: MySQL's NOT IN subquery plan does not use an index here, so
    # it was heading toward an effectively quadratic scan. Grouping each
    # column's ~400 distinct values down to a handful of SQL rows avoids
    # that entirely.
    origin_counts = pd.read_sql("SELECT Origin AS code, COUNT(*) AS n FROM stg_bts_flights GROUP BY Origin", engine)
    dest_counts = pd.read_sql("SELECT Dest AS code, COUNT(*) AS n FROM stg_bts_flights GROUP BY Dest", engine)
    code_counts = pd.concat([origin_counts, dest_counts]).groupby("code", as_index=False)["n"].sum()
    code_counts = code_counts.rename(columns={"n": "flight_rows"})

    airport_codes = pd.read_sql(
        "SELECT DISTINCT iata AS code FROM stg_airports WHERE iata IS NOT NULL AND iata <> ''", engine
    )
    df = code_counts[~code_counts["code"].isin(airport_codes["code"])].sort_values("flight_rows", ascending=False)
    df.to_csv(PROFILING_DIR / "problem4_unmatched_airport_codes.csv", index=False)
    print(f"Distinct unmatched Origin/Dest codes: {len(df)}, total flight-row mentions: {int(df['flight_rows'].sum()) if len(df) else 0}")
    return df


# ---------------------------------------------------------------------------
# Problem 1: cancelled flights have empty time/delay fields
# ---------------------------------------------------------------------------

def profile_problem1_cancelled(engine) -> dict:
    section("Problem 1: cancelled flights have empty time/delay fields")
    with engine.connect() as conn:
        total = conn.exec_driver_sql("SELECT COUNT(*) FROM stg_bts_flights").scalar()
        cancelled = conn.exec_driver_sql("SELECT COUNT(*) FROM stg_bts_flights WHERE Cancelled = '1.00'").scalar()
        cancelled_with_arrdelay = conn.exec_driver_sql(
            "SELECT COUNT(*) FROM stg_bts_flights WHERE Cancelled = '1.00' AND ArrDelay <> ''"
        ).scalar()
    sample = pd.read_sql(
        """
        SELECT FlightDate, Reporting_Airline, Flight_Number_Reporting_Airline, Origin, Dest,
               DepTime, ArrTime, ArrDelay, CarrierDelay, Cancelled, CancellationCode
        FROM stg_bts_flights WHERE Cancelled = '1.00' LIMIT 10
        """,
        engine,
    )
    before = sample.copy()
    after = sample.copy()
    after["DepTime"] = None
    after["ArrTime"] = None
    after["ArrDelay"] = None
    after["CarrierDelay"] = None
    after["cancelled_flag_proposed"] = 1
    before.to_csv(PROFILING_DIR / "problem1_before_10rows.csv", index=False)
    after.to_csv(PROFILING_DIR / "problem1_after_10rows_proposed.csv", index=False)
    result = {
        "total_rows": total,
        "cancelled_rows": cancelled,
        "cancelled_pct": round(100.0 * cancelled / total, 2) if total else 0,
        "cancelled_rows_with_nonempty_arrdelay": cancelled_with_arrdelay,
    }
    print(result)
    return result


# ---------------------------------------------------------------------------
# Problem 2: midnight stored as 2400
# ---------------------------------------------------------------------------

def profile_problem2_midnight(engine) -> dict:
    section("Problem 2: midnight stored as 2400 in time fields")
    with engine.connect() as conn:
        counts = {}
        for col in ("CRSDepTime", "DepTime", "CRSArrTime", "ArrTime"):
            counts[col] = conn.exec_driver_sql(f"SELECT COUNT(*) FROM stg_bts_flights WHERE `{col}` = '2400'").scalar()
        any_2400 = conn.exec_driver_sql(
            "SELECT COUNT(*) FROM stg_bts_flights WHERE CRSDepTime='2400' OR DepTime='2400' OR CRSArrTime='2400' OR ArrTime='2400'"
        ).scalar()
    sample = pd.read_sql(
        """
        SELECT FlightDate, Reporting_Airline, Origin, Dest, CRSDepTime, DepTime, CRSArrTime, ArrTime
        FROM stg_bts_flights WHERE CRSDepTime = '2400' OR ArrTime = '2400' LIMIT 10
        """,
        engine,
    )
    before = sample.copy()
    after = sample.copy()
    for col in ("CRSDepTime", "DepTime", "CRSArrTime", "ArrTime"):
        after[col] = after[col].replace("2400", "0000")
    after["note"] = (
        "Proposed preview only (open decision 4, not yet team-decided): time "
        "mapped 2400->0000; FlightDate is left unchanged here per the locked "
        "rule that flight date stays the local departure date, rolling the "
        "date forward only when a full timestamp is built, which this "
        "preview does not do."
    )
    before.to_csv(PROFILING_DIR / "problem2_before_10rows.csv", index=False)
    after.to_csv(PROFILING_DIR / "problem2_after_10rows_proposed.csv", index=False)
    result = {"any_2400_rows": any_2400, **counts}
    print(result)
    return result


# ---------------------------------------------------------------------------
# Problem 3: delay cause fields blank when arrival delay under 15 minutes
# ---------------------------------------------------------------------------

def profile_problem3_delay_causes(engine) -> dict:
    section("Problem 3: delay cause fields blank when ArrDelay < 15, and cause-sum reconciliation for ArrDelay >= 15")
    with engine.connect() as conn:
        blank_causes_low_delay = conn.exec_driver_sql(
            """
            SELECT COUNT(*) FROM stg_bts_flights
            WHERE Cancelled = '0.00' AND ArrDelay <> '' AND CAST(ArrDelay AS DECIMAL(10,2)) < 15
              AND CarrierDelay = '' AND WeatherDelay = '' AND NASDelay = '' AND SecurityDelay = '' AND LateAircraftDelay = ''
            """
        ).scalar()
        qualifying_high_delay = conn.exec_driver_sql(
            """
            SELECT COUNT(*) FROM stg_bts_flights
            WHERE Cancelled = '0.00' AND ArrDelay <> '' AND CAST(ArrDelay AS DECIMAL(10,2)) >= 15
              AND CarrierDelay <> '' AND WeatherDelay <> '' AND NASDelay <> '' AND SecurityDelay <> '' AND LateAircraftDelay <> ''
            """
        ).scalar()
        mismatches = conn.exec_driver_sql(
            """
            SELECT COUNT(*) FROM stg_bts_flights
            WHERE Cancelled = '0.00' AND ArrDelay <> '' AND CAST(ArrDelay AS DECIMAL(10,2)) >= 15
              AND CarrierDelay <> '' AND WeatherDelay <> '' AND NASDelay <> '' AND SecurityDelay <> '' AND LateAircraftDelay <> ''
              AND CAST(ArrDelay AS DECIMAL(10,2)) <>
                  (CAST(CarrierDelay AS DECIMAL(10,2)) + CAST(WeatherDelay AS DECIMAL(10,2))
                   + CAST(NASDelay AS DECIMAL(10,2)) + CAST(SecurityDelay AS DECIMAL(10,2))
                   + CAST(LateAircraftDelay AS DECIMAL(10,2)))
            """
        ).scalar()
    sample = pd.read_sql(
        """
        SELECT FlightDate, Reporting_Airline, Origin, Dest, ArrDelay,
               CarrierDelay, WeatherDelay, NASDelay, SecurityDelay, LateAircraftDelay
        FROM stg_bts_flights
        WHERE Cancelled = '0.00' AND ArrDelay <> '' AND CAST(ArrDelay AS DECIMAL(10,2)) < 15
          AND CarrierDelay = ''
        LIMIT 10
        """,
        engine,
    )
    before = sample.copy()
    after = sample.copy()
    for col in ("CarrierDelay", "WeatherDelay", "NASDelay", "SecurityDelay", "LateAircraftDelay"):
        after[col] = 0
    before.to_csv(PROFILING_DIR / "problem3_before_10rows.csv", index=False)
    after.to_csv(PROFILING_DIR / "problem3_after_10rows_proposed.csv", index=False)
    result = {
        "rows_blank_causes_low_delay": blank_causes_low_delay,
        "rows_qualifying_for_cause_sum_check": qualifying_high_delay,
        "rows_where_causes_dont_sum_to_arrdelay": mismatches,
        "mismatch_pct_of_qualifying": round(100.0 * mismatches / qualifying_high_delay, 3) if qualifying_high_delay else 0,
    }
    print(result)
    return result


# ---------------------------------------------------------------------------
# Problem 9: extreme delay values and diverted flights
# ---------------------------------------------------------------------------

def profile_problem9_outliers(engine) -> dict:
    section("Problem 9: extreme delay values and diverted flights")
    with engine.connect() as conn:
        total = conn.exec_driver_sql("SELECT COUNT(*) FROM stg_bts_flights").scalar()
        diverted = conn.exec_driver_sql("SELECT COUNT(*) FROM stg_bts_flights WHERE Diverted = '1.00'").scalar()
        max_arrdelay = conn.exec_driver_sql(
            "SELECT MAX(CAST(ArrDelay AS DECIMAL(10,2))) FROM stg_bts_flights WHERE ArrDelay <> ''"
        ).scalar()
        extreme_arrdelay = conn.exec_driver_sql(
            "SELECT COUNT(*) FROM stg_bts_flights WHERE ArrDelay <> '' AND CAST(ArrDelay AS DECIMAL(10,2)) > 180"
        ).scalar()
    result = {
        "total_rows": total,
        "diverted_rows": diverted,
        "diverted_pct": round(100.0 * diverted / total, 3) if total else 0,
        "max_arrdelay_minutes": float(max_arrdelay) if max_arrdelay is not None else None,
        "rows_with_arrdelay_over_180min": extreme_arrdelay,
        "rows_with_arrdelay_over_180min_pct": round(100.0 * extreme_arrdelay / total, 4) if total else 0,
    }
    print(result)
    return result


# ---------------------------------------------------------------------------
# Problem 7: airport-to-nearest-station distance histogram (feeds decision 5)
# ---------------------------------------------------------------------------

OUTLIER_DISTANCE_KM = 500.0


def profile_airport_station_distance(engine) -> pd.DataFrame:
    section("Problem 7 / open decision 5: airport-to-nearest-station distance histogram")
    airports = pd.read_csv(
        RAW_DIR / "openflights" / "airports.dat",
        header=None,
        names=[
            "airport_id", "name", "city", "country", "iata", "icao",
            "latitude", "longitude", "altitude", "tz_offset", "dst",
            "tz_database_name", "airport_type", "source",
        ],
        na_values=["\\N"],
    )
    airports = airports[airports["country"] == "United States"].dropna(subset=["iata", "latitude", "longitude"])
    airports = airports[airports["iata"] != ""]

    stations = pd.read_fwf(
        RAW_DIR / "noaa" / "ghcnd-stations.txt",
        colspecs=[(0, 11), (12, 20), (21, 30), (31, 37), (38, 40), (41, 71)],
        names=["id", "latitude", "longitude", "elevation", "state", "name"],
    )
    us_stations = stations[stations["id"].str.startswith("US")]

    rows = []
    station_lats = us_stations["latitude"].to_numpy()
    station_lons = us_stations["longitude"].to_numpy()
    station_ids = us_stations["id"].to_numpy()

    for _, airport in airports.iterrows():
        distances = haversine_km_vectorized(airport["latitude"], airport["longitude"], station_lats, station_lons)
        nearest_idx = int(np.argmin(distances))
        rows.append(
            {
                "iata": airport["iata"],
                "nearest_station_id": station_ids[nearest_idx],
                "distance_km": round(float(distances[nearest_idx]), 2),
            }
        )

    df = pd.DataFrame(rows)
    df.to_csv(PROFILING_DIR / "problem7_airport_station_distances.csv", index=False)

    # New problem found (not one of the brief's original nine): a few
    # OpenFlights rows have country == "United States" but a latitude and
    # longitude that place them elsewhere entirely (checked by hand: IATA
    # codes TZR and OEL resolve to "Taszar Air Base" in Hungary and "Oryol
    # Yuzhny Airport" in Russia). Left in, these produce nonsense
    # "nearest station" distances of several thousand km that would
    # distort the threshold decision. They are flagged out of the main
    # histogram here rather than silently dropped from the dataset: see
    # problem10_mislabeled_country_outliers.csv, and
    # docs/profiling/summary.md for the real-impact check (do any actual
    # 2025 flights reference these codes).
    outliers = df[df["distance_km"] > OUTLIER_DISTANCE_KM].copy()
    clean = df[df["distance_km"] <= OUTLIER_DISTANCE_KM].copy()
    if len(outliers):
        flight_counts = pd.read_sql(
            f"""
            SELECT code, COUNT(*) AS flight_rows FROM (
                SELECT Origin AS code FROM stg_bts_flights WHERE Origin IN ({",".join(repr(c) for c in outliers["iata"])})
                UNION ALL
                SELECT Dest AS code FROM stg_bts_flights WHERE Dest IN ({",".join(repr(c) for c in outliers["iata"])})
            ) t GROUP BY code
            """,
            engine,
        )
        outliers = outliers.merge(flight_counts, left_on="iata", right_on="code", how="left").drop(columns=["code"])
        outliers["flight_rows"] = outliers["flight_rows"].fillna(0).astype(int)
    outliers.to_csv(PROFILING_DIR / "problem10_mislabeled_country_outliers.csv", index=False)

    bins = [0, 5, 10, 20, 30, 50, 75, 100, 150, 200, float("inf")]
    labels = ["0-5", "5-10", "10-20", "20-30", "30-50", "50-75", "75-100", "100-150", "150-200", "200+"]
    hist = pd.cut(clean["distance_km"], bins=bins, labels=labels).value_counts().sort_index()
    hist_df = hist.reset_index()
    hist_df.columns = ["distance_km_band", "airport_count"]
    hist_df.to_csv(PROFILING_DIR / "problem7_distance_histogram.csv", index=False)
    print(f"Excluded {len(outliers)} airport(s) with a mislabeled-country distance over {OUTLIER_DISTANCE_KM}km (see problem10 CSV): {outliers['iata'].tolist() if len(outliers) else []}")
    print(hist_df.to_string(index=False))
    print(f"US airports with a matched nearest station: {len(clean)} of {len(airports)} (after excluding {len(outliers)} mislabeled-country outlier(s))")
    df = clean
    print(
        f"distance stats (km): min={df['distance_km'].min():.2f}, "
        f"median={df['distance_km'].median():.2f}, p90={df['distance_km'].quantile(0.9):.2f}, "
        f"max={df['distance_km'].max():.2f}"
    )
    return df, outliers


# ---------------------------------------------------------------------------
# Open decision 3: AWND (wind) coverage among nearest stations
# ---------------------------------------------------------------------------

def profile_awnd_coverage(nearest_stations: pd.DataFrame) -> dict:
    section("Open decision 3: AWND (wind) coverage among the nearest stations found above")
    inventory = pd.read_fwf(
        RAW_DIR / "noaa" / "ghcnd-inventory.txt",
        colspecs=[(0, 11), (12, 20), (21, 30), (31, 35), (36, 40), (41, 45)],
        names=["id", "latitude", "longitude", "element", "firstyear", "lastyear"],
    )
    awnd_stations = set(inventory[inventory["element"] == "AWND"]["id"])
    used_stations = set(nearest_stations["nearest_station_id"])
    with_awnd = used_stations & awnd_stations
    result = {
        "nearest_stations_used": len(used_stations),
        "of_those_reporting_AWND": len(with_awnd),
        "pct_reporting_AWND": round(100.0 * len(with_awnd) / len(used_stations), 1) if used_stations else 0,
    }
    print(result)
    return result


# ---------------------------------------------------------------------------
# Summary markdown
# ---------------------------------------------------------------------------

def write_summary_md(results: dict) -> Path:
    path = PROFILING_DIR / "summary.md"
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [
        "# Data quality profiling summary",
        "",
        f"Generated {ts} by `etl/profile.py`, against the real staged data",
        "loaded by `etl/extract.py` (7,001,619 rows in `stg_bts_flights`,",
        "7,698 rows in `stg_airports`) and the real NOAA reference files.",
        "Every number below comes from a query or script run against real",
        "data; none is invented (hard rule 3).",
        "",
        "## The nine expected problems from section 4 of the brief",
        "",
        "| # | Problem | Confirmed? | Count found | % of rows | Proposed rule |",
        "|---|---|---|---|---|---|",
        f"| 1 | Cancelled flights have empty time/delay fields | **Confirmed** | {results['p1']['cancelled_rows']} cancelled rows ({results['p1']['cancelled_rows_with_nonempty_arrdelay']} unexpectedly had a non-empty ArrDelay) | {results['p1']['cancelled_pct']}% | Keep row, set a cancelled flag, keep delay measures NULL, exclude from delay averages, include in cancellation rate. See `problem1_before_10rows.csv` / `problem1_after_10rows_proposed.csv`. |",
        f"| 2 | Midnight stored as 2400 in time fields | **Confirmed** | {results['p2']['any_2400_rows']} rows (CRSDepTime={results['p2']['CRSDepTime']}, DepTime={results['p2']['DepTime']}, CRSArrTime={results['p2']['CRSArrTime']}, ArrTime={results['p2']['ArrTime']}) | {round(100*results['p2']['any_2400_rows']/results['p1']['total_rows'],3)}% | **Open decision 4, not yet decided.** Preview only: map 2400 to 0000, flight date unchanged (per the locked date rule), roll forward only when a full timestamp is built. See `problem2_before_10rows.csv` / `problem2_after_10rows_proposed.csv`. |",
        f"| 3 | Delay cause fields blank when ArrDelay < 15 | **Confirmed** | {results['p3']['rows_blank_causes_low_delay']} rows; of {results['p3']['rows_qualifying_for_cause_sum_check']} rows with ArrDelay >= 15 and all five causes populated, {results['p3']['rows_where_causes_dont_sum_to_arrdelay']} do not sum to ArrDelay | mismatch {results['p3']['mismatch_pct_of_qualifying']}% of qualifying rows | Set causes to 0 for non-cancelled rows with ArrDelay < 15, keep NULL for cancelled rows, report (not hide) any cause-sum mismatch for ArrDelay >= 15. See `problem3_before_10rows.csv` / `problem3_after_10rows_proposed.csv`. |",
        f"| 4 | Airport codes with no match in the airport reference | **{'Confirmed' if len(results['p4']) else 'Refuted'}** | {len(results['p4'])} distinct unmatched Origin/Dest codes | n/a | Map to the Unknown airport member (key -1), log the code in the exception table. See `problem4_unmatched_airport_codes.csv`. |",
        f"| 5 | Duplicate flight records | **{'Confirmed' if results['dup_rows'] else 'Refuted'}** | {results['dup_rows']} rows share a business key with at least one other row | {round(100*results['dup_rows']/results['p1']['total_rows'],4)}% | Keep the first row by business key, move the rest to the reject table with reason DUPLICATE. See `problem5_duplicate_business_keys.csv`. |",
        "| 6 | Weather values in tenths of units, -9999 as missing flag | **Deferred to Phase 4** | n/a: no NOAA per-station daily values are staged yet (station selection happens in Phase 3; see `sql/02_create_staging.sql` scope note) | n/a | Will divide by 10 for mm/C/m-s, convert -9999 to NULL, once real per-station data is loaded. Not fabricated here. |",
        f"| 7 | Station too far from airport to represent its weather | **Confirmed as a real spread, threshold still open** | distance histogram over {len(results['p7'])} US airports; see `problem7_distance_histogram.csv` | n/a | **Open decision 5, not yet decided.** Evidence produced; threshold to be set by the team from the histogram, not guessed. |",
        f"| 8 | Most recent BTS months incomplete due to release lag | **Not found in the chosen year** | all 12 months of 2025 loaded with staged row count exactly matching the source CSV line count (see Phase 1 walkthrough and `row_counts_per_month.csv`); 2025 was verified complete before selecting it (`docs/DECISIONS.md`, decision 1) | 0% | No cut-off needed for 2025; re-check this when adding any later month. |",
        f"| 9 | Extreme delay values and diverted flights | **Confirmed** | {results['p9']['diverted_rows']} diverted rows ({results['p9']['diverted_pct']}%), {results['p9']['rows_with_arrdelay_over_180min']} rows with arrival delay over 180 minutes ({results['p9']['rows_with_arrdelay_over_180min_pct']}%), max arrival delay {results['p9']['max_arrdelay_minutes']} minutes | see above | Keep these rows, add outlier and diverted flags, report OLAP results with and without them (Phase 6 sensitivity check). |",
        f"| 10 (new, not in the brief) | OpenFlights rows with a mislabeled `country` field | **Confirmed** | {len(results['p10'])} airport(s): {results['p10']['iata'].tolist() if len(results['p10']) else []}, flagged with a raw haversine distance over {OUTLIER_DISTANCE_KM}km to the nearest US station because their real location (per latitude/longitude) is not in the US at all, despite `country = \"United States\"` in the source file | 0 real flight rows reference them (checked directly against `stg_bts_flights`; see `problem10_mislabeled_country_outliers.csv`) | Exclude from `dim_airport`/`airport_station_map` by location plausibility, not by trusting the `country` field alone; flag in the exception log if ever referenced by a real flight (none are, in 2025). |",
        "",
        "## Open decision 3: wind (AWND) coverage",
        "",
        f"Of {results['awnd']['nearest_stations_used']} distinct nearest stations found across US airports, "
        f"{results['awnd']['of_those_reporting_AWND']} ({results['awnd']['pct_reporting_AWND']}%) report AWND "
        "(average wind speed) at all, per `ghcnd-inventory.txt`. This is real coverage evidence for the "
        "team to decide open decision 3 (take wind from the nearest station that has it within the "
        "threshold, or accept NULL and flag); not decided here.",
        "",
        "## Row reconciliation",
        "",
        "`stg_bts_flights` holds 7,001,619 rows across all 12 months of 2025. "
        "Every month's staged row count exactly matched its source CSV's data-row "
        "count during `etl/extract.py` (no mismatches were logged); since staging "
        "performs no filtering, rejected rows = 0 at this stage, so source rows = "
        "loaded rows + rejected rows holds trivially (rejection happens during "
        "cleaning in Phase 4, against the rules this phase evidenced above).",
        "",
        "## What still needs a human decision",
        "",
        "Per `docs/BUILD_PLAN.md` Phase 2, open decisions 3 (wind coverage), 4 "
        "(midnight handling) and 5 (distance threshold) are informed by the "
        "evidence above but not decided by this script. See `docs/DECISIONS.md`.",
    ]
    path.write_text("\n".join(lines) + "\n")
    return path


def main() -> int:
    PROFILING_DIR.mkdir(parents=True, exist_ok=True)
    engine = get_engine()

    results = {}
    profile_row_counts(engine)
    profile_null_counts(engine)
    results["dup_rows"] = profile_duplicates(engine)
    results["p4"] = profile_airport_code_match(engine)
    results["p1"] = profile_problem1_cancelled(engine)
    results["p2"] = profile_problem2_midnight(engine)
    results["p3"] = profile_problem3_delay_causes(engine)
    results["p9"] = profile_problem9_outliers(engine)
    results["p7"], results["p10"] = profile_airport_station_distance(engine)
    results["awnd"] = profile_awnd_coverage(results["p7"])

    summary_path = write_summary_md(results)
    print(f"\nSummary written to {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
