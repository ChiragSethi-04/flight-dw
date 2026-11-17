# Flight Delay Analytics Data Warehouse

A MySQL star schema warehouse, fed by a Python ETL pipeline, that joins
one full calendar year of US domestic flight performance with daily
airport weather, so an airline operations team can see why flights run
late and where to act first. Built for a Data Warehousing and BI course
assignment.

The project brief is the source of truth for every design decision in
this repository: `docs/brief.pdf`. The build is sequenced phase by phase
in `docs/BUILD_PLAN.md`, with the working rules in `CLAUDE.md`.

## Status

**Phases 0 through 4 are complete.**

- **Phase 0 (setup):** repository scaffold, Docker Compose MySQL
  service, environment configuration and documentation skeleton, with
  the database connectivity check passing. See
  `docs/walkthrough/phase0.md`.
- **Phase 1 (source acquisition):** `data/download_sources.py`
  downloads and verifies all four sources. The full 2025 calendar year
  of BTS flight data is downloaded (12 files, 392 MB, checksummed), as
  are the NOAA station/inventory reference files and the OpenFlights
  airport list. The data year (2025) was resolved with real evidence,
  not guessed; see `docs/DECISIONS.md`, decision 1. The BTS lookup
  tables (S4: carrier names, airport IDs, cancellation codes) are
  **blocked**, not downloaded: the BTS lookup page redirects away from
  the file for every endpoint tried. See `docs/DECISIONS.md`, item B1,
  for what a human needs to check. Real column lists for S1 and S3 are
  documented in `docs/source_columns.md`. See
  `docs/walkthrough/phase1.md` for the full write-up, including two
  real bugs found and fixed while building this (a silent
  redirect-to-wrong-content, and a dropped connection that crashed an
  early run).

- **Phase 2 (data quality profiling):** `sql/01_create_schemas.sql` and
  `sql/02_create_staging.sql` create the staging tables; `etl/extract.py`
  bulk-loads S1 and S3 into them (7,001,619 flight rows, 7,698 airport
  rows, every month's row count verified against its source CSV);
  `etl/profile.py` confirms or refutes all nine of the brief's expected
  data-quality problems with real counts, finds and documents a tenth
  (two OpenFlights reference rows with a mislabeled country field), and
  produces the real evidence open decisions 3, 4 and 5 needed (wind
  coverage, midnight handling, airport-to-station distance threshold),
  see `docs/profiling/summary.md`. All three were resolved in Phase 4
  using this evidence; see `docs/DECISIONS.md`. See
  `docs/walkthrough/phase2.md` for the full write-up, including three
  real performance bugs found and fixed (a stalled `NOT IN` query, an
  18-minute null-count step cut to one pass, and the mislabeled-airport
  discovery).
- **Phase 3 (dimensional model and DDL):** `sql/03_create_warehouse.sql`
  creates the full star schema (2 facts, 7 dimensions,
  `airport_station_map`, `reject_flights`, `exception_log`,
  `audit_log`), idempotent and verified to run cleanly twice, with every
  dimension's `-1` Unknown row confirmed to exist. Built in Claude
  Code's plan mode per the brief's own guide. `dest_weather_key` (open
  decision 2) and a new `is_outlier_delay` column were added, both
  confirmed with the user before any DDL was written; see
  `docs/DECISIONS.md`. Full column-level documentation in
  `docs/data_dictionary.md`/`.csv`, `docs/source_to_target_mapping.md`,
  and the real `SHOW CREATE TABLE` output in `docs/schema_dump.sql`.
  Star schema and ETL flow diagrams are in `docs/diagrams/` as Mermaid
  source (`.mmd`) plus rendered SVGs (`.svg`, rendered and reviewed by
  a human, since Claude Code could not auto-install a renderer itself;
  see `docs/walkthrough/phase3.md`). The MySQL Workbench EER diagram
  (`docs/BUILD_PLAN.md` Phase 3's human-only task) is done too:
  `docs/diagrams/eer_diagram.png`, reverse-engineered directly from the
  live schema. Checked column-by-column against `sql/03_create_warehouse.sql`:
  matches exactly, including the full `fact_flight` measure list and
  every FK.
- **Phase 4 (ETL build):** the full pipeline is real. `run_all.py`
  downloads NOAA's full-year bulk weather file (filtered to the
  ~1,225 matched stations), stages everything, and loads all 7
  dimensions and both facts: **7,001,619 `fact_flight` rows** (an
  exact match with `stg_bts_flights`, confirming no row was silently
  dropped) and **334,896 `fact_airport_weather_daily` rows**. Open
  decisions 3 (wind: NULL, no secondary lookup), 4 (2400 maps to 0,
  no date rollover) and 5 (75km distance threshold) were resolved with
  real Phase 2 evidence before any code was written; decision 6
  (carrier SCD2) was resolved by checking the real data directly (no
  real change in one year) and demonstrating the lookup on a
  synthetic, clearly labelled test case per the brief's own
  instruction. See `docs/DECISIONS.md`. Re-ran the full pipeline twice
  to confirm identical counts (idempotent, hard rule 4). `etl/clean.py`'s
  transformation functions have 34 dedicated pytest cases (42 total
  across the project) covering the brief's named edge cases (2400,
  0000, cancelled rows, -9999, non-summing causes). See
  `docs/walkthrough/phase4.md` for the full write-up, including four
  real bugs found and fixed: a reserved placeholder colliding with a
  real IATA code, a real data anomaly colliding with a dimension's
  reserved row and duplicating fact rows, a country filter that
  silently dropped eight real US territory airports (~92,000
  flight-row mentions), and a SQL comment-handling bug in the
  orchestrator's first real run.

`docs/AI_USE_LOG.md` records what AI generated versus what was reviewed,
for all phases so far.

Phases 5 through 8 (validation, OLAP queries, findings, handoff) are
tracked in `docs/BUILD_PLAN.md` and have not started. Decision 7
(dashboard tool) is the only one still open, pending the professor's
confirmation; see `docs/DECISIONS.md`.

## Repository structure

```
flight-dw/
  README.md              this file
  CLAUDE.md               working rules for Claude Code on this project
  docker-compose.yml      MySQL 8 service, local_infile enabled
  .env.example            environment variable template (.env is gitignored)
  requirements.txt        Python dependencies
  run_all.py               full pipeline orchestrator, every step, in order
  Makefile                convenience wrappers around docker compose and run_all.py
  data/
    download_sources.py    downloads and verifies S1-S4, plus the S2 NOAA bulk weather file
    raw/                  full downloaded source files (gitignored)
    sample/               small committed slice for reviewers
  etl/
    db.py                  shared MySQL connection helper
    extract.py             loads S1, S3 and (once airport_station_map exists) filtered S2 daily weather
    clean.py               pure transformation functions (hhmm/2400, cause rules, NOAA units, bands)
    conform.py             NOAA long-to-wide pivot; the SCD2 carrier lookup
    load_dims.py            builds all 7 dimensions + airport_station_map
    load_facts.py           builds both facts (fact_flight as one set-based INSERT ... SELECT)
    audit.py                per-stage row-count logging to audit_log and logs/
    profile.py             data quality profiling (Phase 2)
  sql/
    01_create_schemas.sql    the flight_dw schema
    02_create_staging.sql    stg_bts_flights, stg_airports, stg_noaa_daily
    03_create_warehouse.sql  2 facts, 7 dimensions, airport_station_map, reject/exception/audit logs
  tests/                  pytest (42 tests): transformation functions, SCD2 lookup, scaffold
  logs/                   per-run row counts, download and validation logs (gitignored)
  exports/                CSV and chart exports for the dashboard and report
  docs/
    brief.pdf                the project brief
    BUILD_PLAN.md            phase-by-phase build plan
    DECISIONS.md             decisions log: resolved decisions, open decisions, blockers
    source_columns.md        verified real column lists for S1 and S3, vs. the brief
    data_dictionary.md/.csv  every warehouse column, generated from the live schema
    source_to_target_mapping.md  every source field's path into the schema
    schema_dump.sql          real SHOW CREATE TABLE output
    AI_USE_LOG.md            record of AI use per phase
    walkthrough/             plain-language write-up of each phase, for the whole team
    diagrams/                star schema and ETL flow diagrams (.mmd source + rendered .svg)
    profiling/               data quality profiling output (Phase 2)
    evidence/                validation check output (Phase 5, not yet built)
    report/                  final report drafts (Phase 7, not yet built)
```

## Setup

Requirements: Docker Desktop, Python 3.11+, about 15 GB free disk once
the full year of data is downloaded.

```bash
git clone <this-repository-url>
cd flight-dw

cp .env.example .env
# edit .env and set real MySQL credentials

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

docker compose up -d
python run_all.py --check-db
```

A successful check prints:

```
MySQL connection OK, SELECT 1 returned: 1
```

The Docker Compose file maps the container's MySQL port (3306) to
**3307** on the host, not 3306, because a locally installed MySQL server
is a common thing to already have running on 3306 (this was the case on
the machine this was built on: a Homebrew MySQL 8.4 service, left
untouched). If 3307 is also taken on your machine, change the host-side
number in both `docker-compose.yml` and `.env` (`MYSQL_PORT`) to match.

## Downloading the source data

```bash
python data/download_sources.py           # downloads S1-S4 for DATA_YEAR in .env
python data/download_sources.py --year 2025 --only s1   # just one source, one year
```

This is resumable: re-running it only fetches what is missing or has
changed size. It downloads about 400 MB for a full year of S1-S3. S4
(BTS lookup tables) is currently blocked; see `docs/DECISIONS.md`, item
B1, for what to do about it. A reviewer who does not want to download
the full year can use `data/sample/bts_on_time_2025_01_sample_5000rows.csv`
instead.

## Loading staging and profiling

```bash
python -m etl.extract            # loads S1 and S3 into stg_bts_flights / stg_airports
python -m etl.profile            # writes docs/profiling/summary.md and supporting CSVs
```

`etl.extract` takes a couple of minutes for the full year (7,001,619
rows). `etl.profile` takes under a minute. Both are idempotent: staging
tables are dropped and recreated each run, and profiling always reads
whatever is currently staged.

## Building the warehouse schema

```bash
docker compose exec -T mysql mysql -uroot -p"$MYSQL_ROOT_PASSWORD" < sql/01_create_schemas.sql
docker compose exec -T mysql mysql -uroot -p"$MYSQL_ROOT_PASSWORD" < sql/02_create_staging.sql
docker compose exec -T mysql mysql -uroot -p"$MYSQL_ROOT_PASSWORD" < sql/03_create_warehouse.sql
```

Idempotent: safe to run against an empty database or one that already
has this schema. Creates the two facts, seven dimensions (each with its
`-1` Unknown row), `airport_station_map`, `reject_flights`,
`exception_log` and `audit_log`. Does not populate any real rows beyond
the Unknown members; that is Phase 4.

## Reproducing the full pipeline

```bash
python run_all.py
```

Runs every step end to end: the three SQL DDL scripts, S1/S3 staging,
all 7 dimensions, the NOAA bulk weather download and filtered staging,
and both facts, in the brief's locked order (dimensions before facts).
Idempotent: safe to run more than once, and does. Real timing on this
project's dev machine: about 14 minutes total, almost all of it
`fact_flight`'s set-based load (~10 minutes) and the initial S1 staging
(~2.5 minutes); everything else is under a minute combined. Will be
tested against a clean clone before the final submission, per
`docs/BUILD_PLAN.md` Phase 7.

```bash
python run_all.py --status    # list every step without running them
python run_all.py --check-db  # just verify the MySQL connection
```

## AI use disclosure

Parts of this repository's scaffolding, documentation and (in later
phases) code were drafted with Claude Code. Every phase's AI involvement
is logged in `docs/AI_USE_LOG.md`, including what was generated and what
a human reviewed or changed. This feeds the AI-use acknowledgement in the
final report, per the institution's requirements.

## License

No license has been chosen yet; this is coursework, not a public
release.
