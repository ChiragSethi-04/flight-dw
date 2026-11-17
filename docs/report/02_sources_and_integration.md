# Task 2: Source systems and integration

## The four sources

| Source | What it is | Status | Real evidence |
|---|---|---|---|
| S1: BTS Reporting Carrier On-Time Performance | Monthly CSV, one row per scheduled flight, 109 real columns | **Loaded, all 12 months of 2025** | 392 MB across 12 files, checksummed; `logs/download_20261117T060315Z.log`; staged row count matches each month's source CSV line count exactly, 7,001,619 rows total |
| S2: NOAA GHCN-Daily | Daily per-station weather observations | **Loaded**, filtered to the ~1,225 stations actually nearest a US airport | The full-year `by_year/2025.csv.gz` bulk file (one file, all worldwide stations) was used instead of ~1,225 separate per-station requests, for efficiency; see `docs/walkthrough/phase4.md` |
| S3: OpenFlights `airports.dat` | Global airport reference (IATA/ICAO, name, location, timezone) | **Loaded**, 7,698 rows staged | `docs/source_columns.md` has the real, verified column list |
| S4: BTS lookup tables (carrier names, airport IDs, cancellation reason descriptions) | Reference/decode tables | **Blocked** | Every attempted URL (`L_UNIQUE_CARRIERS`, `L_AIRPORT_ID`, `L_CANCELLATION`) returns an HTTP 302 redirect to the BTS homepage instead of the file; see `docs/DECISIONS.md` item B1 for the exact URLs tried and what a human should check in a real browser |

## Integration approach

All four sources load into their own text-only staging tables
(`stg_bts_flights`, `stg_airports`, `stg_noaa_daily`; hard rule 1: raw
data is never modified, every column stays TEXT at this stage) before
any cleaning or type conversion happens. Loading uses
`LOAD DATA LOCAL INFILE`, not row-by-row inserts, per the brief's own
technical conventions. Every load is tagged with a UUID `load_id`,
`source_file` and `load_timestamp` so any row can be traced back to
exactly which run and which source file produced it.

## S4 being blocked: real impact

Two fields remain placeholders because of the S4 blocker:
`dim_carrier.carrier_name` is currently just the two-letter carrier
code (e.g. "OO" instead of "SkyWest Airlines"), and
`dim_flight_status.cancellation_reason_code` is the raw BTS single
letter code (A/B/C/D) without its decoded description. Neither blocks
any of the six business questions or KPIs: every join, aggregation and
chart in this project uses the surrogate keys and raw codes directly,
not the missing descriptive text. If a human confirms the S4 lookup
pages work in a real browser (per `docs/DECISIONS.md`, item B1), these
two columns can be backfilled with a small, additive update, no schema
change required.

## Column mapping

Every source column actually used, and exactly where it lands in the
warehouse, is documented in full in `docs/source_to_target_mapping.md`
and `docs/data_dictionary.md`/`.csv` (generated from the live schema,
not written by hand).
