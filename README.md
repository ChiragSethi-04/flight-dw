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

**Phase 0 (setup) is complete.** The repository scaffold, Docker Compose
MySQL service, environment configuration and documentation skeleton are
in place and the database connectivity check passes. See
`docs/walkthrough/phase0.md` for what was built and why, and
`docs/AI_USE_LOG.md` for what AI generated versus what was reviewed.

No flight or weather data has been downloaded or loaded yet. Phases 1
through 8 (source acquisition, profiling, dimensional model, ETL build,
validation, OLAP queries, findings, handoff) are tracked in
`docs/BUILD_PLAN.md` and have not started. Several design choices stay
open until the team or data profiling settles them; see
`docs/DECISIONS.md`.

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
    raw/                  full downloaded source files (gitignored, Phase 1)
    sample/               small committed slice for reviewers (Phase 1)
  etl/                    extraction, cleaning, loading and audit modules
  sql/                    numbered, re-runnable SQL scripts (01 through 07)
  tests/                  pytest unit tests for transformation logic
  logs/                   per-run row counts and validation output (gitignored)
  exports/                CSV and chart exports for the dashboard and report
  docs/
    brief.pdf              the project brief
    BUILD_PLAN.md          phase-by-phase build plan
    DECISIONS.md           decisions log, including the 7 open decisions
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
