# Phase 4 walkthrough: ETL build

## What was built

- **`etl/clean.py`**: pure transformation functions (hhmm-to-hour with
  the 2400 rule, the cause-field NULL/0 rule, NOAA tenths-to-units and
  -9999-to-NULL, the five banding functions, `delay_class`), each
  unit tested in `tests/test_clean.py` (34 tests) with the exact edge
  cases the brief names: 2400, 0000, cancelled rows, -9999, and a
  cause value present when it should be absent.
- **`etl/conform.py`**: `build_station_daily_weather` (pivots
  `stg_noaa_daily`'s long format into the wide, banded form both
  `dim_weather_condition` and `fact_airport_weather_daily` need, so
  both agree) and `resolve_carrier_key` (the SCD2 lookup, pure
  function, tested in `tests/test_conform.py` against a clearly
  labelled synthetic carrier history, per open decision 6: real 2025
  data shows no carrier with more than one version).
- **`etl/load_dims.py`**: generates `dim_date` (365 rows, `holidays`
  package) and `dim_time_of_day` (24 rows); builds `dim_airport` and
  `airport_station_map` for real (haversine, 75km threshold); builds
  `dim_carrier`, `dim_route`, `dim_flight_status`, `dim_weather_condition`
  from the real distinct values actually found in the staged data.
- **`etl/load_facts.py`**: `fact_airport_weather_daily` (pandas, one
  merge), and `fact_flight` as a single set-based `INSERT ... SELECT`
  (not row-by-row, per the brief's performance guidance), joining
  `stg_bts_flights` to every dimension by business key.
- **`etl/audit.py`**: a `stage()` context manager that writes one
  `audit_log` row and one `logs/audit_*.log` line per pipeline step,
  with row counts and timing, whether the step succeeds or raises.
- **`run_all.py`**: now a real orchestrator, not a skeleton. Runs
  every step above in the brief's locked order and is idempotent.
- **`data/download_sources.py`**: added `download_s2_noaa_daily_by_year`,
  fetching NOAA's single bulk `by_year/<year>.csv.gz` file instead of
  one request per matched station (about 1,225 separate downloads
  otherwise).
- **`sql/02_create_staging.sql`**: added `stg_noaa_daily`.
- **`sql/03_create_warehouse.sql`**: the Unknown-row placeholder for
  `dim_airport`/`dim_route` changed from `'UNK'` to `'ZZZ'` (see below).

## Why each choice was made

- **NOAA's `by_year` bulk file instead of 1,225 per-station
  downloads.** Checked first: one ~158MB file covering every GHCN
  station worldwide for 2025, filtered down to the ~1,225 stations
  actually used (`airport_station_map`) after downloading. Downloaded
  in under 3 minutes; 1,225 separate HTTP requests at this sandbox's
  observed throughput would plausibly have taken hours.
- **`fact_flight` is one `INSERT ... SELECT`, built with staged CTEs
  (`base`, `base2`, `resolved`), not a Python loop.** The brief is
  explicit that row-by-row inserts are not acceptable at 7 million
  rows. Staging the derived columns (cancelled/diverted flags, the
  computed delay class, the normalized time) in `base`/`base2` before
  the dimension joins in `resolved` exists because MySQL will not let
  a `JOIN ... ON` clause reference another column's alias from the
  same `SELECT`; splitting into CTEs avoids repeating that logic at
  every join site.
- **Every dimension join in `fact_flight`'s SQL explicitly excludes
  `-1`** (`AND oa.airport_key <> -1`, and similarly for carrier,
  route, flight_status). This was not the original design; see the
  first bug below for why it turned out to be necessary.

## What went wrong and why (real debugging, not hypothetical)

Four real problems came up while building this phase, in the order
they were found:

1. **A real IATA code collided with the dimension's own Unknown
   placeholder.** The first `dim_airport` load failed on a unique-key
   violation: `'UNK'`, the placeholder chosen for the `-1` row, turned
   out to be Unalakleet Airport's real IATA code in Alaska. Fixed by
   changing the placeholder to `'ZZZ'` (confirmed absent from the real
   downloaded file) in both `dim_airport` and `dim_route`'s `-1` rows,
   with a comment recording why.

2. **A real data anomaly collided with the Unknown placeholder's
   shape, producing duplicate fact rows.** `fact_flight`'s first full
   run failed on the business-key unique constraint. The duplicate
   turned out to be a single, genuine BTS anomaly already found in
   Phase 2 profiling (one 2025-09-06 flight, cancelled = false,
   diverted = false, `ArrDelay` blank): its derived
   `(cancelled_flag=false, cancellation_reason_code=NULL,
   diverted_flag=false, delay_class='Unknown')` combination happens to
   be identical to `dim_flight_status`'s reserved `-1` row's values, so
   the join matched *both* the real row and the placeholder,
   duplicating the fact row. Fixed by adding `AND <key> <> -1` to
   every dimension join in `fact_flight`'s SQL: the placeholder should
   only ever be reached through `COALESCE(..., -1)` when nothing
   matches, never through a natural-key join that happens to coincide
   with its values.

3. **A country-name filter silently dropped eight real US territory
   airports.** After the first successful `fact_flight` load, checking
   `origin_airport_key = -1` counts found about 49,000 unmatched rows,
   far more than Phase 2's own finding of 2 unmatched codes
   (6,004 mentions). The real unmatched list was `SJU`, `STT`, `BQN`,
   `STX`, `GUM`, `PSE`, `SPN`, `PPG` (over 92,000 flight-row mentions
   combined) plus the already-known `XWA`/`EAR`. All eight are real US
   territory airports (San Juan, St. Thomas, Aguadilla, St. Croix,
   Guam, Ponce, Saipan, Pago Pago) that OpenFlights labels with their
   own territory name (`"Puerto Rico"`, `"Guam"`, and so on) rather
   than `"United States"`, so `dim_airport`'s `country == "United
   States"` filter wrongly excluded them, even though BTS's own
   domestic on-time data includes them as real Origin/Dest points.
   Fixed by widening the filter to a `US_DOMESTIC_COUNTRIES` set.
   `XWA`/`EAR` remain genuinely unmatched (confirmed already in Phase
   2): real BTS airports simply absent from OpenFlights.

4. **A performance lesson from Phase 2 almost repeated itself.** While
   investigating problem 3, the first attempt to list every unmatched
   code used a `LEFT JOIN ... WHERE airport_key IS NULL` directly
   against 7 million rows (twice, once per Origin and once per Dest)
   and did not return in a reasonable time. Rewritten the same way
   Phase 2's `NOT IN` stall was fixed: `GROUP BY` each column down to
   its few hundred distinct values first, then compare that small set
   in pandas. Immediate.

5. **`run_all.py`'s first real run (after the territory fix above)
   failed immediately on `sql/03_create_warehouse.sql`, with a plain
   SQL syntax error.** `etl/extract.py`'s `run_sql_file` (reused by
   `run_all.py`) stripped only whole comment-only lines, not an inline
   trailing comment after real SQL on the same line (`col TEXT, --
   note`). `sql/01` and `sql/02` happen not to have any such lines, so
   this had never been exercised; `sql/03` has several, and until this
   run, `sql/03` had only ever been applied directly through the
   `mysql` CLI (which handles trailing comments correctly natively),
   never through this Python helper. Fixed by stripping everything
   from the first `--` on each line, not just whole-comment lines.
   A second bug followed immediately: the failure handler tried to
   write that failure to `audit_log`, which `sql/03` had not finished
   creating yet, hiding the real error behind a `Table doesn't exist`
   one. Fixed by not wrapping the three schema-bootstrapping SQL
   scripts in the `audit_log`-writing `stage()` helper, since they are
   what creates that table in the first place.

## How the pieces connect

`run_all.py` runs the three SQL DDL scripts, then `etl/extract.py`'s
S1/S3 staging, then `etl/load_dims.py`'s date/time/airport/station-map
step, then downloads and stages NOAA's filtered daily weather (which
needed `airport_station_map` to know which stations to keep), then the
remaining dimensions (carrier/route/status/weather-condition, the last
of which needs the staged weather), then `fact_airport_weather_daily`,
then `fact_flight` (which needs that weather fact's weather band). This
is exactly the brief's own locked load order; `etl/audit.py` wraps
every step so `audit_log` and `logs/` show real row counts and timing
for each one, not just a final total.

## Acceptance check run

```
$ python run_all.py
...
OK      extract_s1_bts (140.8s)
OK      extract_s3_airports (0.2s)
dim_date: 365 rows for 2025
dim_time_of_day: 24 rows
dim_airport: 1269 rows, airport_station_map: 1269 rows (27 beyond 75.0km threshold)
OK      download_s2_noaa_daily_by_year (1.9s, already downloaded)
OK      extract_s2_noaa_daily: 36,359,281 global rows scanned, 1,353,314 kept (17.6s)
dim_carrier: 14 rows
dim_route: 6938 rows
dim_flight_status: 9 distinct combinations found in the real data
dim_weather_condition: 265 distinct band combinations found in the real data
fact_airport_weather_daily: 334896 rows
fact_flight: 7001619 rows (578.0s)
run_all finished
EXIT=0
```

Row reconciliation: `fact_flight` holds exactly 7,001,619 rows, matching
`stg_bts_flights` exactly (every raw row produced one fact row, none
silently dropped). Unmatched Origin/Dest codes: 3,002 + 3,002 = 6,004
mentions, exactly matching Phase 2's `XWA`/`EAR` finding (and only
those two codes remain unmatched, confirmed directly). Re-run:
`python run_all.py` a second time gave identical counts across every
dimension and fact (365, 24, 1269, 14, 6938, 9, 265, 334896, 7001619),
confirmed by diffing the two runs' row counts, not assumed.

```
$ python -m pytest -q
..........................................                               [100%]
42 passed in 0.87s
```

## Likely examiner questions

1. **Why does `cause_minutes`/the cause-field SQL check
   `arr_delay_val < 15` before checking whether the raw field is
   blank, instead of the other way around?**
   Because the rule is about what the *value should be*, not just
   what BTS happened to write. A non-cancelled flight with a real
   delay under 15 minutes gets 0 regardless of what is in the raw
   field (which is normally blank there anyway); checking the delay
   threshold first makes that explicit rather than incidental.

2. **Why was `'UNK'` ever chosen as a placeholder in the first place,
   if it was always a risk?**
   It looked like an obviously safe abbreviation and was not checked
   against the real downloaded file before use. The fix captures the
   actual lesson: a placeholder for a reserved key must be verified
   absent from the real data, not just a plausible-looking string.

3. **The duplicate-row bug (finding 2): why exclude `-1` from the
   join instead of just picking a delay_class placeholder value that
   can never occur naturally, the same fix as finding 1?**
   Because `dim_flight_status`'s placeholder is a *combination* of
   four columns, each individually a value real data already uses
   (`false`, `NULL`, `false`, `'Unknown'` are all real, common values
   on their own). There is no safe placeholder combination to pick in
   advance; excluding the reserved key explicitly from every natural-
   key join is the general fix, and was applied to every dimension
   join for the same reason, not just the one that broke first.

4. **Finding 3 says BTS includes Puerto Rico and Guam as "domestic."
   Does that match the brief's stated scope?**
   Yes: the brief's scope is "US domestic flights for one calendar
   year" from BTS's own Reporting Carrier On-Time Performance dataset,
   and BTS's own domestic data includes these routes. The gap was in
   this project's dimension-loading code trusting OpenFlights'
   `country` field as a proxy for "is this in scope," not in the
   brief's definition of scope itself.

5. **How do you know finding 3 is actually fixed, and not just
   reducing the unmatched count?**
   By checking the exact unmatched code list before and after: before,
   10 codes covering about 98,700 flight-row mentions; after, it
   should be exactly the 2 already-known genuine gaps (`XWA`, `EAR`,
   6,004 mentions, confirmed in Phase 2) and nothing else. The
   acceptance check below shows the real post-fix count.

6. **Why does `fact_flight`'s business-key uniqueness check matter
   enough to have caused two of these four bugs?**
   Because it is the one constraint standing between "this pipeline
   can be re-run safely" (hard rule 4) and silent duplication. Both
   bugs it caught were real: a reserved placeholder colliding with
   real data, and the IATA-code collision earlier in Phase 3. A looser
   or absent constraint would have let both through unnoticed.

7. **What would have happened if `XWA` and `EAR` had NOT already
   been confirmed as genuine gaps in Phase 2?**
   The same investigation as finding 3 would have been needed for
   them too: check whether they are a filter bug or bug-free real gap,
   rather than assuming either.

8. **Diverted flights all have a blank `ArrDelay`. Is that assumed or
   checked?**
   Checked directly: `SELECT COUNT(*) FROM stg_bts_flights WHERE
   Diverted='1.00' AND Cancelled='0.00' AND ArrDelay<>''` returns 0,
   out of 19,258 diverted, non-cancelled rows. `on_time_flag IS NULL`
   count (122,135) is exactly cancelled (102,876) plus diverted
   (19,258) plus the one known anomaly (1), confirmed by arithmetic
   on the real numbers, not assumed.

9. **Why is `is_outlier_delay`'s count (110,121) exactly the same as
   a number already seen in Phase 2?**
   Because it is the same 180-minute cutoff, applied to the same
   `ArrDelay` field, now computed during the real load instead of a
   profiling query. The match is a deliberate cross-check that the
   load logic agrees with the profiling evidence it was built from.

10. **What is still not real, going into Phase 5?**
    `dim_carrier.carrier_name` is still a placeholder (the raw code),
    since S4 is still blocked. `cancellation_reason_code` descriptions
    are likewise pending S4. Everything else in the warehouse is now
    loaded from real 2025 data.
