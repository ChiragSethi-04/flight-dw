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

**Phases 0, 1 and 2 are complete.**

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
  produces the real evidence open decisions 3, 4 and 5 need (wind
  coverage, midnight handling, airport-to-station distance threshold) —
  see `docs/profiling/summary.md`. Those three decisions are still
  **open**, pending the team's own review, per `docs/DECISIONS.md`. See
  `docs/walkthrough/phase2.md` for the full write-up, including three
  real performance bugs found and fixed (a stalled `NOT IN` query, an
  18-minute null-count step cut to one pass, and the mislabeled-airport
  discovery).

`docs/AI_USE_LOG.md` records what AI generated versus what was reviewed,
for all three phases.

Phases 3 through 8 (dimensional model, ETL build, validation, OLAP
queries, findings, handoff) are tracked in `docs/BUILD_PLAN.md` and have
not started. Several design choices stay open until the team or data
profiling settles them; see `docs/DECISIONS.md`.

## Repository structure

```
flight-dw/
  README.md              this file
  CLAUDE.md               working rules for Claude Code on this project
  docker-compose.yml      MySQL 8 service, local_infile enabled
  .env.example            environment variable template (.env is gitignored)
  requirements.txt        Python dependencies
  run_all.py               pipeline orchestrator, numbered steps added phase by phase
  Makefile                convenience wrappers around docker compose and run_all.py
  data/
    download_sources.py    downloads and verifies S1-S4 into data/raw/
    raw/                  full downloaded source files (gitignored)
    sample/               small committed slice for reviewers
  etl/
    db.py                  shared MySQL connection helper
    extract.py             loads S1 and S3 into staging
    profile.py             data quality profiling (Phase 2)
  sql/
    01_create_schemas.sql  the flight_dw schema
    02_create_staging.sql  stg_bts_flights, stg_airports
  tests/                  pytest unit tests for transformation logic
  logs/                   per-run row counts, download and validation logs (gitignored)
  exports/                CSV and chart exports for the dashboard and report
  docs/
    brief.pdf              the project brief
    BUILD_PLAN.md          phase-by-phase build plan
    DECISIONS.md           decisions log: resolved decisions, open decisions, blockers
    source_columns.md      verified real column lists for S1 and S3, vs. the brief
    profiling/              null counts, duplicate/referential checks, distance histogram, summary.md
    AI_USE_LOG.md          record of AI use per phase
    walkthrough/           plain-language write-up of each phase, for the whole team
    diagrams/               star schema and ETL flow diagrams
    profiling/              data quality profiling output
    evidence/                validation check output
    report/                  final report drafts
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

## Reproducing the full pipeline

Not yet available. Once Phase 4 is built, running the full pipeline will
be:

```bash
python run_all.py
```

which executes every numbered step in order (dimensions before facts,
per hard rule 5 in `CLAUDE.md`). This README will be updated with exact
run order and timings once that phase is reviewed, and tested against a
clean clone before the final submission, per `docs/BUILD_PLAN.md` Phase 7.

## AI use disclosure

Parts of this repository's scaffolding, documentation and (in later
phases) code were drafted with Claude Code. Every phase's AI involvement
is logged in `docs/AI_USE_LOG.md`, including what was generated and what
a human reviewed or changed. This feeds the AI-use acknowledgement in the
final report, per the institution's requirements.

## License

No license has been chosen yet; this is coursework, not a public
release.
