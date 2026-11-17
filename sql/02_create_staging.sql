-- 02_create_staging.sql
--
-- Staging tables. Every source column is TEXT: no casting, trimming or
-- cleaning happens here (hard rule 1 in CLAUDE.md). load_id identifies
-- one run of etl/extract.py (a UUID, shared by every row loaded in that
-- run); source_file is the exact file a row came from; load_timestamp
-- is when it was loaded. Staging is truncate-and-reload, so no
-- secondary indexes are added here (BUILD_PLAN: add indexes after bulk
-- load, not before, and staging is not queried the way the warehouse
-- is).
--
-- Column names and order for stg_bts_flights are taken from the real
-- header of the downloaded BTS file (see docs/source_columns.md), not
-- the brief's summary list. The source file has a trailing comma on
-- every line, producing an unnamed 110th field that is always empty;
-- etl/extract.py's LOAD DATA statement discards it rather than
-- persisting a meaningless column.
--
-- Scope note (Phase 2): S1 (BTS flights) and S3 (OpenFlights airports)
-- were staged first. S4 (BTS lookup tables) is blocked (see
-- docs/DECISIONS.md, item B1): its staging tables are not created until
-- a real file exists to load, so their structure is not guessed.
-- stg_noaa_daily was added in Phase 4, once airport_station_map existed
-- and the stations to keep were known (NOAA's by_year bulk file,
-- data/download_sources.py --only s2-daily, filtered to the matched
-- stations and the six elements this warehouse uses). Before that,
-- only NOAA's small station list and inventory were used, directly
-- from the raw text files via pandas (for the distance histogram and
-- AWND coverage check): reference data read transiently, not fact
-- data, so they are not staged as a table (matching the brief's own
-- staging table list in section 6/7, which
-- does not include them).

USE flight_dw;

DROP TABLE IF EXISTS stg_bts_flights;
CREATE TABLE stg_bts_flights (
    Year TEXT,
    Quarter TEXT,
    Month TEXT,
    DayofMonth TEXT,
    DayOfWeek TEXT,
    FlightDate TEXT,
    Reporting_Airline TEXT,
    DOT_ID_Reporting_Airline TEXT,
    IATA_CODE_Reporting_Airline TEXT,
    Tail_Number TEXT,
    Flight_Number_Reporting_Airline TEXT,
    OriginAirportID TEXT,
    OriginAirportSeqID TEXT,
    OriginCityMarketID TEXT,
    Origin TEXT,
    OriginCityName TEXT,
    OriginState TEXT,
    OriginStateFips TEXT,
    OriginStateName TEXT,
    OriginWac TEXT,
    DestAirportID TEXT,
    DestAirportSeqID TEXT,
    DestCityMarketID TEXT,
    Dest TEXT,
    DestCityName TEXT,
    DestState TEXT,
    DestStateFips TEXT,
    DestStateName TEXT,
    DestWac TEXT,
    CRSDepTime TEXT,
    DepTime TEXT,
    DepDelay TEXT,
    DepDelayMinutes TEXT,
    DepDel15 TEXT,
    DepartureDelayGroups TEXT,
    DepTimeBlk TEXT,
    TaxiOut TEXT,
    WheelsOff TEXT,
    WheelsOn TEXT,
    TaxiIn TEXT,
    CRSArrTime TEXT,
    ArrTime TEXT,
    ArrDelay TEXT,
    ArrDelayMinutes TEXT,
    ArrDel15 TEXT,
    ArrivalDelayGroups TEXT,
    ArrTimeBlk TEXT,
    Cancelled TEXT,
    CancellationCode TEXT,
    Diverted TEXT,
    CRSElapsedTime TEXT,
    ActualElapsedTime TEXT,
    AirTime TEXT,
    Flights TEXT,
    Distance TEXT,
    DistanceGroup TEXT,
    CarrierDelay TEXT,
    WeatherDelay TEXT,
    NASDelay TEXT,
    SecurityDelay TEXT,
    LateAircraftDelay TEXT,
    FirstDepTime TEXT,
    TotalAddGTime TEXT,
    LongestAddGTime TEXT,
    DivAirportLandings TEXT,
    DivReachedDest TEXT,
    DivActualElapsedTime TEXT,
    DivArrDelay TEXT,
    DivDistance TEXT,
    Div1Airport TEXT,
    Div1AirportID TEXT,
    Div1AirportSeqID TEXT,
    Div1WheelsOn TEXT,
    Div1TotalGTime TEXT,
    Div1LongestGTime TEXT,
    Div1WheelsOff TEXT,
    Div1TailNum TEXT,
    Div2Airport TEXT,
    Div2AirportID TEXT,
    Div2AirportSeqID TEXT,
    Div2WheelsOn TEXT,
    Div2TotalGTime TEXT,
    Div2LongestGTime TEXT,
    Div2WheelsOff TEXT,
    Div2TailNum TEXT,
    Div3Airport TEXT,
    Div3AirportID TEXT,
    Div3AirportSeqID TEXT,
    Div3WheelsOn TEXT,
    Div3TotalGTime TEXT,
    Div3LongestGTime TEXT,
    Div3WheelsOff TEXT,
    Div3TailNum TEXT,
    Div4Airport TEXT,
    Div4AirportID TEXT,
    Div4AirportSeqID TEXT,
    Div4WheelsOn TEXT,
    Div4TotalGTime TEXT,
    Div4LongestGTime TEXT,
    Div4WheelsOff TEXT,
    Div4TailNum TEXT,
    Div5Airport TEXT,
    Div5AirportID TEXT,
    Div5AirportSeqID TEXT,
    Div5WheelsOn TEXT,
    Div5TotalGTime TEXT,
    Div5LongestGTime TEXT,
    Div5WheelsOff TEXT,
    Div5TailNum TEXT,
    load_id CHAR(36) NOT NULL,
    source_file VARCHAR(255) NOT NULL,
    load_timestamp DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

DROP TABLE IF EXISTS stg_airports;
CREATE TABLE stg_airports (
    airport_id TEXT,
    name TEXT,
    city TEXT,
    country TEXT,
    iata TEXT,
    icao TEXT,
    latitude TEXT,
    longitude TEXT,
    altitude TEXT,
    tz_offset TEXT,
    dst TEXT,
    tz_database_name TEXT,
    airport_type TEXT,
    source TEXT,
    load_id CHAR(36) NOT NULL,
    source_file VARCHAR(255) NOT NULL,
    load_timestamp DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Columns per NOAA's documented GHCN-Daily "by_year" format, verified
-- against the real downloaded file: id, date, element, value, m-flag,
-- q-flag, s-flag, obs-time, no header row. Only rows for stations in
-- airport_station_map and elements PRCP/SNOW/SNWD/TMAX/TMIN/AWND are
-- kept; see etl/extract.py.
DROP TABLE IF EXISTS stg_noaa_daily;
CREATE TABLE stg_noaa_daily (
    station_id TEXT,
    obs_date TEXT,
    element TEXT,
    raw_value TEXT,
    m_flag TEXT,
    q_flag TEXT,
    s_flag TEXT,
    obs_time TEXT,
    load_id CHAR(36) NOT NULL,
    source_file VARCHAR(255) NOT NULL,
    load_timestamp DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
