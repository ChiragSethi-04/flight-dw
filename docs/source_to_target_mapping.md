# Source-to-target mapping

Extends the sample mapping in brief section 3 to every source field
actually used by the schema in `sql/03_create_warehouse.sql`. Columns
present in staging but not mapped anywhere below (most of the BTS
diversion-leg fields, for example) are intentionally out of scope; see
`docs/source_columns.md` for the full real column list and why each one
is or is not used.

## dim_date (generated, Phase 4)

| Source | Target | Rule |
|---|---|---|
| (none; generated) | `dim_date.*` | One row per calendar day over a generated range; `is_us_holiday`/`holiday_name` from the `holidays` Python package. |
| S1 `FlightDate` | `fact_flight.date_key` (lookup) | Convert to `yyyymmdd` integer, look up `dim_date.date_key`. Unmatched dates do not occur (the dimension is generated to fully cover the data year), so no Unknown fallback is expected here in practice. |

## dim_time_of_day (generated, Phase 4)

| Source | Target | Rule |
|---|---|---|
| (none; generated) | `dim_time_of_day.*` | 24 rows, one per hour, each with its departure band. |
| S1 `CRSDepTime` | `fact_flight.dep_time_key` (lookup) | Convert `hhmm` to hour, map `2400` to hour `0` per open decision 4 (not yet team-decided; see `docs/DECISIONS.md`). Look up by hour. |
| S1 `CRSDepTime` | `fact_flight.scheduled_dep_time` | Cast straight to `SMALLINT` (no banding): kept at full precision for the business-key uniqueness constraint. `2400` mapping here follows the same decision-4 outcome once set. |

## dim_airport (role-playing: origin and destination)

| Source | Target | Rule |
|---|---|---|
| S3 `iata` | `dim_airport.iata_code` | Business key. |
| S3 `icao` | `dim_airport.icao_code` | - |
| S3 `name`, `city`, `country` | `dim_airport.name/city/country` | OpenFlights rows where `country = "United States"` but latitude/longitude place them elsewhere are excluded (`docs/profiling/summary.md`, problem 10: `TZR`, `OEL`). |
| S1 `OriginState`/`DestState` | `dim_airport.state` | OpenFlights has no US state field; matched in from BTS by IATA code. |
| S3 `latitude`, `longitude` | `dim_airport.latitude/longitude` | Cast to `DECIMAL(9,6)`. |
| S3 `tz_database_name` | `dim_airport.tz_database_name` | - |
| S2 `ghcnd-stations.txt` (id, latitude, longitude) | `airport_station_map.station_id`, `dim_airport.nearest_station_id` | Nearest by haversine distance (method proven in `etl/profile.py`'s distance histogram); threshold from open decision 5. |
| S1 `Origin`/`Dest` | `fact_flight.origin_airport_key`/`dest_airport_key` (lookup) | Look up by IATA code; no match maps to the Unknown member (`airport_key = -1`) and is logged to `exception_log` (problem 4: 2 such codes found in 2025, `XWA`, `EAR`, see `docs/profiling/problem4_unmatched_airport_codes.csv`). |

## dim_carrier (SCD Type 2)

| Source | Target | Rule |
|---|---|---|
| S1 `Reporting_Airline` | `dim_carrier.carrier_code` | Business key. |
| S4 (blocked, `docs/DECISIONS.md` B1) | `dim_carrier.carrier_name` | Falls back to the raw code until S4 is unblocked. |
| S1 `Reporting_Airline` + `FlightDate` | `fact_flight.carrier_key` (lookup) | SCD2 lookup: the carrier-code row whose `effective_from`/`effective_to` range covers the flight date. |

## dim_route

| Source | Target | Rule |
|---|---|---|
| S1 `Origin`, `Dest` | `dim_route.origin_iata/dest_iata` | Business key pair. |
| S1 `Distance` | `dim_route.distance_miles`, `fact_flight.distance_miles` | Cast to decimal; kept on both the dimension (per the brief's own `dim_route` attribute list) and the fact (as a measure). |
| Derived | `dim_route.distance_band` | Banded in Phase 4. |

## dim_flight_status (junk)

| Source | Target | Rule |
|---|---|---|
| S1 `Cancelled` | `dim_flight_status.cancelled_flag`, `fact_flight.flight_status_key` (lookup) | `'1.00'` -> true. |
| S1 `CancellationCode` | `dim_flight_status.cancellation_reason_code` | Raw letter kept; description pending S4. |
| S1 `Diverted` | `dim_flight_status.diverted_flag` | `'1.00'` -> true. |
| Derived (S1 `ArrDelay`, `Cancelled`) | `dim_flight_status.delay_class` | Bucketed in Phase 4. |

## dim_weather_condition (junk, derived from S2)

| Source | Target | Rule |
|---|---|---|
| S2 `PRCP`, `SNOW`, `AWND`, `TMAX`/`TMIN` (per the mapped station/date) | `dim_weather_condition.precip_band/snow_band/wind_band/temp_band` | Converted from tenths per problem 6 (deferred to Phase 4: no weather values are staged yet, see `docs/profiling/summary.md`), then banded. |
| `dim_weather_condition` row for the origin airport's date | `fact_flight.origin_weather_key` | Avoids a many-to-many join between flights and daily weather at query time. |
| `dim_weather_condition` row for the destination airport's date | `fact_flight.dest_weather_key` | Added per open decision 2 (resolved yes in Phase 3; see `docs/DECISIONS.md`). |

## airport_station_map

| Source | Target | Rule |
|---|---|---|
| S3 `latitude`/`longitude`, S2 `ghcnd-stations.txt` latitude/longitude | `airport_station_map.distance_km` | Haversine formula, as implemented and evidenced in `etl/profile.py`. |
| Derived | `airport_station_map.within_threshold` | Cutoff value from open decision 5, set from `docs/profiling/problem7_distance_histogram.csv`, not guessed. |

## fact_airport_weather_daily

| Source | Target | Rule |
|---|---|---|
| S2 `PRCP`, `SNOW`, `SNWD` | `precip_mm`, `snowfall_mm`, `snow_depth_mm` | Divide by 10 (tenths to mm); `-9999` to NULL. Not yet demonstrated on real data (problem 6 deferred; no per-station daily file is staged yet). |
| S2 `AWND` | `avg_wind_ms` | Divide by 10 (tenths to m/s); `-9999` to NULL. Open decision 3 governs whether a missing value here is backfilled from the next station or left NULL. |
| S2 `TMAX`, `TMIN` | `tmax_c`, `tmin_c` | Divide by 10 (tenths of a degree C to degrees C); `-9999` to NULL. |
| `airport_station_map.distance_km` | `station_distance_km` | Copied for the specific airport/date row. |

## fact_flight

| Source | Target | Rule |
|---|---|---|
| S1 `FlightDate` | `dim_date.date_key` (lookup) | Convert to `yyyymmdd`. |
| S1 `Reporting_Airline` | `dim_carrier.carrier_key` (lookup) | SCD2, by code and flight date. |
| S1 `Origin` | `dim_airport.airport_key` (lookup), as `origin_airport_key` | By IATA code. |
| S1 `CRSDepTime` | `dim_time_of_day.time_key` (lookup), as `dep_time_key` | Convert `hhmm` to hour, map `2400` to `0000` (open decision 4). |
| S1 `ArrDelay` | `arr_delay_min` | Cast to integer; kept NULL for cancelled flights (problem 1). |
| S1 `CarrierDelay`, `WeatherDelay`, `NASDelay`, `SecurityDelay`, `LateAircraftDelay` | `carrier_delay_min`, `weather_delay_min`, `nas_delay_min`, `security_delay_min`, `late_aircraft_delay_min` | Cast to integer; NULL to 0 only when `ArrDelay < 15` for non-cancelled flights, NULL kept for cancelled (problem 3; reconciliation held for 1,534,634 of 1,534,638 qualifying rows, 99.999%, see `docs/profiling/summary.md`). |
| S1 `DepDelay` | `dep_delay_min` | Cast to integer; NULL for cancelled. |
| S1 `TaxiOut`, `TaxiIn` | `taxi_out_min`, `taxi_in_min` | Cast to integer. |
| S1 `Distance` | `distance_miles` | Cast to decimal. |
| S1 `Flights` | `flight_count` | Always 1; summed in OLAP for flight counts. |
| S1 `Flight_Number_Reporting_Airline` | `flight_number` | Degenerate dimension, no lookup. |
| S1 `Tail_Number` | `tail_number` | Degenerate dimension, no lookup. |
| Derived (`ArrDelay`, `Cancelled`) | `on_time_flag` | `ArrDelay < 15` for non-cancelled; NULL for cancelled. |
| Derived (`ArrDelay`) | `is_outlier_delay` | Threshold set in Phase 4; added per Phase 2 problem 9 evidence (110,121 rows over 180 minutes in 2025, 1.57%), agreed with the user during Phase 3 planning. |

## reject_flights, exception_log, audit_log

Not sourced from any single input column: these are ETL-generated
traceability tables (hard rules 1 and 2), populated by `etl/clean.py`,
`etl/conform.py` and `etl/load_*.py` in Phase 4, not by a source-to-target
column mapping.
