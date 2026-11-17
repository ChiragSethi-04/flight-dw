-- schema_dump.sql
-- Real output of SHOW CREATE TABLE for every table, captured 2026-11-17 after
-- running sql/01, sql/02, sql/03 against a live MySQL 8 container.

-- ---- dim_date ----
*************************** 1. row ***************************
dim_date
CREATE TABLE `dim_date` (
  `date_key` int NOT NULL,
  `full_date` date NOT NULL,
  `day_of_month` tinyint NOT NULL,
  `day_of_week_num` tinyint NOT NULL,
  `day_of_week_name` varchar(9) NOT NULL,
  `week_of_year` tinyint NOT NULL,
  `month_num` tinyint NOT NULL,
  `month_name` varchar(9) NOT NULL,
  `quarter` tinyint NOT NULL,
  `year` smallint NOT NULL,
  `is_weekend` tinyint(1) NOT NULL,
  `is_us_holiday` tinyint(1) NOT NULL,
  `holiday_name` varchar(50) DEFAULT NULL,
  `season` varchar(10) NOT NULL,
  PRIMARY KEY (`date_key`),
  KEY `ix_dim_date_year_month` (`year`,`month_num`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci

-- ---- dim_time_of_day ----
*************************** 1. row ***************************
dim_time_of_day
CREATE TABLE `dim_time_of_day` (
  `time_key` int NOT NULL,
  `hour_of_day` tinyint NOT NULL,
  `departure_band` varchar(20) NOT NULL,
  PRIMARY KEY (`time_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci

-- ---- dim_airport ----
*************************** 1. row ***************************
dim_airport
CREATE TABLE `dim_airport` (
  `airport_key` int NOT NULL AUTO_INCREMENT,
  `iata_code` char(3) NOT NULL,
  `icao_code` char(4) DEFAULT NULL,
  `name` varchar(100) NOT NULL,
  `city` varchar(100) DEFAULT NULL,
  `state` char(2) DEFAULT NULL,
  `country` varchar(60) DEFAULT NULL,
  `latitude` decimal(9,6) DEFAULT NULL,
  `longitude` decimal(9,6) DEFAULT NULL,
  `tz_database_name` varchar(50) DEFAULT NULL,
  `nearest_station_id` char(11) DEFAULT NULL,
  `traffic_tier` varchar(20) DEFAULT NULL,
  PRIMARY KEY (`airport_key`),
  UNIQUE KEY `uq_dim_airport_iata` (`iata_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci

-- ---- dim_carrier ----
*************************** 1. row ***************************
dim_carrier
CREATE TABLE `dim_carrier` (
  `carrier_key` int NOT NULL AUTO_INCREMENT,
  `carrier_code` char(2) NOT NULL,
  `carrier_name` varchar(100) NOT NULL,
  `effective_from` date NOT NULL,
  `effective_to` date DEFAULT NULL,
  `is_current` tinyint(1) NOT NULL,
  PRIMARY KEY (`carrier_key`),
  KEY `ix_dim_carrier_code` (`carrier_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci

-- ---- dim_route ----
*************************** 1. row ***************************
dim_route
CREATE TABLE `dim_route` (
  `route_key` int NOT NULL AUTO_INCREMENT,
  `origin_iata` char(3) NOT NULL,
  `dest_iata` char(3) NOT NULL,
  `distance_miles` decimal(8,2) DEFAULT NULL,
  `distance_band` varchar(20) DEFAULT NULL,
  PRIMARY KEY (`route_key`),
  UNIQUE KEY `uq_dim_route_pair` (`origin_iata`,`dest_iata`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci

-- ---- dim_flight_status ----
*************************** 1. row ***************************
dim_flight_status
CREATE TABLE `dim_flight_status` (
  `flight_status_key` int NOT NULL AUTO_INCREMENT,
  `cancelled_flag` tinyint(1) NOT NULL,
  `cancellation_reason_code` char(1) DEFAULT NULL,
  `diverted_flag` tinyint(1) NOT NULL,
  `delay_class` varchar(20) NOT NULL,
  PRIMARY KEY (`flight_status_key`),
  UNIQUE KEY `uq_dim_flight_status_combo` (`cancelled_flag`,`cancellation_reason_code`,`diverted_flag`,`delay_class`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci

-- ---- dim_weather_condition ----
*************************** 1. row ***************************
dim_weather_condition
CREATE TABLE `dim_weather_condition` (
  `weather_condition_key` int NOT NULL AUTO_INCREMENT,
  `precip_band` varchar(20) NOT NULL,
  `snow_band` varchar(20) NOT NULL,
  `wind_band` varchar(20) NOT NULL,
  `temp_band` varchar(20) NOT NULL,
  PRIMARY KEY (`weather_condition_key`),
  UNIQUE KEY `uq_dim_weather_condition_combo` (`precip_band`,`snow_band`,`wind_band`,`temp_band`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci

-- ---- airport_station_map ----
*************************** 1. row ***************************
airport_station_map
CREATE TABLE `airport_station_map` (
  `airport_key` int NOT NULL,
  `station_id` char(11) NOT NULL,
  `distance_km` decimal(7,2) NOT NULL,
  `within_threshold` tinyint(1) NOT NULL,
  PRIMARY KEY (`airport_key`),
  CONSTRAINT `fk_station_map_airport` FOREIGN KEY (`airport_key`) REFERENCES `dim_airport` (`airport_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci

-- ---- fact_airport_weather_daily ----
*************************** 1. row ***************************
fact_airport_weather_daily
CREATE TABLE `fact_airport_weather_daily` (
  `date_key` int NOT NULL,
  `airport_key` int NOT NULL,
  `weather_condition_key` int NOT NULL DEFAULT '-1',
  `precip_mm` decimal(6,2) DEFAULT NULL,
  `snowfall_mm` decimal(6,2) DEFAULT NULL,
  `snow_depth_mm` decimal(6,2) DEFAULT NULL,
  `avg_wind_ms` decimal(5,2) DEFAULT NULL,
  `tmax_c` decimal(5,2) DEFAULT NULL,
  `tmin_c` decimal(5,2) DEFAULT NULL,
  `station_distance_km` decimal(7,2) DEFAULT NULL,
  PRIMARY KEY (`date_key`,`airport_key`),
  KEY `ix_weather_daily_airport` (`airport_key`),
  KEY `ix_weather_daily_condition` (`weather_condition_key`),
  CONSTRAINT `fk_weather_daily_airport` FOREIGN KEY (`airport_key`) REFERENCES `dim_airport` (`airport_key`),
  CONSTRAINT `fk_weather_daily_condition` FOREIGN KEY (`weather_condition_key`) REFERENCES `dim_weather_condition` (`weather_condition_key`),
  CONSTRAINT `fk_weather_daily_date` FOREIGN KEY (`date_key`) REFERENCES `dim_date` (`date_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci

-- ---- fact_flight ----
*************************** 1. row ***************************
fact_flight
CREATE TABLE `fact_flight` (
  `flight_key` bigint NOT NULL AUTO_INCREMENT,
  `date_key` int NOT NULL DEFAULT '-1',
  `dep_time_key` int NOT NULL DEFAULT '-1',
  `origin_airport_key` int NOT NULL DEFAULT '-1',
  `dest_airport_key` int NOT NULL DEFAULT '-1',
  `carrier_key` int NOT NULL DEFAULT '-1',
  `route_key` int NOT NULL DEFAULT '-1',
  `flight_status_key` int NOT NULL DEFAULT '-1',
  `origin_weather_key` int NOT NULL DEFAULT '-1',
  `dest_weather_key` int NOT NULL DEFAULT '-1',
  `flight_number` varchar(10) NOT NULL,
  `tail_number` varchar(10) DEFAULT NULL,
  `scheduled_dep_time` smallint NOT NULL,
  `dep_delay_min` smallint DEFAULT NULL,
  `arr_delay_min` smallint DEFAULT NULL,
  `carrier_delay_min` smallint DEFAULT NULL,
  `weather_delay_min` smallint DEFAULT NULL,
  `nas_delay_min` smallint DEFAULT NULL,
  `security_delay_min` smallint DEFAULT NULL,
  `late_aircraft_delay_min` smallint DEFAULT NULL,
  `taxi_out_min` smallint DEFAULT NULL,
  `taxi_in_min` smallint DEFAULT NULL,
  `distance_miles` decimal(6,1) DEFAULT NULL,
  `flight_count` tinyint NOT NULL DEFAULT '1',
  `on_time_flag` tinyint(1) DEFAULT NULL,
  `is_outlier_delay` tinyint(1) DEFAULT NULL,
  PRIMARY KEY (`flight_key`),
  UNIQUE KEY `uq_fact_flight_business_key` (`date_key`,`carrier_key`,`flight_number`,`origin_airport_key`,`dest_airport_key`,`scheduled_dep_time`),
  KEY `fk_flight_origin_weather` (`origin_weather_key`),
  KEY `fk_flight_dest_weather` (`dest_weather_key`),
  KEY `ix_flight_date` (`date_key`),
  KEY `ix_flight_dep_time` (`dep_time_key`),
  KEY `ix_flight_origin_airport` (`origin_airport_key`),
  KEY `ix_flight_dest_airport` (`dest_airport_key`),
  KEY `ix_flight_carrier` (`carrier_key`),
  KEY `ix_flight_route` (`route_key`),
  KEY `ix_flight_status` (`flight_status_key`),
  CONSTRAINT `fk_flight_carrier` FOREIGN KEY (`carrier_key`) REFERENCES `dim_carrier` (`carrier_key`),
  CONSTRAINT `fk_flight_date` FOREIGN KEY (`date_key`) REFERENCES `dim_date` (`date_key`),
  CONSTRAINT `fk_flight_dep_time` FOREIGN KEY (`dep_time_key`) REFERENCES `dim_time_of_day` (`time_key`),
  CONSTRAINT `fk_flight_dest_airport` FOREIGN KEY (`dest_airport_key`) REFERENCES `dim_airport` (`airport_key`),
  CONSTRAINT `fk_flight_dest_weather` FOREIGN KEY (`dest_weather_key`) REFERENCES `dim_weather_condition` (`weather_condition_key`),
  CONSTRAINT `fk_flight_origin_airport` FOREIGN KEY (`origin_airport_key`) REFERENCES `dim_airport` (`airport_key`),
  CONSTRAINT `fk_flight_origin_weather` FOREIGN KEY (`origin_weather_key`) REFERENCES `dim_weather_condition` (`weather_condition_key`),
  CONSTRAINT `fk_flight_route` FOREIGN KEY (`route_key`) REFERENCES `dim_route` (`route_key`),
  CONSTRAINT `fk_flight_status` FOREIGN KEY (`flight_status_key`) REFERENCES `dim_flight_status` (`flight_status_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci

-- ---- reject_flights ----
*************************** 1. row ***************************
reject_flights
CREATE TABLE `reject_flights` (
  `reject_id` bigint NOT NULL AUTO_INCREMENT,
  `load_id` char(36) NOT NULL,
  `source_file` varchar(255) NOT NULL,
  `reason_code` varchar(50) NOT NULL,
  `reason_detail` varchar(255) DEFAULT NULL,
  `raw_row` json NOT NULL,
  `rejected_at` datetime NOT NULL,
  PRIMARY KEY (`reject_id`),
  KEY `ix_reject_flights_load` (`load_id`),
  KEY `ix_reject_flights_reason` (`reason_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci

-- ---- exception_log ----
*************************** 1. row ***************************
exception_log
CREATE TABLE `exception_log` (
  `exception_id` bigint NOT NULL AUTO_INCREMENT,
  `load_id` char(36) NOT NULL,
  `source_table` varchar(100) NOT NULL,
  `natural_key` varchar(255) NOT NULL,
  `exception_type` varchar(50) NOT NULL,
  `detail` varchar(255) DEFAULT NULL,
  `logged_at` datetime NOT NULL,
  PRIMARY KEY (`exception_id`),
  KEY `ix_exception_log_load` (`load_id`),
  KEY `ix_exception_log_type` (`exception_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci

-- ---- audit_log ----
*************************** 1. row ***************************
audit_log
CREATE TABLE `audit_log` (
  `audit_id` bigint NOT NULL AUTO_INCREMENT,
  `load_id` char(36) NOT NULL,
  `stage_name` varchar(100) NOT NULL,
  `source_file` varchar(255) DEFAULT NULL,
  `rows_in` int DEFAULT NULL,
  `rows_out` int DEFAULT NULL,
  `rows_rejected` int DEFAULT NULL,
  `started_at` datetime NOT NULL,
  `finished_at` datetime DEFAULT NULL,
  `status` varchar(20) NOT NULL,
  `message` varchar(500) DEFAULT NULL,
  PRIMARY KEY (`audit_id`),
  KEY `ix_audit_log_load` (`load_id`),
  KEY `ix_audit_log_stage` (`stage_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci

-- ---- stg_bts_flights ----
*************************** 1. row ***************************
stg_bts_flights
CREATE TABLE `stg_bts_flights` (
  `Year` text,
  `Quarter` text,
  `Month` text,
  `DayofMonth` text,
  `DayOfWeek` text,
  `FlightDate` text,
  `Reporting_Airline` text,
  `DOT_ID_Reporting_Airline` text,
  `IATA_CODE_Reporting_Airline` text,
  `Tail_Number` text,
  `Flight_Number_Reporting_Airline` text,
  `OriginAirportID` text,
  `OriginAirportSeqID` text,
  `OriginCityMarketID` text,
  `Origin` text,
  `OriginCityName` text,
  `OriginState` text,
  `OriginStateFips` text,
  `OriginStateName` text,
  `OriginWac` text,
  `DestAirportID` text,
  `DestAirportSeqID` text,
  `DestCityMarketID` text,
  `Dest` text,
  `DestCityName` text,
  `DestState` text,
  `DestStateFips` text,
  `DestStateName` text,
  `DestWac` text,
  `CRSDepTime` text,
  `DepTime` text,
  `DepDelay` text,
  `DepDelayMinutes` text,
  `DepDel15` text,
  `DepartureDelayGroups` text,
  `DepTimeBlk` text,
  `TaxiOut` text,
  `WheelsOff` text,
  `WheelsOn` text,
  `TaxiIn` text,
  `CRSArrTime` text,
  `ArrTime` text,
  `ArrDelay` text,
  `ArrDelayMinutes` text,
  `ArrDel15` text,
  `ArrivalDelayGroups` text,
  `ArrTimeBlk` text,
  `Cancelled` text,
  `CancellationCode` text,
  `Diverted` text,
  `CRSElapsedTime` text,
  `ActualElapsedTime` text,
  `AirTime` text,
  `Flights` text,
  `Distance` text,
  `DistanceGroup` text,
  `CarrierDelay` text,
  `WeatherDelay` text,
  `NASDelay` text,
  `SecurityDelay` text,
  `LateAircraftDelay` text,
  `FirstDepTime` text,
  `TotalAddGTime` text,
  `LongestAddGTime` text,
  `DivAirportLandings` text,
  `DivReachedDest` text,
  `DivActualElapsedTime` text,
  `DivArrDelay` text,
  `DivDistance` text,
  `Div1Airport` text,
  `Div1AirportID` text,
  `Div1AirportSeqID` text,
  `Div1WheelsOn` text,
  `Div1TotalGTime` text,
  `Div1LongestGTime` text,
  `Div1WheelsOff` text,
  `Div1TailNum` text,
  `Div2Airport` text,
  `Div2AirportID` text,
  `Div2AirportSeqID` text,
  `Div2WheelsOn` text,
  `Div2TotalGTime` text,
  `Div2LongestGTime` text,
  `Div2WheelsOff` text,
  `Div2TailNum` text,
  `Div3Airport` text,
  `Div3AirportID` text,
  `Div3AirportSeqID` text,
  `Div3WheelsOn` text,
  `Div3TotalGTime` text,
  `Div3LongestGTime` text,
  `Div3WheelsOff` text,
  `Div3TailNum` text,
  `Div4Airport` text,
  `Div4AirportID` text,
  `Div4AirportSeqID` text,
  `Div4WheelsOn` text,
  `Div4TotalGTime` text,
  `Div4LongestGTime` text,
  `Div4WheelsOff` text,
  `Div4TailNum` text,
  `Div5Airport` text,
  `Div5AirportID` text,
  `Div5AirportSeqID` text,
  `Div5WheelsOn` text,
  `Div5TotalGTime` text,
  `Div5LongestGTime` text,
  `Div5WheelsOff` text,
  `Div5TailNum` text,
  `load_id` char(36) NOT NULL,
  `source_file` varchar(255) NOT NULL,
  `load_timestamp` datetime NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci

-- ---- stg_airports ----
*************************** 1. row ***************************
stg_airports
CREATE TABLE `stg_airports` (
  `airport_id` text,
  `name` text,
  `city` text,
  `country` text,
  `iata` text,
  `icao` text,
  `latitude` text,
  `longitude` text,
  `altitude` text,
  `tz_offset` text,
  `dst` text,
  `tz_database_name` text,
  `airport_type` text,
  `source` text,
  `load_id` char(36) NOT NULL,
  `source_file` varchar(255) NOT NULL,
  `load_timestamp` datetime NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci

