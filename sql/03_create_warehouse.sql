-- 03_create_warehouse.sql
--
-- The star schema itself: two facts, seven dimensions, plus
-- airport_station_map, reject_flights, exception_log and audit_log.
-- Idempotent: drops in dependency order (children before parents) then
-- recreates, so this runs cleanly on an empty database and on a
-- database that already has this schema.
--
-- Every dimension carries a -1 "Unknown" row, inserted here rather
-- than in Phase 4's load scripts, because the Phase 3 acceptance check
-- requires it to exist as soon as the schema does.
--
-- dim_date and dim_time_of_day are NOT populated with real calendar
-- rows here. Generating those is Phase 4's job (etl/load_dims.py); this
-- script only creates the table shape and the -1 row.
--
-- Open decisions 3 (wind coverage), 4 (midnight handling) and 5
-- (distance threshold) do not change anything below: the columns here
-- (nullable measures, a within_threshold flag) already accommodate any
-- way the team eventually decides those. See docs/DECISIONS.md.

USE flight_dw;

SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS fact_flight;
DROP TABLE IF EXISTS fact_airport_weather_daily;
DROP TABLE IF EXISTS airport_station_map;
DROP TABLE IF EXISTS dim_route;
DROP TABLE IF EXISTS dim_flight_status;
DROP TABLE IF EXISTS dim_weather_condition;
DROP TABLE IF EXISTS dim_carrier;
DROP TABLE IF EXISTS dim_airport;
DROP TABLE IF EXISTS dim_time_of_day;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS reject_flights;
DROP TABLE IF EXISTS exception_log;
DROP TABLE IF EXISTS audit_log;

SET FOREIGN_KEY_CHECKS = 1;

-- ---------------------------------------------------------------------
-- Dimensions
-- ---------------------------------------------------------------------

CREATE TABLE dim_date (
    date_key INT PRIMARY KEY,                  -- yyyymmdd, e.g. 20250101
    full_date DATE NOT NULL,
    day_of_month TINYINT NOT NULL,
    day_of_week_num TINYINT NOT NULL,          -- 1 = Monday .. 7 = Sunday
    day_of_week_name VARCHAR(9) NOT NULL,
    week_of_year TINYINT NOT NULL,
    month_num TINYINT NOT NULL,
    month_name VARCHAR(9) NOT NULL,
    quarter TINYINT NOT NULL,
    year SMALLINT NOT NULL,
    is_weekend BOOLEAN NOT NULL,
    is_us_holiday BOOLEAN NOT NULL,
    holiday_name VARCHAR(50) NULL,
    season VARCHAR(10) NOT NULL,
    INDEX ix_dim_date_year_month (year, month_num)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO dim_date (
    date_key, full_date, day_of_month, day_of_week_num, day_of_week_name,
    week_of_year, month_num, month_name, quarter, year, is_weekend,
    is_us_holiday, holiday_name, season
) VALUES (
    -1, '1900-01-01', 0, 0, 'Unknown', 0, 0, 'Unknown', 0, 0, FALSE,
    FALSE, NULL, 'Unknown'
);

CREATE TABLE dim_time_of_day (
    time_key INT PRIMARY KEY,
    hour_of_day TINYINT NOT NULL,              -- 0-23
    departure_band VARCHAR(20) NOT NULL        -- early morning/morning/afternoon/evening/night
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO dim_time_of_day (time_key, hour_of_day, departure_band)
VALUES (-1, -1, 'Unknown');

CREATE TABLE dim_airport (
    airport_key INT AUTO_INCREMENT PRIMARY KEY,
    iata_code CHAR(3) NOT NULL,
    icao_code CHAR(4) NULL,
    name VARCHAR(100) NOT NULL,
    city VARCHAR(100) NULL,
    state CHAR(2) NULL,
    country VARCHAR(60) NULL,
    latitude DECIMAL(9,6) NULL,
    longitude DECIMAL(9,6) NULL,
    tz_database_name VARCHAR(50) NULL,
    nearest_station_id CHAR(11) NULL,          -- denormalized convenience copy; airport_station_map is authoritative
    traffic_tier VARCHAR(20) NULL,
    UNIQUE KEY uq_dim_airport_iata (iata_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO dim_airport (
    airport_key, iata_code, icao_code, name, city, state, country,
    latitude, longitude, tz_database_name, nearest_station_id, traffic_tier
) VALUES (
    -1, 'UNK', NULL, 'Unknown', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
);

CREATE TABLE dim_carrier (
    carrier_key INT AUTO_INCREMENT PRIMARY KEY,
    carrier_code CHAR(2) NOT NULL,
    carrier_name VARCHAR(100) NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE NULL,                    -- NULL = still current
    is_current BOOLEAN NOT NULL,
    INDEX ix_dim_carrier_code (carrier_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO dim_carrier (
    carrier_key, carrier_code, carrier_name, effective_from, effective_to, is_current
) VALUES (
    -1, 'XX', 'Unknown', '1900-01-01', NULL, TRUE
);

CREATE TABLE dim_route (
    route_key INT AUTO_INCREMENT PRIMARY KEY,
    origin_iata CHAR(3) NOT NULL,
    dest_iata CHAR(3) NOT NULL,
    distance_miles DECIMAL(8,2) NULL,
    distance_band VARCHAR(20) NULL,
    UNIQUE KEY uq_dim_route_pair (origin_iata, dest_iata)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO dim_route (
    route_key, origin_iata, dest_iata, distance_miles, distance_band
) VALUES (
    -1, 'UNK', 'UNK', NULL, 'Unknown'
);

CREATE TABLE dim_flight_status (
    flight_status_key INT AUTO_INCREMENT PRIMARY KEY,
    cancelled_flag BOOLEAN NOT NULL,
    cancellation_reason_code CHAR(1) NULL,     -- raw BTS code (A/B/C/D); description pending S4 (see docs/DECISIONS.md, item B1)
    diverted_flag BOOLEAN NOT NULL,
    delay_class VARCHAR(20) NOT NULL,
    UNIQUE KEY uq_dim_flight_status_combo (cancelled_flag, cancellation_reason_code, diverted_flag, delay_class)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO dim_flight_status (
    flight_status_key, cancelled_flag, cancellation_reason_code, diverted_flag, delay_class
) VALUES (
    -1, FALSE, NULL, FALSE, 'Unknown'
);

CREATE TABLE dim_weather_condition (
    weather_condition_key INT AUTO_INCREMENT PRIMARY KEY,
    precip_band VARCHAR(20) NOT NULL,
    snow_band VARCHAR(20) NOT NULL,
    wind_band VARCHAR(20) NOT NULL,
    temp_band VARCHAR(20) NOT NULL,
    UNIQUE KEY uq_dim_weather_condition_combo (precip_band, snow_band, wind_band, temp_band)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO dim_weather_condition (
    weather_condition_key, precip_band, snow_band, wind_band, temp_band
) VALUES (
    -1, 'Unknown', 'Unknown', 'Unknown', 'Unknown'
);

-- ---------------------------------------------------------------------
-- Airport to nearest station map (not a dimension; a mapping table used
-- to build dim_airport.nearest_station_id and fact_airport_weather_daily)
-- ---------------------------------------------------------------------

CREATE TABLE airport_station_map (
    airport_key INT PRIMARY KEY,
    station_id CHAR(11) NOT NULL,
    distance_km DECIMAL(7,2) NOT NULL,
    within_threshold BOOLEAN NOT NULL,         -- threshold value set in Phase 4, open decision 5
    CONSTRAINT fk_station_map_airport FOREIGN KEY (airport_key) REFERENCES dim_airport (airport_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- Facts
-- ---------------------------------------------------------------------

CREATE TABLE fact_airport_weather_daily (
    date_key INT NOT NULL,
    airport_key INT NOT NULL,
    weather_condition_key INT NOT NULL DEFAULT -1,
    precip_mm DECIMAL(6,2) NULL,
    snowfall_mm DECIMAL(6,2) NULL,
    snow_depth_mm DECIMAL(6,2) NULL,
    avg_wind_ms DECIMAL(5,2) NULL,              -- nullable regardless of open decision 3's outcome
    tmax_c DECIMAL(5,2) NULL,
    tmin_c DECIMAL(5,2) NULL,
    station_distance_km DECIMAL(7,2) NULL,
    PRIMARY KEY (date_key, airport_key),
    CONSTRAINT fk_weather_daily_date FOREIGN KEY (date_key) REFERENCES dim_date (date_key),
    CONSTRAINT fk_weather_daily_airport FOREIGN KEY (airport_key) REFERENCES dim_airport (airport_key),
    CONSTRAINT fk_weather_daily_condition FOREIGN KEY (weather_condition_key) REFERENCES dim_weather_condition (weather_condition_key),
    INDEX ix_weather_daily_airport (airport_key),
    INDEX ix_weather_daily_condition (weather_condition_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE fact_flight (
    flight_key BIGINT AUTO_INCREMENT PRIMARY KEY,
    date_key INT NOT NULL DEFAULT -1,
    dep_time_key INT NOT NULL DEFAULT -1,
    origin_airport_key INT NOT NULL DEFAULT -1,
    dest_airport_key INT NOT NULL DEFAULT -1,
    carrier_key INT NOT NULL DEFAULT -1,
    route_key INT NOT NULL DEFAULT -1,
    flight_status_key INT NOT NULL DEFAULT -1,
    origin_weather_key INT NOT NULL DEFAULT -1,
    dest_weather_key INT NOT NULL DEFAULT -1,  -- open decision 2, resolved: added for symmetry with origin_weather_key
    flight_number VARCHAR(10) NOT NULL,        -- degenerate dimension
    tail_number VARCHAR(10) NULL,              -- degenerate dimension
    scheduled_dep_time SMALLINT NOT NULL,      -- raw HHMM (0-2359); dep_time_key is a coarser band, see docs/walkthrough/phase3.md
    dep_delay_min SMALLINT NULL,
    arr_delay_min SMALLINT NULL,
    carrier_delay_min SMALLINT NULL,
    weather_delay_min SMALLINT NULL,
    nas_delay_min SMALLINT NULL,
    security_delay_min SMALLINT NULL,
    late_aircraft_delay_min SMALLINT NULL,
    taxi_out_min SMALLINT NULL,
    taxi_in_min SMALLINT NULL,
    distance_miles DECIMAL(6,1) NULL,
    flight_count TINYINT NOT NULL DEFAULT 1,
    on_time_flag BOOLEAN NULL,                 -- NULL for cancelled flights, where on-time does not apply
    is_outlier_delay BOOLEAN NULL,             -- threshold decided in Phase 4; beyond the brief's literal list, added per Phase 2 problem 9 evidence
    CONSTRAINT uq_fact_flight_business_key UNIQUE (
        date_key, carrier_key, flight_number, origin_airport_key, dest_airport_key, scheduled_dep_time
    ),
    CONSTRAINT fk_flight_date FOREIGN KEY (date_key) REFERENCES dim_date (date_key),
    CONSTRAINT fk_flight_dep_time FOREIGN KEY (dep_time_key) REFERENCES dim_time_of_day (time_key),
    CONSTRAINT fk_flight_origin_airport FOREIGN KEY (origin_airport_key) REFERENCES dim_airport (airport_key),
    CONSTRAINT fk_flight_dest_airport FOREIGN KEY (dest_airport_key) REFERENCES dim_airport (airport_key),
    CONSTRAINT fk_flight_carrier FOREIGN KEY (carrier_key) REFERENCES dim_carrier (carrier_key),
    CONSTRAINT fk_flight_route FOREIGN KEY (route_key) REFERENCES dim_route (route_key),
    CONSTRAINT fk_flight_status FOREIGN KEY (flight_status_key) REFERENCES dim_flight_status (flight_status_key),
    CONSTRAINT fk_flight_origin_weather FOREIGN KEY (origin_weather_key) REFERENCES dim_weather_condition (weather_condition_key),
    CONSTRAINT fk_flight_dest_weather FOREIGN KEY (dest_weather_key) REFERENCES dim_weather_condition (weather_condition_key),
    INDEX ix_flight_date (date_key),
    INDEX ix_flight_dep_time (dep_time_key),
    INDEX ix_flight_origin_airport (origin_airport_key),
    INDEX ix_flight_dest_airport (dest_airport_key),
    INDEX ix_flight_carrier (carrier_key),
    INDEX ix_flight_route (route_key),
    INDEX ix_flight_status (flight_status_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- Traceability tables (hard rules 1 and 2: nothing is silently modified
-- or dropped)
-- ---------------------------------------------------------------------

CREATE TABLE reject_flights (
    reject_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    load_id CHAR(36) NOT NULL,
    source_file VARCHAR(255) NOT NULL,
    reason_code VARCHAR(50) NOT NULL,          -- e.g. DUPLICATE
    reason_detail VARCHAR(255) NULL,
    raw_row JSON NOT NULL,
    rejected_at DATETIME NOT NULL,
    INDEX ix_reject_flights_load (load_id),
    INDEX ix_reject_flights_reason (reason_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE exception_log (
    exception_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    load_id CHAR(36) NOT NULL,
    source_table VARCHAR(100) NOT NULL,
    natural_key VARCHAR(255) NOT NULL,         -- e.g. the unmatched airport or carrier code
    exception_type VARCHAR(50) NOT NULL,       -- e.g. UNKNOWN_AIRPORT_CODE, UNKNOWN_CARRIER_CODE
    detail VARCHAR(255) NULL,
    logged_at DATETIME NOT NULL,
    INDEX ix_exception_log_load (load_id),
    INDEX ix_exception_log_type (exception_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE audit_log (
    audit_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    load_id CHAR(36) NOT NULL,
    stage_name VARCHAR(100) NOT NULL,          -- e.g. extract_s1_bts, load_dim_date
    source_file VARCHAR(255) NULL,
    rows_in INT NULL,
    rows_out INT NULL,
    rows_rejected INT NULL,
    started_at DATETIME NOT NULL,
    finished_at DATETIME NULL,
    status VARCHAR(20) NOT NULL,               -- e.g. success, failed
    message VARCHAR(500) NULL,
    INDEX ix_audit_log_load (load_id),
    INDEX ix_audit_log_stage (stage_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
