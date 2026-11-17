# Phase 3 walkthrough: dimensional model and DDL

## What was built

- **`sql/03_create_warehouse.sql`**: the two fact tables, seven
  dimensions, `airport_station_map`, `reject_flights`,
  `exception_log` and `audit_log` from brief section 5, as real,
  idempotent MySQL DDL. Every dimension gets its `-1` Unknown row as
  part of this script. `dim_date` and `dim_time_of_day` are not
  populated with real calendar/hour rows yet; that is Phase 4's job.
- **`docs/data_dictionary.md`** and **`.csv`**: every column of every
  warehouse table (115 columns across 13 tables), generated from the
  live schema (`SHOW COLUMNS`) and paired with a hand-written
  description, source and rule.
- **`docs/source_to_target_mapping.md`**: extends the brief's
  section-3 sample to every source field the schema actually uses.
- **`docs/diagrams/star_schema.mmd`** and **`etl_flow.mmd`**: Mermaid
  source for the star schema and the ETL flow. Claude Code could not
  render these to an image itself (see below), so the human running
  this session rendered both independently (a Graphviz-based tool,
  color-coded by fact/dimension/conformed-dimension/mapping-table) and
  checked them back in as **`docs/diagrams/star_schema.svg`** and
  **`etl_flow.svg`**. Both were reviewed column-by-column and
  edge-by-edge against `sql/03_create_warehouse.sql` and the brief's
  own section 5/6 diagrams before being accepted: every FK, every
  cardinality marker, the five-stage load order, and the six
  validation checks all match.
- **`docs/schema_dump.sql`**: the real `SHOW CREATE TABLE` output for
  every table, captured after running the DDL, not copied from the
  source `.sql` files.
- **`docs/diagrams/eer_diagram.png`**: the MySQL Workbench EER diagram,
  reverse-engineered by the human running this session directly from
  the live `flight_dw` schema, per `docs/BUILD_PLAN.md` Phase 3's
  human-only task (Claude Code cannot operate the Workbench GUI).
  Checked column-by-column against `sql/03_create_warehouse.sql`
  before being accepted: matches exactly, including every FK and the
  full `fact_flight` measure list.
- This plan was built and approved in Claude Code's plan mode, per the
  brief's own guide's instruction to do so for Phases 3 and 4.

## Why each choice was made

- **A raw `scheduled_dep_time` column on `fact_flight`, separate from
  the `dep_time_key` FK.** The brief's business key needs the exact
  scheduled departure time, but `dim_time_of_day` is deliberately
  coarse (hour and departure band) for OLAP slicing. Relying on
  `dep_time_key` alone for uniqueness would let two different flights
  in the same hour-band collide. Keeping both means the band dimension
  can stay coarse without weakening the uniqueness guarantee.
- **The business-key `UNIQUE` constraint on `fact_flight` uses
  surrogate FKs, not raw codes.** This works without redundant columns
  because `dim_airport` has no SCD versioning (one row per IATA code,
  ever) and `dim_carrier`'s SCD2 lookup is a deterministic function of
  (carrier code, flight date). So the FK tuple is already equivalent to
  the natural business key.
- **`dest_weather_key` was added to `fact_flight`** (open decision 2,
  resolved yes with the user before writing the DDL): symmetric with
  `origin_weather_key`, both referencing `dim_weather_condition`.
- **`is_outlier_delay` was added to `fact_flight`**, beyond the
  brief's literal measure list, because Phase 2 found real evidence
  for it (110,121 of 7,001,619 rows, 1.57%, have an arrival delay over
  180 minutes) and the brief's own problem-9 rule calls for an outlier
  flag; confirmed with the user before writing the DDL.
- **Open decisions 3, 4 and 5 do not block this phase.** Each is a
  question about data values or an ETL threshold, not about the shape
  of a table: `avg_wind_ms` is nullable either way decision 3 goes,
  `within_threshold` is a flag column regardless of what number
  decision 5 eventually sets, and decision 4 only affects how a time
  value gets computed, not which columns exist.
- **Unknown rows are inserted in this script, not Phase 4's.** The
  Phase 3 acceptance check itself requires "every dimension has a -1
  row" to exist once this phase is done.

## How the pieces connect

`sql/03_create_warehouse.sql` runs after `sql/01_create_schemas.sql`
and `sql/02_create_staging.sql`. Its own internal table order (drop
facts and the mapping table first, then dimensions; create dimensions
first, then the mapping table, then the weather fact, then the flight
fact) mirrors the brief's locked ETL load order exactly, so Phase 4's
`etl/load_dims.py` and `etl/load_facts.py` can follow the same sequence
without reconciling two different orderings.

## Acceptance check run

```
$ docker compose exec -T mysql mysql -uroot -p... < sql/01_create_schemas.sql
$ docker compose exec -T mysql mysql -uroot -p... < sql/02_create_staging.sql
$ docker compose exec -T mysql mysql -uroot -p... < sql/03_create_warehouse.sql
(exit code 0, no errors)

$ docker compose exec -T mysql mysql -uroot -p... < sql/03_create_warehouse.sql
(run a second time, exit code 0, no errors: idempotent)
```

Every one of the 7 dimension tables was queried directly
(`SELECT COUNT(*) FROM <table> WHERE <key> = -1`) and returned exactly
one row. `docs/schema_dump.sql` holds the real `SHOW CREATE TABLE`
output; spot-checked directly from that output (not from the source
`.sql`) that `fact_flight` really has its 9 foreign keys, its
`uq_fact_flight_business_key` unique constraint on the 6 business-key
columns, and that `airport_station_map` really has its FK to
`dim_airport`.

Running `sql/02_create_staging.sql` a second time during this phase's
work (by mistake, to re-check something unrelated) truncated the
7,001,619 staged rows from Phase 2, since staging is deliberately
truncate-and-reload. This did not affect anything in this phase (DDL
creation does not need staged data), and the data is trivially
reproducible with `python -m etl.extract` (about 3 minutes) whenever
Phase 4 needs it; the Phase 2 profiling evidence itself is unaffected,
since it was already saved to `docs/profiling/` as files, not left only
in the live table.

## Likely examiner questions

1. **Why does `fact_flight` have both `dep_time_key` and
   `scheduled_dep_time`? Isn't that redundant?**
   They serve different purposes at different precisions.
   `dep_time_key` is for OLAP slicing by a human-meaningful band (Q4's
   departure-band matrix). `scheduled_dep_time` is the exact HHMM value,
   needed so the business-key uniqueness constraint cannot confuse two
   different flights that happen to depart in the same hour.

2. **Why is `carrier_key` enough for the uniqueness constraint when
   `dim_carrier` is SCD Type 2?**
   Because the lookup that produces `carrier_key` from a raw carrier
   code is itself a function of the flight date (which SCD2 version was
   active then). Two rows with the same carrier code on different dates
   could, in principle, resolve to different `carrier_key` values if the
   carrier's name changed between them, but that is exactly the
   history SCD2 is meant to capture correctly, not a bug.

3. **Why are `dim_date` and `dim_time_of_day` empty except for their
   `-1` row right now?**
   Because generating their real rows is explicitly Phase 4's
   responsibility in `docs/BUILD_PLAN.md`, and doing it here would mean
   guessing at exactly how (date range, holiday logic) before that
   phase is reviewed.

4. **What would happen today if `etl/load_facts.py` tried to insert a
   flight referencing an airport code not in `dim_airport`?**
   It would fail the foreign key constraint, by design. The intended
   Phase 4 behavior is to resolve unmatched codes to the `-1` Unknown
   member before insert (and log the code to `exception_log`), exactly
   as happened for the 2 unmatched codes found in Phase 2 profiling
   (`XWA`, `EAR`).

5. **Why does `airport_station_map` use `airport_key` as its primary
   key instead of a separate surrogate key?**
   Because the grain is exactly "one row per airport" (the nearest
   station to that airport), so `airport_key` is already the natural,
   unique identifier for a row; adding a separate surrogate key would
   not identify anything a reader couldn't already get from
   `airport_key` alone.

6. **Was `dest_weather_key` actually necessary, or just symmetric for
   its own sake?**
   The brief itself raises the need in section 3 (destination weather
   matters for analyzing arrival delay, not just departure), and its
   own guide recommends adding it. Symmetry with `origin_weather_key`
   was the reason it was easy to add correctly, not the reason it was
   needed.

7. **The `is_outlier_delay` column has no threshold defined yet. Is an
   empty rule a real design decision?**
   Yes: the column exists so Phase 4 can set a threshold from real
   analysis (for example, a percentile or a fixed cutoff informed by
   the max-4,336-minute value Phase 2 found) without needing a schema
   migration later. Deciding the number now, before that analysis,
   would be exactly the kind of guessing hard rule 7 forbids.

8. **Why didn't Claude Code render the diagrams itself?**
   Doing so would have meant automatically downloading and running a
   third-party npm package (`@mermaid-js/mermaid-cli`) inside this
   session, which this session's own safety policy does not allow
   without explicit human review. The Mermaid source was complete and
   correct either way; a human rendered it independently with their own
   tool and checked the result back in as `docs/diagrams/*.svg`.

9. **If the team later decides open decision 5's threshold is, say,
   100km, does anything in this phase's DDL need to change?**
   No. `airport_station_map.within_threshold` is already a boolean
   column; only the value Phase 4's ETL writes into it depends on the
   threshold, not the column's existence or type.

10. **How do you know the FK and unique constraints actually exist in
    MySQL, and not just in the `.sql` source file?**
    `docs/schema_dump.sql` is `SHOW CREATE TABLE` output read back from
    the live database after running the script, not a copy of the
    source file. The constraint names and definitions shown there
    (for example `uq_fact_flight_business_key`) come from MySQL itself.
