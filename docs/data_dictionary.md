# Data dictionary

Every table, column, type, description, source and rule in the
warehouse schema built by `sql/03_create_warehouse.sql` (two facts,
seven dimensions, `airport_station_map`, `reject_flights`,
`exception_log`, `audit_log`). Generated from the real, live schema
(`SHOW COLUMNS`), not written by hand against an assumed design; see
`docs/schema_dump.sql` for the full `SHOW CREATE TABLE` output this
was checked against. The two staging tables (`stg_bts_flights`,
`stg_airports`) are documented separately in `docs/source_columns.md`,
since their 109 and 14 columns respectively are just the raw source
columns as text, already covered there against the brief's field list.

## `dim_date`

| Column | Type | Nullable | Description | Source | Rule |
|---|---|---|---|---|---|
| `date_key` | int | NO | Surrogate key, yyyymmdd integer. -1 = Unknown. | Generated | Phase 4 generates one row per calendar day; this phase only creates the table and the -1 row. |
| `full_date` | date | NO | The calendar date. | Generated | - |
| `day_of_month` | tinyint | NO | 1-31. | Generated | - |
| `day_of_week_num` | tinyint | NO | 1=Monday .. 7=Sunday. | Generated | - |
| `day_of_week_name` | varchar(9) | NO | Monday .. Sunday. | Generated | - |
| `week_of_year` | tinyint | NO | ISO week number. | Generated | - |
| `month_num` | tinyint | NO | 1-12. | Generated | - |
| `month_name` | varchar(9) | NO | January .. December. | Generated | - |
| `quarter` | tinyint | NO | 1-4. | Generated | - |
| `year` | smallint | NO | Calendar year. | Generated | - |
| `is_weekend` | tinyint(1) | NO | Saturday or Sunday. | Generated | - |
| `is_us_holiday` | tinyint(1) | NO | US federal holiday. | Generated | Computed with the holidays package in Phase 4. |
| `holiday_name` | varchar(50) | YES | Name of the holiday, if any. | Generated | - |
| `season` | varchar(10) | NO | Winter/Spring/Summer/Fall. | Generated | - |
## `dim_time_of_day`

| Column | Type | Nullable | Description | Source | Rule |
|---|---|---|---|---|---|
| `time_key` | int | NO | Surrogate key. -1 = Unknown. | Generated | Phase 4 generates 24 real rows, one per hour. |
| `hour_of_day` | tinyint | NO | 0-23. | Generated | - |
| `departure_band` | varchar(20) | NO | early morning/morning/afternoon/evening/night. | Generated | Band boundaries fixed in Phase 4. |
## `dim_airport`

| Column | Type | Nullable | Description | Source | Rule |
|---|---|---|---|---|---|
| `airport_key` | int | NO | Surrogate key. -1 = Unknown. | Generated | - |
| `iata_code` | char(3) | NO | 3-letter IATA code. Business key. | S3 (OpenFlights) | Also the join target for BTS Origin/Dest. |
| `icao_code` | char(4) | YES | 4-letter ICAO code. | S3 | - |
| `name` | varchar(100) | NO | Airport name. | S3 | - |
| `city` | varchar(100) | YES | City. | S3 | - |
| `state` | char(2) | YES | US state abbreviation. | S1 (BTS OriginState/DestState) | OpenFlights does not carry a US state field directly; matched from BTS in Phase 4. |
| `country` | varchar(60) | YES | Country. | S3 | Two OpenFlights rows with country='United States' but a non-US lat/lon are excluded; see docs/profiling/summary.md, problem 10. |
| `latitude` | decimal(9,6) | YES | Decimal degrees. | S3 | Feeds the haversine distance to the nearest NOAA station. |
| `longitude` | decimal(9,6) | YES | Decimal degrees. | S3 | - |
| `tz_database_name` | varchar(50) | YES | IANA tz database name. | S3 | - |
| `nearest_station_id` | char(11) | YES | Denormalized copy of airport_station_map.station_id. | Derived (S2 + S3) | airport_station_map is the authoritative source; this is a convenience copy. |
| `traffic_tier` | varchar(20) | YES | Derived flight-volume tier. | Derived (S1) | Computed from fact_flight volume in Phase 4. |
## `dim_carrier`

| Column | Type | Nullable | Description | Source | Rule |
|---|---|---|---|---|---|
| `carrier_key` | int | NO | Surrogate key. -1 = Unknown. | Generated | SCD Type 2: a carrier code can have more than one row over time. |
| `carrier_code` | char(2) | NO | 2-letter BTS carrier code. Business key. | S1 (Reporting_Airline) | - |
| `carrier_name` | varchar(100) | NO | Full carrier name. | S4 (blocked, see DECISIONS.md B1) | Until S4 is unblocked, this may fall back to the raw code. |
| `effective_from` | date | NO | SCD2 version start date. | Derived | - |
| `effective_to` | date | YES | SCD2 version end date, NULL if current. | Derived | - |
| `is_current` | tinyint(1) | NO | Whether this is the active version. | Derived | Open decision 6: one year of data may show no real carrier change; if so, this is demonstrated on a labelled test case, not real data. |
## `dim_route`

| Column | Type | Nullable | Description | Source | Rule |
|---|---|---|---|---|---|
| `route_key` | int | NO | Surrogate key. -1 = Unknown. | Generated | - |
| `origin_iata` | char(3) | NO | Origin airport IATA code. | S1 (Origin) | - |
| `dest_iata` | char(3) | NO | Destination airport IATA code. | S1 (Dest) | - |
| `distance_miles` | decimal(8,2) | YES | Great-circle distance for the route. | S1 (Distance) | Also stored as a fact_flight measure; kept here too per the brief's own dim_route attribute list. |
| `distance_band` | varchar(20) | YES | Banded distance, e.g. 0-250/250-500 miles. | Derived | Bands fixed in Phase 4. |
## `dim_flight_status`

| Column | Type | Nullable | Description | Source | Rule |
|---|---|---|---|---|---|
| `flight_status_key` | int | NO | Surrogate key. -1 = Unknown. | Generated | Junk dimension: one row per real combination found in the data. |
| `cancelled_flag` | tinyint(1) | NO | Whether the flight was cancelled. | S1 (Cancelled) | - |
| `cancellation_reason_code` | char(1) | YES | Raw BTS single-letter code (A/B/C/D). | S1 (CancellationCode) | Description lookup pending S4 (DECISIONS.md B1). |
| `diverted_flag` | tinyint(1) | NO | Whether the flight was diverted. | S1 (Diverted) | - |
| `delay_class` | varchar(20) | NO | Derived bucket, e.g. on_time/minor_delay/major_delay/cancelled/diverted. | Derived | Bucket boundaries fixed in Phase 4. |
## `dim_weather_condition`

| Column | Type | Nullable | Description | Source | Rule |
|---|---|---|---|---|---|
| `weather_condition_key` | int | NO | Surrogate key. -1 = Unknown. | Generated | Junk dimension over banded weather measures. |
| `precip_band` | varchar(20) | NO | Banded precipitation. | Derived (S2) | - |
| `snow_band` | varchar(20) | NO | Banded snowfall. | Derived (S2) | - |
| `wind_band` | varchar(20) | NO | Banded average wind. | Derived (S2) | Open decision 3 (AWND coverage) affects how often this is Unknown, not the column itself. |
| `temp_band` | varchar(20) | NO | Banded max/min temperature. | Derived (S2) | - |
## `airport_station_map`

| Column | Type | Nullable | Description | Source | Rule |
|---|---|---|---|---|---|
| `airport_key` | int | NO | FK to dim_airport. One row per airport. | Derived | - |
| `station_id` | char(11) | NO | Nearest GHCN station ID. | S2 (ghcnd-stations.txt) | Nearest by haversine distance, computed in pandas (see etl/profile.py's distance histogram for the method). |
| `distance_km` | decimal(7,2) | NO | Haversine distance, airport to station. | Derived | - |
| `within_threshold` | tinyint(1) | NO | Whether distance_km is within the agreed cutoff. | Derived | Open decision 5: the cutoff value itself is set in Phase 4 from docs/profiling/problem7_distance_histogram.csv, not guessed. |
## `fact_airport_weather_daily`

| Column | Type | Nullable | Description | Source | Rule |
|---|---|---|---|---|---|
| `date_key` | int | NO | FK to dim_date. Part of the composite PK. | Generated | - |
| `airport_key` | int | NO | FK to dim_airport. Part of the composite PK. | Generated | - |
| `weather_condition_key` | int | NO | FK to dim_weather_condition. | Derived | - |
| `precip_mm` | decimal(6,2) | YES | Precipitation in mm. | S2 (PRCP) | Converted from tenths of mm; -9999 becomes NULL (problem 6, deferred to Phase 4). |
| `snowfall_mm` | decimal(6,2) | YES | Snowfall in mm. | S2 (SNOW) | Same conversion as precip_mm. |
| `snow_depth_mm` | decimal(6,2) | YES | Snow depth in mm. | S2 (SNWD) | Same conversion. |
| `avg_wind_ms` | decimal(5,2) | YES | Average wind speed in m/s. | S2 (AWND) | Open decision 3: NULL and flagged, or backfilled from the next station with coverage; either way the column stays nullable. |
| `tmax_c` | decimal(5,2) | YES | Max temperature in Celsius. | S2 (TMAX) | Converted from tenths of a degree C. |
| `tmin_c` | decimal(5,2) | YES | Min temperature in Celsius. | S2 (TMIN) | Same conversion. |
| `station_distance_km` | decimal(7,2) | YES | Copy of airport_station_map.distance_km for this row's airport. | Derived | - |
## `fact_flight`

| Column | Type | Nullable | Description | Source | Rule |
|---|---|---|---|---|---|
| `flight_key` | bigint | NO | Surrogate key, auto-increment. Not the business key. | Generated | - |
| `date_key` | int | NO | FK to dim_date. | S1 (FlightDate) | Part of the business-key unique constraint. |
| `dep_time_key` | int | NO | FK to dim_time_of_day (hour/band). | S1 (CRSDepTime) | Coarser than scheduled_dep_time; used for OLAP slicing, not uniqueness. |
| `origin_airport_key` | int | NO | FK to dim_airport. | S1 (Origin) | Part of the business-key unique constraint. |
| `dest_airport_key` | int | NO | FK to dim_airport. | S1 (Dest) | Part of the business-key unique constraint. |
| `carrier_key` | int | NO | FK to dim_carrier (resolved by carrier code + flight date under SCD2). | S1 (Reporting_Airline) | Part of the business-key unique constraint. |
| `route_key` | int | NO | FK to dim_route. | Derived (S1 Origin+Dest) | - |
| `flight_status_key` | int | NO | FK to dim_flight_status. | Derived (S1) | - |
| `origin_weather_key` | int | NO | FK to dim_weather_condition for the origin airport's weather band on this flight date. | Derived (S2 + S3 + S1) | Denormalized onto the fact to avoid a many-to-many join at query time. |
| `dest_weather_key` | int | NO | FK to dim_weather_condition for the destination airport's weather band. | Derived | Added per open decision 2 (resolved: yes, see docs/DECISIONS.md). |
| `flight_number` | varchar(10) | NO | Degenerate dimension: BTS flight number. | S1 (Flight_Number_Reporting_Airline) | Part of the business-key unique constraint. |
| `tail_number` | varchar(10) | YES | Degenerate dimension: aircraft tail number. | S1 (Tail_Number) | - |
| `scheduled_dep_time` | smallint | NO | Raw scheduled departure time, HHMM (0-2359). | S1 (CRSDepTime) | Kept at full precision specifically so the business-key unique constraint cannot collide two different flights in the same dep_time_key band. |
| `dep_delay_min` | smallint | YES | Departure delay in minutes. | S1 (DepDelay) | NULL for cancelled flights. |
| `arr_delay_min` | smallint | YES | Arrival delay in minutes. 'Delayed' = >= 15. | S1 (ArrDelay) | NULL for cancelled flights. |
| `carrier_delay_min` | smallint | YES | Carrier-caused delay minutes. | S1 (CarrierDelay) | NULL for cancelled; 0 for non-cancelled rows with ArrDelay < 15 (problem 3). |
| `weather_delay_min` | smallint | YES | Weather-caused delay minutes (extreme weather only). | S1 (WeatherDelay) | Same NULL/0 rule as carrier_delay_min. |
| `nas_delay_min` | smallint | YES | Air traffic system delay minutes. | S1 (NASDelay) | Same NULL/0 rule. |
| `security_delay_min` | smallint | YES | Security-caused delay minutes. | S1 (SecurityDelay) | Same NULL/0 rule. |
| `late_aircraft_delay_min` | smallint | YES | Late-inbound-aircraft delay minutes. | S1 (LateAircraftDelay) | Same NULL/0 rule. |
| `taxi_out_min` | smallint | YES | Gate departure to wheels-off, minutes. | S1 (TaxiOut) | - |
| `taxi_in_min` | smallint | YES | Wheels-on to gate arrival, minutes. | S1 (TaxiIn) | - |
| `distance_miles` | decimal(6,1) | YES | Great-circle route distance. | S1 (Distance) | - |
| `flight_count` | tinyint | NO | Always 1. Summed for flight counts in OLAP. | S1 (Flights) | - |
| `on_time_flag` | tinyint(1) | YES | Arrival delay < 15 minutes. NULL for cancelled flights. | Derived (S1 ArrDelay) | On-time rate = SUM(on_time_flag) / COUNT(non-cancelled). |
| `is_outlier_delay` | tinyint(1) | YES | Extreme delay value flag. | Derived (S1 ArrDelay) | Threshold decided in Phase 4; supports the brief's Task 8 with/without-outliers sensitivity check. Added beyond the brief's literal measure list, agreed with the user in Phase 3 planning. |
## `reject_flights`

| Column | Type | Nullable | Description | Source | Rule |
|---|---|---|---|---|---|
| `reject_id` | bigint | NO | Surrogate key. | Generated | - |
| `load_id` | char(36) | NO | Which ETL run produced this reject. | Generated | - |
| `source_file` | varchar(255) | NO | Which raw file the row came from. | Generated | - |
| `reason_code` | varchar(50) | NO | e.g. DUPLICATE. | Generated | - |
| `reason_detail` | varchar(255) | YES | Free-text detail. | Generated | - |
| `raw_row` | json | NO | The full original row, as JSON, for traceability. | Generated | Hard rule 2: no row is silently dropped. |
| `rejected_at` | datetime | NO | Timestamp. | Generated | - |
## `exception_log`

| Column | Type | Nullable | Description | Source | Rule |
|---|---|---|---|---|---|
| `exception_id` | bigint | NO | Surrogate key. | Generated | - |
| `load_id` | char(36) | NO | Which ETL run logged this. | Generated | - |
| `source_table` | varchar(100) | NO | Which staging/fact table the exception relates to. | Generated | - |
| `natural_key` | varchar(255) | NO | The unmatched code, e.g. an airport or carrier code. | Generated | - |
| `exception_type` | varchar(50) | NO | e.g. UNKNOWN_AIRPORT_CODE. | Generated | - |
| `detail` | varchar(255) | YES | Free-text detail. | Generated | - |
| `logged_at` | datetime | NO | Timestamp. | Generated | - |
## `audit_log`

| Column | Type | Nullable | Description | Source | Rule |
|---|---|---|---|---|---|
| `audit_id` | bigint | NO | Surrogate key. | Generated | - |
| `load_id` | char(36) | NO | Which ETL run. | Generated | - |
| `stage_name` | varchar(100) | NO | e.g. extract_s1_bts, load_dim_date. | Generated | - |
| `source_file` | varchar(255) | YES | File processed, if applicable. | Generated | - |
| `rows_in` | int | YES | Rows read. | Generated | Row reconciliation: rows_in = rows_out + rows_rejected. |
| `rows_out` | int | YES | Rows written. | Generated | - |
| `rows_rejected` | int | YES | Rows rejected. | Generated | - |
| `started_at` | datetime | NO | Timestamp. | Generated | - |
| `finished_at` | datetime | YES | Timestamp. | Generated | - |
| `status` | varchar(20) | NO | success or failed. | Generated | - |
| `message` | varchar(500) | YES | Free-text detail, e.g. an error message. | Generated | - |
