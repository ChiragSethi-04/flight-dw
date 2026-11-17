# Task 5: Staging and ETL design

## Staging

`sql/02_create_staging.sql` creates three text-only staging tables:
`stg_bts_flights` (109 real source columns, none renamed or
retyped), `stg_airports` (14 OpenFlights columns), `stg_noaa_daily`
(station/date/element/value, long format, exactly as GHCN-Daily
publishes it). Staging is truncate-and-reload, not incremental, per
hard rule 4: `etl/extract.py` always deletes and reloads the full
table, so running the pipeline twice is safe by construction rather
than by careful bookkeeping.

## Pipeline stages, in order

1. **Extract** (`etl/extract.py`): bulk-loads S1 and S3 via `LOAD DATA
   LOCAL INFILE`, verifies the loaded row count against each source
   file's own line count, then (once `airport_station_map` exists)
   loads S2 filtered to only the stations actually nearest a matched
   airport.
2. **Clean** (`etl/clean.py`): pure, independently-tested functions
   with no side effects (`normalize_hhmm`, `cause_minutes`,
   `delay_class`, `noaa_value`, the five banding functions). 34
   pytest cases cover the brief's own named edge cases (2400, 0000,
   cancelled rows, -9999, non-summing causes) plus the 14 real
   mismatches problem 3 found.
3. **Conform** (`etl/conform.py`): pivots `stg_noaa_daily` from long
   to wide (one row per station per day, five weather elements as
   columns) and resolves the `dim_carrier` SCD2 lookup from a carrier
   code and flight date.
4. **Load dimensions** (`etl/load_dims.py`): all seven dimensions,
   always before facts, per the brief's locked load order.
5. **Load facts** (`etl/load_facts.py`): `fact_airport_weather_daily`
   first, then `fact_flight` as one set-based `INSERT ... SELECT`
   (not row-by-row), with every dimension join guarded against the
   dimension's own `-1` row to prevent the join-fan-out duplicate bug
   found in Phase 4. Also runs `log_exceptions()`, which records every
   distinct source code that fails to match a dimension to
   `exception_log`, rather than only resolving it to Unknown silently.
6. **Audit** (`etl/audit.py`): every stage above runs inside a
   `stage()` context manager that writes one `audit_log` row and one
   `logs/` line per stage, success or failure, with real row counts in
   and out.

`run_all.py` runs all of the above as numbered steps in this exact
order, and is idempotent: two full runs produced byte-identical row
counts in every table (`docs/walkthrough/phase4.md`).

## Upsert strategy

Dimensions load by upsert on their business key (airport IATA code,
carrier code + effective date, origin/destination pair, etc.), not by
blind append, so re-running the pipeline against an already-loaded
warehouse does not create duplicate dimension rows. `fact_flight` is
protected the same way by its own real `UNIQUE KEY` constraint on the
business key, which would reject a duplicate at insert time even if
the load logic tried to create one.
