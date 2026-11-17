# CLAUDE.md: Flight Delay Analytics Data Warehouse

You are helping a student team build the project described in `docs/brief.pdf` (Flight Delay Analytics Data Warehouse, initial project brief). The brief is the source of truth. Read it fully before doing anything. Phase-by-phase instructions are in `docs/BUILD_PLAN.md`. Work one phase at a time and stop at the end of each phase for human review.

## What we are building

A MySQL star schema (2 fact tables, 7 dimensions) fed by a Python (pandas) ETL pipeline from four public sources, with data quality profiling, validation checks, OLAP SQL, dashboard-ready data, and a written report. Scale is one full calendar year of US domestic flights, roughly 6 to 7 million rows.

Sources: S1 BTS Reporting Carrier On-Time Performance (monthly CSV), S2 NOAA GHCN-Daily, S3 OpenFlights `airports.dat`, S4 BTS lookup tables.

## Hard rules (never break these)

1. **Raw data is never modified.** Staging tables hold every column as text, plus `load_id`, `source_file`, `load_timestamp`.
2. **No row is silently dropped.** Anything rejected goes to a reject table with a reason code. Always hold: source rows = loaded rows + rejected rows, per month.
3. **Every number in any report comes from a query or script you ran.** Never invent results, counts, percentages or findings. The brief's hypotheses stay hypotheses until the warehouse confirms or rejects them. Mark each inference as association, not proof.
4. **Every step is idempotent.** Running the pipeline twice gives identical counts. Staging is truncate and reload. Dimensions and facts load by upsert on the business key. One `run_all` script executes numbered steps.
5. **Dimensions load before facts.** Each dimension has an integer surrogate key, keeps its source business key, and has an Unknown member with key -1.
6. **Secrets stay out of git.** Database credentials live in `.env` (gitignored). Raw data lives in `data/raw/` (gitignored). Only small samples go in `data/sample/`.
7. **Ask before guessing.** If a download URL fails, a data fact contradicts the brief, or a design decision is listed under "Open decisions" below, stop and ask the human. Do not quietly pick something and move on.
8. **Do not commit unless asked.** When asked, commit under the human's configured git identity and add a `Co-Authored-By: Claude` trailer. The team must be able to evidence each member's contribution and must disclose AI use.
9. **Writing style.** Never use em dashes in any prose, comments or documents. Keep sentences direct and plain. Write equations in LaTeX.

## Teaching mode (mandatory)

The brief states every member must be able to explain all of the work, and the assessors may question any member on any part. So after each phase:

- Write `docs/walkthrough/phaseN.md` in plain language: what was built, why each design choice was made, how the pieces connect, and 8 to 10 likely examiner questions with short model answers.
- Append an entry to `docs/AI_USE_LOG.md`: date, phase, what Claude generated, what the human reviewed or changed. This feeds the AI-use acknowledgement in the final report.

## Locked decisions (from the brief)

| Topic | Decision |
|---|---|
| Schema | Star, not snowflake. Facts: `fact_flight`, `fact_airport_weather_daily` |
| Dimensions | `dim_date`, `dim_time_of_day`, `dim_airport` (role-playing: origin and destination), `dim_carrier` (SCD Type 2), `dim_route`, `dim_flight_status` (junk), `dim_weather_condition` |
| Grain of `fact_flight` | One scheduled flight per flight date. Business key: carrier + flight number + origin + destination + scheduled departure time (+ flight date). Cancelled and diverted flights stay in |
| Degenerate dimensions | `flight_number`, `tail_number` |
| Unique constraint | On the `fact_flight` business key |
| Weather join | Airport to nearest NOAA station by haversine distance, stored in `airport_station_map` with `distance_km`. Missing station days are flagged, never filled silently |
| "Delayed" definition | Arrival delay of 15 minutes or more. Fixed everywhere and stated in the report |
| Out of scope | Real-time streaming, prices, revenue, passenger or crew data, international flights, ML (future work only) |

Haversine distance between airport $(\varphi_1,\lambda_1)$ and station $(\varphi_2,\lambda_2)$, with $R = 6371$ km:

$$d = 2R \arcsin\sqrt{\sin^2\!\left(\tfrac{\varphi_2-\varphi_1}{2}\right) + \cos\varphi_1 \cos\varphi_2 \sin^2\!\left(\tfrac{\lambda_2-\lambda_1}{2}\right)}$$

KPI definitions (non-cancelled flights unless stated):

$$\text{On-time rate} = \frac{\#\{\text{ArrDelay} < 15\}}{\#\{\text{non-cancelled flights}\}}$$

$$\text{Cancellation rate} = \frac{\#\{\text{cancelled}\}}{\#\{\text{scheduled flights}\}}$$

$$\text{Weather delay share} = \frac{\sum \text{WeatherDelay}}{\sum \text{(Carrier+Weather+NAS+Security+LateAircraft)}}$$

$$\text{Late-aircraft share} = \frac{\sum \text{LateAircraftDelay}}{\sum \text{all five causes}}$$

Average arrival delay, average departure delay and average taxi-out are plain means over non-cancelled flights.

## Open decisions (ask the human, record the answer in `docs/DECISIONS.md`)

1. **Data year.** Recommend the most recent full calendar year that BTS has published in full (verify which). Fallback: 2024.
2. **Destination weather.** The brief only lists `origin_weather_key` on `fact_flight` but section 3 mentions destination weather for arrival. Recommend adding `dest_weather_key`. Needs team agreement.
3. **Wind coverage.** GHCN `AWND` is reported by only a minority of stations, so the nearest station often has no wind. Options: take wind from the nearest station that has it within the threshold, or accept NULL and flag. Decide after profiling.
4. **Midnight (2400).** Decide after counting them. Flight date stays the local departure date. Roll the date forward only when building a full timestamp.
5. **Distance threshold** for the airport to station map. Set from the profiled distance histogram, not guessed.
6. **SCD Type 2 evidence.** One year of data may show no carrier change. Use BTS carrier history dates in the lookup, and if a real change does not appear, say so and demonstrate the logic on a clearly labelled test case, not as real data.
7. **Dashboard tool.** The brief proposes Power BI or Tableau subject to lecturer approval. You cannot operate these. Produce the clean views and export files, and a dashboard build spec (see the plan). If neither tool is approved, ask before using an alternative.

## Technical conventions

- Python 3.11+, virtual environment in `.venv`, dependencies in `requirements.txt` (pandas, SQLAlchemy, PyMySQL or mysql-connector, python-dotenv, holidays, matplotlib, pytest).
- MySQL 8 via `docker-compose.yml` with a named volume. Enable `local_infile` for bulk loads.
- Read BTS in chunks with every column as text. For loading, prefer `LOAD DATA LOCAL INFILE` or set-based `INSERT ... SELECT` joins over row-by-row inserts. Add secondary indexes after bulk load, not before.
- SQL scripts are numbered and re-runnable: `sql/01_create_schemas.sql` through `sql/07_olap_queries.sql`, as in section 7 of the brief.
- Repo layout follows section 7 of the brief (`README.md`, `data/`, `etl/`, `sql/`, `docs/`). Add `tests/` and `logs/`.
- Logging: every ETL stage writes row counts in and out to `logs/` and to an `audit_log` table.
- Tests: pytest for transformation functions (hhmm conversion, 2400 handling, unit conversion, cause rules). Validation SQL for the six audit checks in section 6 of the brief.
- Before saying a phase is done, run its acceptance checks from the plan and show the actual output.

## Working style

- Start each phase by stating your plan in a few lines, then wait for a go-ahead if the phase touches an open decision.
- Prefer small, reviewable changes. Explain trade-offs briefly.
- If you hit an error twice with the same approach, stop and report instead of looping.
- Do not install system packages or change global settings without asking.
