"""Loads S1 (BTS flights) and S3 (OpenFlights airports) into staging.

Every source column is loaded as text, unmodified (hard rule 1 in
CLAUDE.md: no casting, trimming or cleaning happens here). Each run of
this script gets one load_id (a UUID), shared by every row loaded in
that run; source_file records which physical file a row came from, so
any staged row can be traced back to it.

S2 (NOAA) is not staged as a table in this phase: only its small
reference files (ghcnd-stations.txt, ghcnd-inventory.txt) are used,
directly via pandas in etl/profile.py, to build the distance histogram
and AWND coverage check needed for open decisions 3 and 5. S4 (BTS
lookup tables) is not staged: it is blocked, see docs/DECISIONS.md,
item B1.

Usage:
    python -m etl.extract              # (re)load both S1 and S3
    python -m etl.extract --only s1    # just BTS flights
    python -m etl.extract --only s3    # just OpenFlights airports
"""
import argparse
import sys
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import pandas as pd
from sqlalchemy.engine import Engine

from etl.db import get_engine

ROOT_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT_DIR / "data" / "raw"
SQL_DIR = ROOT_DIR / "sql"
LOG_DIR = ROOT_DIR / "logs"

AIRPORT_COLUMNS = [
    "airport_id",
    "name",
    "city",
    "country",
    "iata",
    "icao",
    "latitude",
    "longitude",
    "altitude",
    "tz_offset",
    "dst",
    "tz_database_name",
    "airport_type",
    "source",
]

METADATA_COLUMNS = {"load_id", "source_file", "load_timestamp"}

LOG_LINES: List[str] = []


def log(line: str) -> None:
    stamped = f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {line}"
    print(stamped, flush=True)
    LOG_LINES.append(stamped)


def run_sql_file(engine: Engine, path: Path) -> None:
    # Strips a trailing "-- comment" from each line, not just lines that
    # are entirely a comment: sql/03_create_warehouse.sql has several
    # inline comments after real SQL on the same line (e.g. "col TEXT, --
    # note"), which a whole-line-only filter leaves in place, corrupting
    # the statement. None of this project's SQL files use "--" inside a
    # quoted string, so a plain split is safe here.
    kept_lines = [line.split("--", 1)[0] for line in path.read_text().splitlines()]
    sql_text = "\n".join(kept_lines)
    statements = [s.strip() for s in sql_text.split(";") if s.strip()]
    with engine.begin() as conn:
        for stmt in statements:
            conn.exec_driver_sql(stmt)


def table_columns(engine: Engine, table: str) -> List[str]:
    with engine.connect() as conn:
        rows = conn.exec_driver_sql(f"SHOW COLUMNS FROM {table}").fetchall()
    names = [r[0] for r in rows]
    return [n for n in names if n not in METADATA_COLUMNS]


def count_csv_data_lines(path: Path, has_header: bool) -> int:
    count = 0
    with open(path, "rb") as f:
        for _ in f:
            count += 1
    return count - 1 if has_header else count


def load_file_local_infile(
    engine: Engine,
    csv_path: Path,
    table: str,
    columns: List[str],
    load_id: str,
    source_file: str,
    has_header: bool,
    trailing_phantom_field: bool,
) -> int:
    col_list = list(columns)
    if trailing_phantom_field:
        col_list = col_list + ["@__phantom"]
    columns_clause = ", ".join(col_list)
    ignore_clause = "IGNORE 1 LINES" if has_header else ""
    load_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    sql = f"""
        LOAD DATA LOCAL INFILE '{csv_path.as_posix()}'
        INTO TABLE {table}
        FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
        LINES TERMINATED BY '\\n'
        {ignore_clause}
        ({columns_clause})
        SET load_id = '{load_id}', source_file = '{source_file}', load_timestamp = '{load_ts}'
    """
    with engine.begin() as conn:
        result = conn.exec_driver_sql(sql)
        return result.rowcount


def extract_s1_bts(engine: Engine, load_id: str) -> None:
    log("== Loading S1 BTS flights into stg_bts_flights ==")
    columns = table_columns(engine, "stg_bts_flights")
    zip_paths = sorted((RAW_DIR / "bts").glob("*.zip"))
    if not zip_paths:
        log("No BTS zip files found in data/raw/bts/. Run data/download_sources.py first.")
        return
    with tempfile.TemporaryDirectory(prefix="flight_dw_extract_") as tmpdir:
        for zip_path in zip_paths:
            with zipfile.ZipFile(zip_path) as zf:
                csv_members = [n for n in zf.namelist() if n.lower().endswith(".csv")]
                if len(csv_members) != 1:
                    log(f"FAIL  {zip_path.name}: expected exactly one CSV member, found {csv_members}")
                    continue
                extracted_path = Path(zf.extract(csv_members[0], path=tmpdir))

            source_rows = count_csv_data_lines(extracted_path, has_header=True)
            loaded_rows = load_file_local_infile(
                engine,
                extracted_path,
                table="stg_bts_flights",
                columns=columns,
                load_id=load_id,
                source_file=zip_path.name,
                has_header=True,
                trailing_phantom_field=True,
            )
            status = "OK" if loaded_rows == source_rows else "MISMATCH"
            log(
                f"{status:<9} {zip_path.name}: csv data rows={source_rows}, "
                f"loaded rows={loaded_rows}"
            )
            extracted_path.unlink(missing_ok=True)


def extract_s3_airports(engine: Engine, load_id: str) -> None:
    log("== Loading S3 OpenFlights airports into stg_airports ==")
    dat_path = RAW_DIR / "openflights" / "airports.dat"
    if not dat_path.exists():
        log("airports.dat not found in data/raw/openflights/. Run data/download_sources.py first.")
        return
    source_rows = count_csv_data_lines(dat_path, has_header=False)
    loaded_rows = load_file_local_infile(
        engine,
        dat_path,
        table="stg_airports",
        columns=AIRPORT_COLUMNS,
        load_id=load_id,
        source_file=dat_path.name,
        has_header=False,
        trailing_phantom_field=False,
    )
    status = "OK" if loaded_rows == source_rows else "MISMATCH"
    log(f"{status:<9} {dat_path.name}: dat data rows={source_rows}, loaded rows={loaded_rows}")


NOAA_NEEDED_ELEMENTS = {"PRCP", "SNOW", "SNWD", "TMAX", "TMIN", "AWND"}
NOAA_CHUNK_ROWS = 2_000_000


def extract_s2_noaa_daily(engine: Engine, load_id: str, year: int) -> None:
    """Filters NOAA's by_year bulk file down to the stations in
    airport_station_map and the six elements this warehouse uses, then
    stages the result. Requires airport_station_map to already be
    populated (etl/load_dims.py's dim_airport/station-map step), which
    is why this runs after that step, not alongside S1/S3.
    """
    log("== Loading S2 NOAA daily weather (filtered) into stg_noaa_daily ==")
    gz_path = RAW_DIR / "noaa" / f"by_year_{year}.csv.gz"
    if not gz_path.exists():
        log(
            f"{gz_path.name} not found in data/raw/noaa/. Run "
            f"'python data/download_sources.py --only s2-daily --year {year}' first."
        )
        return

    with engine.connect() as conn:
        station_rows = conn.exec_driver_sql("SELECT DISTINCT station_id FROM airport_station_map").fetchall()
    if not station_rows:
        log("airport_station_map is empty. Run etl.load_dims's dim_airport/station-map step first.")
        return
    needed_stations = {s for (s,) in station_rows}
    log(f"Filtering for {len(needed_stations)} stations and elements {sorted(NOAA_NEEDED_ELEMENTS)}")

    source_rows = 0
    kept_rows = 0
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, prefix="flight_dw_noaa_daily_"
    ) as tmp:
        tmp_path = Path(tmp.name)
        reader = pd.read_csv(
            gz_path,
            header=None,
            names=["station_id", "obs_date", "element", "raw_value", "m_flag", "q_flag", "s_flag", "obs_time"],
            dtype=str,
            chunksize=NOAA_CHUNK_ROWS,
            compression="gzip",
            keep_default_na=False,
        )
        for chunk in reader:
            source_rows += len(chunk)
            mask = chunk["station_id"].isin(needed_stations) & chunk["element"].isin(NOAA_NEEDED_ELEMENTS)
            kept = chunk[mask]
            kept_rows += len(kept)
            kept.to_csv(tmp, header=False, index=False, mode="a")

    loaded_rows = load_file_local_infile(
        engine,
        tmp_path,
        table="stg_noaa_daily",
        columns=["station_id", "obs_date", "element", "raw_value", "m_flag", "q_flag", "s_flag", "obs_time"],
        load_id=load_id,
        source_file=gz_path.name,
        has_header=False,
        trailing_phantom_field=False,
    )
    tmp_path.unlink(missing_ok=True)
    status = "OK" if loaded_rows == kept_rows else "MISMATCH"
    log(
        f"{status:<9} {gz_path.name}: {source_rows} global rows scanned, "
        f"{kept_rows} kept for our stations/elements, loaded rows={loaded_rows}"
    )


def write_log_file(load_id: str) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = LOG_DIR / f"extract_{ts}_{load_id[:8]}.log"
    path.write_text("\n".join(LOG_LINES) + "\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=["s1", "s3", "s2-daily"], action="append")
    env_year = __import__("os").environ.get("DATA_YEAR")
    parser.add_argument("--year", type=int, default=int(env_year) if env_year else None)
    parser.add_argument(
        "--skip-schema",
        action="store_true",
        help="skip re-running sql/01 and sql/02 (avoids truncating stg_bts_flights/stg_airports "
        "when only reloading stg_noaa_daily)",
    )
    args = parser.parse_args()
    which = set(args.only) if args.only else {"s1", "s3"}

    engine = get_engine(local_infile=True)

    if not args.skip_schema:
        log("Applying sql/01_create_schemas.sql and sql/02_create_staging.sql")
        run_sql_file(engine, SQL_DIR / "01_create_schemas.sql")
        run_sql_file(engine, SQL_DIR / "02_create_staging.sql")

    load_id = str(uuid.uuid4())
    log(f"load_id for this run: {load_id}")

    if "s1" in which:
        extract_s1_bts(engine, load_id)
    if "s3" in which:
        extract_s3_airports(engine, load_id)
    if "s2-daily" in which:
        if args.year is None:
            log("No data year given for s2-daily. Set DATA_YEAR in .env or pass --year.")
        else:
            extract_s2_noaa_daily(engine, load_id, args.year)

    log_path = write_log_file(load_id)
    log(f"Full log written to {log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
