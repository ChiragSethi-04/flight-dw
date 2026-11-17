# Phase 2 walkthrough: data quality profiling

## What was built

- **`sql/01_create_schemas.sql`**: creates the single `flight_dw` MySQL
  schema. Minimal and idempotent; both staging and warehouse tables
  live in it, matching the single `MYSQL_DATABASE` in
  `docker-compose.yml`.
- **`sql/02_create_staging.sql`**: `stg_bts_flights` (109 real columns,
  taken from the real downloaded file, not the brief's shorter summary
  list, plus `load_id`, `source_file`, `load_timestamp`) and
  `stg_airports` (the 14 OpenFlights columns, same metadata columns).
  Both are `TEXT` throughout: no casting or cleaning happens in
  staging, per hard rule 1.
- **`etl/extract.py`**: loads both staging tables with `LOAD DATA LOCAL
  INFILE`, one UUID `load_id` per run, and checks every file's loaded
  row count against its own CSV line count.
- **`etl/profile.py`**: row counts, a single-pass null/empty count
  across all 109 `stg_bts_flights` columns, duplicate business-key
  detection, a referential check of BTS airport codes against
  `stg_airports`, confirms or refutes each of the brief's nine expected
  problems with real counts, and (via plain pandas, no database
  involved) the airport-to-nearest-station haversine distance histogram
  and AWND coverage check that open decisions 5 and 3 need.
- **`docs/profiling/summary.md`** and about a dozen supporting CSVs in
  `docs/profiling/`.
- **`docs/DECISIONS.md`** updated: open decisions 3, 4 and 5 now carry
  real evidence, but are still marked OPEN, since deciding them is
  explicitly the team's call (`docs/BUILD_PLAN.md` Phase 2: "[HUMAN]
  Review the profiling summary and decide open decisions 3, 4 and 5
  with the team").

## Why each choice was made

- **Only S1 and S3 are staged this phase, not S2 or S4.** S4 is
  blocked (`docs/DECISIONS.md`, item B1): there is no real file to
  derive a staging schema from, so none is guessed. S2's per-station
  daily weather cannot be staged yet either, because which stations to
  load is decided by the airport-to-station match that Phase 3 builds;
  loading "all of NOAA" now would mean loading weather data for
  thousands of stations that will never be used. This matches the
  brief's own list of staging tables in section 6/7, which does not
  include a staging table for the station list or inventory at all:
  those are reference files, read directly by pandas when needed, not
  fact-producing sources.
- **`load_id` is one UUID per run of `etl/extract.py`, shared by every
  row loaded in that run.** `source_file` already distinguishes which
  physical file a row came from; `load_id` additionally lets a whole
  run be identified or rolled back as a unit.
- **The phantom 110th CSV field is discarded, not stored.** Every BTS
  monthly file has a trailing comma on every line, which produces an
  unnamed, always-empty 110th field when parsed strictly. `LOAD DATA`
  maps it to a throwaway MySQL user variable (`@__phantom`) instead of
  adding a meaningless column to the table.
- **The nine expected problems are checked against real counts, not
  assumed.** Problem 6 (NOAA units) is explicitly marked "deferred to
  Phase 4" rather than given a fabricated number, since no weather
  value is staged yet to check.
- **A tenth problem was added, as the brief's own instructions allow
  ("confirm or refute... and add any new problem found").** See below.

## What went wrong and why (real debugging, not hypothetical)

Three real problems came up while building and running this phase:

1. **A `NOT IN` subquery stalled indefinitely.** The first version of
   the airport-code referential check built a 14-million-row `UNION
   ALL` of every `Origin` and `Dest` value and filtered it with `code
   NOT IN (SELECT iata FROM stg_airports ...)`. MySQL's optimizer does
   not always turn `NOT IN` into an indexed anti-join; here it did not,
   and the query was still running after 50+ minutes with almost no CPU
   time used (consistent with it being stuck waiting on a very
   inefficient plan, not genuinely computing). Killed and rewritten to
   group each column down to its few hundred distinct values in SQL
   first, then compare that small set against the airport list in
   pandas. The real check (once fixed) runs in well under a second.

2. **Null-counting was correct but slow: about 18 minutes for a
   profiling step that is not supposed to be the slow part.** The first
   version ran one `SELECT COUNT(*) WHERE col = '' OR col IS NULL`
   query per column, 109 full scans of a 7-million-row unindexed table.
   Rewritten as a single query with 109 conditional `SUM()` aggregates,
   so the table is scanned once instead of 109 times. This is a
   genuine, measured performance fix, not a hypothetical one: the
   first run's timestamps show the null-count step alone took from
   18:08 to 18:26.

3. **The airport-to-station distance histogram was initially corrupted
   by bad reference data, not a bug in this code.** Two OpenFlights
   rows (IATA codes `TZR`, `OEL`) have `country = "United States"` but
   a latitude/longitude that place them in Hungary and Russia
   respectively (checked by hand: "Taszar Air Base" and "Oryol Yuzhny
   Airport"). Trusting the `country` field pulled them into the "US
   airports" set, and their nearest "US"-prefixed GHCN station came
   out at roughly 6,100-6,200km, which would have badly distorted the
   distance-threshold evidence for open decision 5. Checked whether any
   real 2025 flight references either code (`SELECT COUNT(*) FROM
   stg_bts_flights WHERE Origin IN ('TZR','OEL') OR Dest IN
   ('TZR','OEL')`): zero. Excluded both from the histogram with a
   documented threshold (500km) and logged why, rather than silently
   dropping them or silently leaving them in. This is recorded as a
   new, tenth data-quality problem in `docs/profiling/summary.md`,
   since the brief's own instructions allow for that.

## How the pieces connect

`etl/extract.py` applies `sql/01_create_schemas.sql` and
`sql/02_create_staging.sql` (both idempotent: safe to run repeatedly),
then loads S1 and S3. `etl/profile.py` reads from the resulting
`stg_bts_flights` and `stg_airports` tables for everything that needs
real flight or airport data, and reads `data/raw/noaa/ghcnd-stations.txt`
/ `ghcnd-inventory.txt` directly for the two NOAA-only checks, since
those files are not staged. Everything `etl/profile.py` writes under
`docs/profiling/` is the evidence base for Phase 3's dimensional model
and Phase 4's cleaning rules; no number in that phase should need to be
recomputed from scratch, only read from here.

## Acceptance check run

```
$ python -m etl.extract
...
OK        On_Time_Reporting_Carrier_On_Time_Performance_1987_present_2025_1.zip: csv data rows=539747, loaded rows=539747
... (all 12 months: OK, loaded rows == csv data rows, every time)
OK        airports.dat: dat data rows=7698, loaded rows=7698

$ python -m etl.profile
... (full output in docs/walkthrough/phase2.md's "what went wrong" section and docs/profiling/summary.md)

$ python -m pytest -q
...
3 passed in 0.22s
```

`stg_bts_flights` holds 7,001,619 rows; `stg_airports` holds 7,698.
Every month's staged count matches its source CSV's data-row count
exactly (verified by `etl/extract.py`, not assumed).

## Likely examiner questions

1. **Why are only two of the four sources staged in this phase?**
   S4 is blocked (no real file exists to derive a schema from) and S2's
   per-station weather data cannot be scoped until Phase 3 decides
   which stations are actually needed. Staging a guessed schema for
   either would risk building on an assumption instead of a real file,
   which hard rule 7 forbids.

2. **What does `load_id` buy you that `source_file` does not already
   give you?**
   `source_file` says which physical file a row came from.
   `load_id` says which *run* of the loader produced it, which matters
   if the same file is reloaded later (a new `load_id`, same
   `source_file`) or if a whole run needs to be identified or undone as
   a unit.

3. **Why does the staging table have 109 columns when the brief only
   lists 22 as important?**
   Staging holds every column as text, unmodified, so that nothing is
   lost or pre-judged (hard rule 1). Which of the 109 columns actually
   feed the warehouse is a cleaning and conforming decision for Phase 4,
   not a staging decision.

4. **The `NOT IN` query stall: how do you know it was the query and not
   just a slow machine?**
   It had used only 0.75 seconds of CPU time after more than 50 minutes
   of wall-clock time, which is the signature of a process waiting on
   something (in this case, a bad query plan), not one that is
   genuinely computing. A genuinely slow-but-working computation would
   show high, steadily accumulating CPU time instead.

5. **Why fix the null-count query to one pass instead of just letting
   109 queries run slowly in the background?**
   Phase 2's profiling step is meant to be a repeatable part of the
   pipeline, run every time the data changes, not a one-off script.
   An 18-minute step that only needs to be a few seconds would make
   every future profiling run unnecessarily slow, for no benefit.

6. **How did you find the two mislabeled OpenFlights rows, and how do
   you know they are actually wrong rather than your haversine formula
   being wrong?**
   They showed up as extreme outliers (over 6,000km) in a distance
   distribution where every other airport was under 95km, which is a
   strong signal something is off. Checked by looking up the airport
   names for those two IATA codes in the raw file: "Taszar Air Base"
   and "Oryol Yuzhny Airport" are real places, in Hungary and Russia,
   which confirms the `country` field is wrong for those two rows
   specifically, not that the distance math is wrong generally (every
   other airport's distance is small and plausible).

7. **Why exclude the two mislabeled rows instead of just fixing their
   `country` value?**
   Fixing a third party's reference data file would mean silently
   editing a raw source, which hard rule 1 forbids. Excluding them from
   this specific calculation, with the reason logged, is the honest
   version: the data is left as downloaded, and the exclusion plus its
   reason is visible in `docs/profiling/problem10_mislabeled_country_outliers.csv`
   and `docs/profiling/summary.md`.

8. **Problem 3's cause-sum check found 14 mismatches out of 1,534,638
   qualifying rows. Is that good or bad?**
   It is strong evidence the rule holds almost universally (99.999% of
   the time): the five delay-cause fields really do sum to the arrival
   delay whenever all five are populated and the delay qualifies. The
   14 exceptions are themselves useful: they are exactly the kind of
   case the brief says to report, not hide, once Phase 5's formal
   validation check is built.

9. **Why does the 2400-handling evidence not include a decided rule?**
   Because open decision 4 is explicitly listed in the brief as
   something to decide after counting, not something to decide
   unilaterally. The count (4,470 rows, 0.064%) and the mechanical
   mapping are shown as a preview so the team has something concrete to
   react to, but the actual rule (particularly whether any full
   timestamp needs the date rolled forward) is still the team's call.

10. **What would change in this phase's output if the team later picks
    a different data year?**
    Every number here is specific to 2025 and would need to be
    regenerated from scratch for a different year (`python -m
    etl.extract && python -m etl.profile` after changing `DATA_YEAR`).
    Nothing here is written to be year-agnostic by accident; the
    scripts always report on whatever is actually staged.
