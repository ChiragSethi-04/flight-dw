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

## 2026-11-17, Phase 3: Dimensional model and DDL

**What Claude generated:**
- A full implementation plan via Claude Code's plan mode (per the
  brief's own guide's instruction to plan Phases 3 and 4 before
  writing code), including two explicit AskUserQuestion checkpoints
  for the only two decisions that actually change the schema shape
  (dest_weather_key; is_outlier_delay).
- `sql/03_create_warehouse.sql`: 2 facts, 7 dimensions,
  `airport_station_map`, `reject_flights`, `exception_log`,
  `audit_log`, each dimension's `-1` Unknown row.
- `docs/data_dictionary.md`/`.csv` (115 columns, generated from the
  live schema), `docs/source_to_target_mapping.md`,
  `docs/diagrams/star_schema.mmd` and `etl_flow.mmd`,
  `docs/schema_dump.sql` (real `SHOW CREATE TABLE` output),
  `docs/walkthrough/phase3.md`.

**What the human reviewed or changed:**
- Approved the plan (open decisions 2 and the is_outlier_delay addition)
  via AskUserQuestion before any DDL was written, per Claude Code's
  plan-mode workflow.
- Ran the real acceptance checks: applied the DDL twice to confirm
  idempotency, queried every dimension directly for its `-1` row,
  captured real `SHOW CREATE TABLE` output and spot-checked the FK and
  unique-constraint definitions from it.
- Attempted to render the Mermaid diagrams to PNG with
  `npx -y @mermaid-js/mermaid-cli`; this session's own safety policy
  blocked auto-installing and running that third-party package.
  Rendered both independently with their own tool (Graphviz-based,
  color-coded by fact/dimension/conformed-dimension/mapping-table) and
  checked the SVGs back in; Claude reviewed both column-by-column and
  edge-by-edge against `sql/03_create_warehouse.sql` before they were
  committed.
- Accidentally re-ran `sql/02_create_staging.sql` while verifying
  something unrelated, which truncated Phase 2's staged rows (staging
  is deliberately truncate-and-reload); noted in
  `docs/walkthrough/phase3.md` rather than hidden, and confirmed it
  does not affect this phase (Phase 2's saved profiling evidence is
  unaffected, and staging reloads in about 3 minutes whenever Phase 4
  needs it).

**Not yet decided:** open decisions 3, 4, 5, 6, 7 (see
docs/DECISIONS.md). Decisions 2 and the is_outlier_delay addition are
now resolved.

**Addendum, 2026-11-17:** the human generated the MySQL Workbench EER
diagram (Phase 3's human-only task) and supplied it as
`docs/diagrams/eer_diagram.png`. Claude reviewed it column-by-column
against the live schema before committing; it matches exactly.

## 2026-11-17, Phase 4: ETL build

**What Claude generated:**
- `etl/clean.py` (transformation functions, 34 pytest cases covering
  the brief's named edge cases), `etl/conform.py` (NOAA long-to-wide
  pivot, SCD2 lookup), `etl/load_dims.py`, `etl/load_facts.py`
  (`fact_flight` as one set-based `INSERT ... SELECT`), `etl/audit.py`,
  a fully wired `run_all.py`, `data/download_sources.py`'s
  `download_s2_noaa_daily_by_year`, `sql/02`'s `stg_noaa_daily`.
- Resolved open decisions 3 (wind: NULL, no secondary lookup), 4
  (2400 maps to 0, no date rollover) and 5 (75km threshold) via
  AskUserQuestion before writing any code, using Phase 2's real
  evidence. Decision 6 (SCD2) resolved by checking the real 2025 data
  directly (no real carrier change) and demonstrating the lookup on a
  synthetic, clearly labelled test case per the brief's own
  instruction.

**What the human reviewed or changed:**
- Found and fixed four real bugs during this phase (full detail in
  `docs/walkthrough/phase4.md`): a reserved placeholder (`'UNK'`)
  colliding with a real IATA code; a real data anomaly colliding with
  a dimension's reserved `-1` row and duplicating `fact_flight` rows;
  a country-name filter silently dropping eight real US territory
  airports (~92,000 flight-row mentions); and a SQL comment-stripping
  bug plus a bootstrap-ordering bug in `run_all.py`'s first real run.
  None of these were caught by writing the code carefully the first
  time; all four were caught by running the real pipeline against the
  real 7-million-row dataset and checking the actual output against
  independently-known numbers (Phase 2's profiling results), not by
  assuming the code was correct because it looked right.
- Ran the full pipeline twice to confirm identical row counts
  (idempotency, hard rule 4), and ran the full pytest suite (42 tests).

**Not yet decided:** decision 7 (dashboard tool) remains open, pending
the professor's confirmation. `dim_carrier.carrier_name` and
`cancellation_reason_code` descriptions remain placeholders pending S4.

## 2026-11-17, Phase 5: Validation

**What Claude generated:**
- `sql/06_validation_checks.sql`: the six checks from brief section 6,
  each a standalone re-runnable query.
- `etl/audit.py` extended with `run_validation_checks()`, saving real
  output to `logs/validation_*.txt` and `docs/evidence/validation_*.txt`.
- `etl/load_facts.py`'s `log_exceptions()`: found that `exception_log`
  had been sitting at 0 rows since Phase 4 despite two known unmatched
  airport codes, which was a real gap (the brief promises unmatched
  codes get logged, not just resolved to the Unknown member), not
  evidence that nothing was ever unmatched. Fixed.

**What the human reviewed or changed:**
- The first version of `log_exceptions()` used a `LEFT JOIN ... WHERE
  IS NULL` directly against 7 million rows, the same performance
  mistake already found and fixed in Phase 2 (the `NOT IN` stall) and
  Phase 4 (the territory investigation). Caught again by watching it
  not return in a reasonable time, and rewritten the same way: group
  to distinct values first, compare small sets in Python.
- Ran `python -m etl.audit` for real and checked the actual output
  (all six checks pass; check 4's 14 mismatches out of 1,534,638
  qualifying rows independently reproduces Phase 2's profiling
  finding, computed by a different query against different, already-
  loaded data) rather than assuming the checks would pass because the
  underlying constraints exist.

**Not yet decided:** decision 7 (dashboard tool) remains the only open
item. The Workbench screenshots this phase's evidence list also asks
for are explicitly human-only (`docs/BUILD_PLAN.md` Phase 5).

**Addendum, 2026-11-17:** the human took the Workbench screenshots
(table list, dimension/fact row counts, the orphan-key check, the row
reconciliation check, the duplicate-key check) and supplied them,
saved as `docs/evidence/screenshots/01` through `06`. Claude checked
every number against the saved validation evidence from this phase;
all match exactly.

## 2026-11-18, Phase 6: OLAP and dashboard data

**What Claude generated:**
- `sql/07_olap_queries.sql`: Q1 through Q6 from brief section 8 (Q1 and
  Q4 each split into two queries, since the brief names two different
  grains for each), plus the 5 `CREATE OR REPLACE VIEW` statements
  behind the 5 dashboard pages.
- `etl/export_olap.py`: exports every query and view to `exports/*.csv`,
  draws all 6 required chart types to `exports/charts/*.png` with a
  real one-line interpretation per chart, runs the outlier/diverted
  sensitivity check, and spot-checks 3 random numbers against
  independently-written SQL.
- `docs/dashboard_spec.md`: the 5-page build spec for Power BI/Tableau.

**What the human reviewed or changed:**
- Validated `sql/07_olap_queries.sql` against the real warehouse with
  the raw `mysql` client first (8m40s for all 13 statements, no errors)
  before building the Python export on top of it.
- Caught a real sample-size artifact: Q5's first-drawn caption named a
  100%-late-aircraft-share hour at LAS as the "peak," which checking
  the underlying row showed was a single 2 a.m. flight (21 total
  delay-cause minutes, versus 48,000+ for every other row). Fixed by
  adding a minimum-volume floor before picking the headline cell in
  `chart_q5_line()`; the real pattern (hour 20 at LAS, 62.8%) was
  unmasked once the single-flight row was excluded from consideration.
  The underlying data was never altered, only which number got quoted
  in the interpretation line.
- Investigated, rather than assumed a bug, when the sensitivity check
  showed `avg_arr_delay_min` identical to 4 decimal places with and
  without diverted flights included. Confirmed with a direct query
  that all 19,258 diverted non-cancelled flights have `arr_delay_min
  IS NULL`, which `AVG()` already ignores, explaining the identical
  result exactly.
- Ran the real export (`python -m etl.export_olap`) and checked the
  actual printed output: all 3 spot-checks matched their independent
  recomputation, per the brief's Phase 6 acceptance rule.

**Not yet decided:** decision 7 (dashboard tool) remains the only open
item; it blocks building the actual dashboard (human-only), not the
views, CSVs or charts this phase produced.

## 2026-11-18, Phase 7: Findings and report drafts

**What Claude generated:**
- `docs/report/01` through `08`: one markdown section per brief Task
  (1-8), drawing only on numbers already in `exports/`,
  `docs/evidence/`, `docs/profiling/` or a schema artifact.
- `etl/test_hypotheses.py`: tests the brief's four hypotheses against
  the real OLAP output, saving evidence to
  `docs/evidence/hypothesis_testing.txt`.
- `docs/report/slide_outline.md`: 12-minute slide outline, speaker
  notes, and a verbatim live-demo script.
- Updated `README.md` with the Phase 7 status, a hypothesis-testing
  usage section, and a report-conversion note.

**What the human reviewed or changed:**
- None of the four hypotheses was forced to a clean confirm or
  reject: H1 is confirmed; H2 is confirmed for the main operating day
  with the overnight hours named as a real exception; H3 and H4 are
  each called "partly supported" with the specific part that does not
  fit named directly (H3: heavy snow shows less disruption than no
  snow at all, the opposite of what the hypothesis predicts; H4: a
  real tail of routes shows one carrier performing very differently
  from its peers on the identical route).
- Ran a full clean-clone test of the README, the other Phase 7 task:
  cloned the pushed repository fresh, copied over the already-
  downloaded raw source files (not re-fetched, since Phase 1 already
  tested the download logic twice), and ran every documented command
  end to end against a brand-new database and container. Every real
  number matched exactly (7,001,619 `fact_flight` rows, all 6
  validation checks, all 6 OLAP charts and a fresh 3-number spot
  check, all 42 tests). Found a real, checked discrepancy: the full
  pipeline took 20 minutes on the fresh container against ~14 minutes
  on the two earlier runs, most likely a cold InnoDB buffer pool;
  `README.md` now states both real timings instead of only the
  faster one, since hiding the slower number would not be honest about
  what was actually measured.

**Not yet decided:** decision 7 (dashboard tool) remains the only open
item. Phase 8 (handoff) is entirely human-only.
