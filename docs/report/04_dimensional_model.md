# Task 4: Dimensional model

## Design

Star schema, not snowflake, per the brief's locked decision. Two fact
tables share conformed dimensions (`dim_date`, `dim_airport`), so the
same date and the same airport mean exactly the same thing whether
reached from a flight or from a weather reading.

**Grain of `fact_flight`:** one scheduled flight per flight date,
identified by carrier + flight number + origin + destination +
scheduled departure time + flight date. Cancelled and diverted flights
stay in the table (they are facts about a scheduled flight, not
absences of one).

**Grain of `fact_airport_weather_daily`:** one airport, one calendar
day.

## The seven dimensions

| Dimension | Pattern | Real row count (incl. the -1 Unknown row) | Notes |
|---|---|---|---|
| `dim_date` | Conformed, generated | 366 | 365 real 2025 calendar rows + Unknown |
| `dim_time_of_day` | Generated | 25 | 24 hours + Unknown; carries `departure_band` for Q4/Q5 |
| `dim_airport` | Conformed, role-playing (origin and destination) | 1,270 | 1,269 real OpenFlights-sourced airports + Unknown; includes US territories (Puerto Rico, Guam, etc.), a real bug found in Phase 4 |
| `dim_carrier` | SCD Type 2 | 15 | 14 real 2025 carriers, all with a single, still-current version (no real mid-year change observed; see `docs/DECISIONS.md` decision 6) + Unknown |
| `dim_route` | Standard | 6,939 | Every real origin-destination pair actually flown in 2025 + Unknown |
| `dim_flight_status` | Junk | 10 | Every real combination of cancelled flag, cancellation reason code, diverted flag and delay class + Unknown |
| `dim_weather_condition` | Junk | 266 | Every real combination of precipitation, snow, wind and temperature band + Unknown |

Every dimension's Unknown member uses surrogate key `-1`, confirmed to
exist by direct query in Phase 3 and again by Phase 5's check 5/6.
`flight_number` and `tail_number` are degenerate dimensions, stored
directly on `fact_flight` with no separate table, per the brief's
locked decision.

## Fact tables

`fact_flight`: 7,001,619 rows. Nine foreign keys (`date_key`,
`dep_time_key`, `origin_airport_key`, `dest_airport_key`,
`carrier_key`, `route_key`, `flight_status_key`,
`origin_weather_key`, `dest_weather_key`), each defaulting to -1 and
each enforced by a real InnoDB `FOREIGN KEY` constraint, confirmed to
reject orphans by Phase 5's check 2 (0 orphans across all nine).
`dest_weather_key` is this project's own addition beyond the brief's
literal FK list (open decision 2), added for symmetry with
`origin_weather_key` since the brief's own section 3 discusses
destination weather for arrival analysis. `is_outlier_delay` is a
second addition, motivated directly by profiling problem 9's real
evidence (110,121 rows over the 180-minute threshold).

`fact_airport_weather_daily`: 334,896 rows, composite primary key
(`date_key`, `airport_key`).

## Why a raw `scheduled_dep_time` column exists alongside `dep_time_key`

`dim_time_of_day` is deliberately coarse (hour of day plus departure
band) for OLAP slicing. Using only `dep_time_key` in `fact_flight`'s
business-key uniqueness constraint would let two genuinely different
flights departing in the same hour collide. `scheduled_dep_time`
(the literal HHMM value) keeps the uniqueness constraint exact without
making `dim_time_of_day` any finer-grained than the dashboard needs.

## Evidence

Real `SHOW CREATE TABLE` output for every table is in
`docs/schema_dump.sql`. The EER diagram
(`docs/diagrams/eer_diagram.png`) and the Mermaid star-schema/ETL-flow
diagrams (`docs/diagrams/star_schema.svg`, `etl_flow.svg`) were both
checked column by column and edge by edge against the live schema
before being committed; see `docs/walkthrough/phase3.md`.
