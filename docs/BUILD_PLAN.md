# BUILD_PLAN: phase-by-phase guide for Claude Code

Read `CLAUDE.md` first. Do one phase per session. At the end of each phase: run the acceptance checks, show real output, write the walkthrough and AI-use log entries, then stop for human review. The human may start a fresh session between phases (use `/clear` or `/compact`); everything needed must be on disk in `docs/`.

Legend: **[CC]** Claude Code does it. **[HUMAN]** the human must do it.

---

## Phase 0: Setup (mostly [HUMAN])

[HUMAN] Install Claude Code, Python 3.11+, Docker Desktop, Git. Have about 15 GB free disk. Create the repo folder `flight-dw/`, put the brief at `docs/brief.pdf`, put `CLAUDE.md` in the root and this file in `docs/`. Run `git init` and set `git config user.name` and `user.email` to your own identity. Each team member should commit under their own name.

[CC] Create the scaffold from section 7 of the brief, `.gitignore` (`.env`, `data/raw/`, `.venv/`, `logs/`), `.env.example`, `requirements.txt`, `docker-compose.yml` for MySQL 8 with `local_infile=1`, and a `Makefile` or `run_all.py` skeleton. Create `docs/DECISIONS.md`, `docs/AI_USE_LOG.md`, `docs/walkthrough/`.

Acceptance: `docker compose up -d` starts MySQL, and a Python one-liner connects with the `.env` credentials and runs `SELECT 1`.

## Phase 1: Source acquisition (Task 2)

[CC] Write `data/download_sources.py` that downloads and stores under `data/raw/`:

- **S1** BTS On-Time Reporting Carrier monthly files for the chosen year. The BTS TranStats site publishes pre-zipped monthly files (names look like `On_Time_Reporting_Carrier_..._<year>_<month>.zip`). Verify the current URL pattern before relying on it.
- **S2** NOAA GHCN-Daily: first `ghcnd-stations.txt` and `ghcnd-inventory.txt`, then per-station daily files only for the stations selected in Phase 3 (do not download the whole archive).
- **S3** OpenFlights `airports.dat` (raw file from the OpenFlights GitHub repository). The file has no header and uses `\N` for nulls. Document the column order.
- **S4** BTS lookup tables for carriers, airports and cancellation codes.

The script must be resumable (skip files already present), log file sizes and checksums, and fail loudly with the URL on any error.

If a download is blocked or the BTS site needs a form submission, **stop and tell the human** which file to download manually and where to put it. Do not hunt for mirrors.

Also create `data/sample/` with a small slice (for example the first 5,000 rows of one month) so the repo stays small and reviewers can run the pipeline.

Acceptance: file list with sizes, 12 monthly BTS files present, a printed list of which BTS columns exist versus the field list in section 3 of the brief. Note that the brief's field list omits `Diverted`, `Year`, `Month`, `DayOfWeek`, `Origin`/`Dest` city fields and airport IDs. Flag any needed field that is missing.

## Phase 2: Data quality profiling (Task 3)

[CC] Load raw data into staging (`sql/02_create_staging.sql`, `etl/extract.py`): all columns text, with `load_id`, `source_file`, `load_timestamp`. Then write `etl/profile.py` producing, per source: row counts, null counts per column, distinct counts, min and max, duplicates on the business key, and referential checks across sources (BTS airport codes versus OpenFlights, carrier codes versus lookup). Save output to `docs/profiling/` as CSV and a short markdown summary.

Confirm or refute each of the nine expected problems in section 4 of the brief with real counts, and add any new problem found. Produce the evidence the brief promises: for problems 1, 2, 3 and 6, the same ten sample rows before and after the rule, plus counts proving nothing was lost.

Produce the distance histogram input (airport to nearest station) as soon as the station map exists, so the threshold decision (open decision 5) is data-driven.

Acceptance: `docs/profiling/summary.md` with a table of problem, count found, percent of rows, proposed rule. Staging row counts per month match the CSV line counts.

[HUMAN] Review the profiling summary and decide open decisions 3, 4 and 5 with the team.

## Phase 3: Dimensional model and DDL (Task 4)

[CC] Write `sql/01_create_schemas.sql` and `sql/03_create_warehouse.sql` for the two facts and seven dimensions in section 5 of the brief. Use `DATE`, `INT`, `SMALLINT`, `DECIMAL` types sized to the data, integer surrogate keys, foreign keys, indexes on each key column, the unique constraint on the fact business key, and Unknown members with key -1. Add `reject_flights`, `exception_log` and `audit_log` tables, and `airport_station_map`.

Also write:

- `docs/data_dictionary.md` and a CSV (every table, column, type, description, source, rule).
- `docs/source_to_target_mapping.md` (full table, extending the sample in section 3 of the brief).
- Diagrams as source files: a Mermaid or Graphviz star schema and ETL flow in `docs/diagrams/`, rendered to PNG if tools allow.

Acceptance: scripts run cleanly on an empty database twice (idempotent). `SHOW CREATE TABLE` output saved to `docs/schema_dump.sql`. Every dimension has a -1 row.

[HUMAN] Open the schema in MySQL Workbench and generate the EER diagram yourself (Database, Reverse Engineer). Claude Code cannot operate the Workbench GUI. Screenshot it for the report.

## Phase 4: ETL build (Task 5)

[CC] Implement the `etl/` package as modules: `extract.py`, `clean.py`, `conform.py`, `load_dims.py`, `load_facts.py`, `audit.py`, plus `run_all.py`. Follow the load order in section 6 of the brief:

1. `dim_date` (generated, with US holiday flag via the `holidays` package, season, weekend flag) and `dim_time_of_day`
2. `dim_airport` and `airport_station_map` (nearest station by haversine, threshold from Phase 2, fallback station or flagged no-weather)
3. `dim_carrier` (Type 2), `dim_route`, `dim_flight_status`, `dim_weather_condition`
4. `fact_airport_weather_daily`
5. `fact_flight` (needs the weather band from step 4)

Apply the transformation rules from sections 3 and 4 of the brief: cast types, trim and upper-case codes, hhmm to hour with 2400 to 0000, the cause-field rule (NULL to 0 only when arrival delay is under 15, NULL kept for cancelled flights), NOAA unit conversion (tenths to mm, degrees C, m/s) and `-9999` to NULL, outlier and diverted flags, incomplete-month cut-off.

Performance: do not insert row by row. Clean in chunks to files and bulk load, then build the fact with a set-based `INSERT ... SELECT` joining the dimensions on business keys. Expect minutes, not hours, for 6 to 7 million rows. Report timings per stage in the log.

Write pytest unit tests for each transformation function with edge cases (2400, 0000, cancelled rows, `-9999`, causes that do not sum).

Acceptance: `python etl/run_all.py` completes end to end on the sample, then on the full year. Row reconciliation holds for every month. A second run gives identical counts. Tests pass.

## Phase 5: Validation (Task 6)

[CC] Write `sql/06_validation_checks.sql` and `etl/audit.py` covering all six checks in section 6 of the brief: row reconciliation per month, orphan keys (zero), uniqueness (zero duplicates), cause totals (mismatches reported, not hidden), dimension counts (distinct source codes equal dimension rows plus Unknown), re-run test. Save results to `logs/validation_<timestamp>.txt` and to `docs/evidence/`.

Evidence list the brief promises: populated row counts per table, an orphan-key query returning zero rows, sample analytical queries returning correct results.

[HUMAN] Take the screenshots for the report yourself (table creation, row counts, orphan query result in Workbench). Claude Code produces the queries and text outputs, but screenshots of your own screen are your evidence.

Acceptance: all six checks pass or have explained, documented exceptions.

## Phase 6: OLAP and dashboard data (Task 7)

[CC] Write `sql/07_olap_queries.sql` with at least one query per business question as planned in section 8 of the brief:

- Q1 top 10 worst routes by on-time rate with a minimum flight count, using `RANK()`/`DENSE_RANK()` window functions, slice by carrier
- Q2 delay minutes by cause per month as a pivot, rolled up month to quarter to year (`WITH ROLLUP`)
- Q3 average arrival delay and cancellation rate by precipitation, snow and wind band at the origin
- Q4 airport by departure-band matrix of on-time rate, plus `GROUP BY ... WITH ROLLUP` drill-down year to quarter to month to weekday
- Q5 late-aircraft share by hour for the busiest airports
- Q6 each carrier's average delay minus the route average, on routes served by two or more carriers (window `AVG() OVER (PARTITION BY route)`)

Also create reporting views (`vw_kpi_overview`, `vw_routes_carriers`, `vw_delay_causes`, `vw_weather_impact` and `vw_time_patterns`) and export each as CSV to `exports/`, matching the five dashboard pages in the brief. Generate charts with matplotlib (ranked bar, stacked bar, grouped bar, heat map, line, diverging bar) as PNGs in `exports/charts/`, each with a one-line interpretation. These are for the report and as a fallback if the BI tool is unavailable.

Also run the sensitivity checks the brief promises: results with and without outliers and diverted flights.

Write `docs/dashboard_spec.md`: for each of the five pages, the data source (view or CSV), fields, chart type, filters and the interpretation line, detailed enough that a person can build it in Power BI or Tableau in a few hours.

[HUMAN] Build the dashboard in the approved BI tool from the spec and views, and export it. Claude Code cannot operate Power BI Desktop or Tableau Desktop reliably. Connecting Power BI or Tableau to MySQL may need an extra connector or ODBC driver; the CSV exports are the fallback.

Acceptance: every query runs in a reasonable time on the full year (add indexes if not), results are saved to `exports/`, and the spot-check below passes.

**Spot-check rule:** for three randomly chosen numbers from the OLAP output, recompute them directly from the raw staging table with independent SQL or pandas and confirm they match. Show this.

## Phase 7: Findings and report drafts (Task 8)

[CC] Using only the actual query results, draft findings for the brief's four hypotheses (confirmed, rejected, or partly supported), each as evidence, then interpretation, then recommendation. Do not force a result. If the data rejects a hypothesis, say so. State limitations as in section 9 of the brief and mark all inferences as association, not proof.

Draft report sections in markdown in `docs/report/` covering Tasks 1 to 8, with tables and figures referenced from `exports/charts/`. Convert to Word or PDF with pandoc if the human asks. Draft a 12-minute slide outline with speaker notes and the live-demo script (one SQL drill-down and one dashboard filter).

Draft `README.md` with exact reproduction steps and run order, and test it by following it in a clean clone.

Acceptance: every number in the report traces to a file in `exports/` or `docs/evidence/`.

## Phase 8: Handoff checklist (all [HUMAN])

Claude Code cannot do these. Do not let it pretend to:

1. Get the five points in section 11 of the brief confirmed by the professor (tools, public data, two fact tables, full year versus sample, report length and deadline).
2. Confirm which institution's AI-use policy applies. The brief refers to SP Jain requirements, so check that is the right one for your course, then write the AI acknowledgement using `docs/AI_USE_LOG.md`.
3. Read, understand and rework the report in your own words. Rehearse explaining the whole pipeline from source to insight using the walkthrough files.
4. Build and export the dashboard, take screenshots, make the EER diagram.
5. Write your own individual contribution statement using the brief's template, and submit the confidential peer evaluation.
6. Do the live demo and the presentation.
7. Make sure the git history shows genuine contributions from each team member.

---

## Kickoff prompt (paste this into Claude Code at the start of Phase 0)

> Read CLAUDE.md and docs/BUILD_PLAN.md and the project brief at docs/brief.pdf. Summarise the project and the plan back to me in 10 lines, list any contradictions or gaps you notice in the brief, and list the open decisions you need me to answer. Do not write any code yet.

## Per-phase prompt template

> We are starting Phase N from docs/BUILD_PLAN.md. State your plan in a few lines first. Then do the [CC] items, run the acceptance checks and show me the real output, write docs/walkthrough/phaseN.md and update docs/AI_USE_LOG.md. Stop when done and wait for my review.

## Tips for running Claude Code on this

- Start in plan mode for Phases 3 and 4, since design mistakes there are expensive to undo.
- Allow commands for `docker`, `mysql`, `python`, `pytest` and `git status/diff` so you are not prompted constantly. Keep `git commit` and `git push` on manual approval.
- Test everything on `data/sample/` before the full year.
- If context fills up, run `/compact` and point it back to `CLAUDE.md` and the latest walkthrough file.
- Check `docs/DECISIONS.md` regularly. Every choice the team made should be recorded there with a reason.
