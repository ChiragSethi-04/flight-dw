# AI use log

This log records every use of Claude Code on this project: what it
generated, and what the human reviewed or changed. It feeds the AI-use
acknowledgement in the final report. By explicit instruction from the
human, commits in this repository are not tagged with an AI co-author
trailer; this log is the record of AI involvement instead.

## 2026-11-17, Phase 0: Setup

**What Claude generated:**
- Repository scaffold: `data/`, `etl/`, `sql/`, `docs/`, `tests/`, `logs/`, `exports/` directories matching section 7 of the brief, plus the extra `tests/` and `logs/` directories the project's own CLAUDE.md asks for.
- `.gitignore`, `.env.example`, `requirements.txt`, `docker-compose.yml` (MySQL 8 with `local_infile=1`), `Makefile`.
- `etl/db.py` (shared SQLAlchemy/PyMySQL connection helper) and `run_all.py` (step-status orchestrator skeleton with a `--check-db` acceptance check).
- `docs/DECISIONS.md`, `docs/AI_USE_LOG.md` (this file), `docs/walkthrough/phase0.md`, `README.md`.
- Read and summarised `docs/brief.pdf`, the project's `CLAUDE.md`, and `docs/BUILD_PLAN.md` before writing any code, per the brief's own kickoff prompt, and surfaced the gaps noted in `docs/walkthrough/phase0.md`.

**What the human reviewed or changed:**
- Chose to scope this session to the Phase 0 scaffold only, deferring the real data downloads and full ETL build to later phases (see `docs/DECISIONS.md`, P1).
- Decided commits carry no AI co-author trailer; AI involvement is disclosed here instead (P2).
- Chose a public GitHub repository (P3).
- Ran the Phase 0 acceptance check (`docker compose up -d`, then `python run_all.py --check-db`) and confirmed the real output before accepting the phase as done.
- During that run, found a real conflict (a pre-existing local MySQL 8.4 service already on port 3306) and a real auth-plugin incompatibility (`caching_sha2_password` over plain TCP). Both are fixed in `docker-compose.yml` and explained in `docs/walkthrough/phase0.md` rather than worked around silently.

**Not yet decided (see docs/DECISIONS.md, open decisions 2-7):**
destination weather dimension, wind coverage threshold, midnight handling,
station distance threshold, SCD2 evidence approach, dashboard tool. These
require team agreement, professor confirmation, or Phase 2 profiling
evidence, so they are left open rather than guessed.

## 2026-11-17, Phase 1: Source acquisition

**What Claude generated:**
- Verified, with real HTTP requests (not assumption), the BTS PREZIP URL
  pattern, that December 2025 is published and final (resolving open
  decision 1 to `DATA_YEAR=2025`), and the NOAA and OpenFlights URLs.
- `data/download_sources.py`: a resumable downloader for S1-S4 with
  checksum logging, a content-type safety check, and a custom redirect
  handler (`NoRedirect`) added after discovering that S4's lookup
  endpoints return HTTP 200 with the site's homepage HTML rather than
  the requested CSV.
- `docs/source_columns.md`: the real column lists for S1 and S3 from
  actual downloaded files, compared field by field against the brief's
  summary list.
- `data/sample/bts_on_time_2025_01_sample_5000rows.csv`.
- Updated `docs/DECISIONS.md` (decision 1 resolved with evidence; a new
  "Blockers needing human action" entry for S4) and
  `docs/walkthrough/phase1.md`.

**What the human reviewed or changed:**
- The attempt to work around the S4 redirect by sending a browser-like
  User-Agent and Referer header was blocked by this session's own
  sandboxing policy (flagged as a disallowed bot-evasion pattern), which
  is itself consistent with the brief's instruction not to hunt for
  workarounds; S4 was left as a documented blocker for a human to check
  in a real browser instead.
- Ran the real downloads and acceptance checks rather than accepting the
  script's own claims of success at face value; this is how the S4
  false-positive (HTML saved as if it were the CSV) was actually caught.
- A real `ConnectionResetError` crashed the first full download attempt
  partway through (month 3 of 12); the script was fixed to catch
  `OSError` broadly and retry transient errors up to 4 times, then
  re-run to completion. All 12 BTS monthly files for 2025 downloaded
  successfully (392 MB total), verified against the server's
  `Content-Length` and logged with sha256 checksums in
  `logs/download_20261117T060315Z.log`.

**Not yet decided:** open decisions 2-7 remain open (see
docs/DECISIONS.md). S4 is blocked pending a human checking the lookup
URLs in a real browser.

## 2026-11-17, Phase 2: Data quality profiling

**What Claude generated:**
- `sql/01_create_schemas.sql`, `sql/02_create_staging.sql`
  (`stg_bts_flights` with the real 109-column header, `stg_airports`
  with OpenFlights' 14 columns).
- `etl/extract.py`: bulk-loads both via `LOAD DATA LOCAL INFILE`, one
  UUID `load_id` per run, verifies loaded row count against each
  source file's own line count.
- `etl/profile.py`: null counts, duplicate business-key check,
  referential check against `stg_airports`, confirms/refutes the
  brief's nine expected problems with real counts against the staged
  7,001,619-row `stg_bts_flights` table, plus a pandas-only
  airport-to-nearest-station distance histogram and AWND coverage
  check for open decisions 5 and 3.
- `docs/profiling/summary.md` and supporting CSVs; updated
  `docs/DECISIONS.md` (real evidence added for decisions 3/4/5, still
  left OPEN) and `docs/walkthrough/phase2.md`.

**What the human reviewed or changed:**
- A `NOT IN`-based referential check stalled for 50+ minutes with
  almost no CPU time used; killed it and rewrote it to group distinct
  codes first, which runs in under a second.
- A null-count step doing 109 separate full-table scans took about 18
  minutes; rewrote it as one single-pass query, confirmed correct and
  fast on re-run.
- The distance histogram initially showed two ~6,100km outliers;
  investigated rather than accepted, traced to two OpenFlights rows
  with a mislabeled `country` field, confirmed zero real 2025 flights
  reference either airport, and excluded them from the histogram with
  the reason documented (written up as a new, tenth data-quality
  problem, since the brief explicitly allows adding ones found beyond
  its own list of nine).
- Ran the actual acceptance checks (`etl.extract`, `etl.profile`,
  `pytest`) and based every number in `docs/profiling/summary.md` on
  their real output, per hard rule 3.

**Not yet decided:** open decisions 2, 3, 4, 5, 6, 7 (see
docs/DECISIONS.md: 3, 4 and 5 now have real evidence attached, but
deciding them is explicitly the team's call, not this script's).
