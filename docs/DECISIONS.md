# Decisions log

Every design choice the team makes gets a row here with a reason, so any
member can explain why something is the way it is. Open decisions from
CLAUDE.md stay listed as OPEN until the team or the profiling evidence
settles them. Nothing here is guessed.

## Process decisions (Phase 0)

| # | Topic | Decision | Reason | Date |
|---|---|---|---|---|
| P1 | Build scope for this session | Build the Phase 0 scaffold only (repo structure, config, docker-compose, docs skeleton). Defer real data downloads and the full ETL build to later phases. | The brief's own CLAUDE.md requires working one phase at a time with human review between phases, and the full pipeline needs a real multi-gigabyte download plus hours of processing that should not happen inside a single unreviewed session. | 2026-11-17 |
| P2 | Git identity | All commits are made under Chirag Sethi's configured git identity. No AI co-author trailer is added to commits, by explicit instruction. | AI use is disclosed in docs/AI_USE_LOG.md instead, which is the mechanism the brief's own AI-use acknowledgement relies on. | 2026-11-17 |
| P3 | GitHub repo visibility | Public. | Explicit choice by the team member setting up the repo. | 2026-11-17 |

## Decided, with evidence

| # | Topic | Decision | Evidence | Date |
|---|---|---|---|---|
| 1 | Data year | **2025.** | Checked the live BTS TranStats PREZIP endpoint directly (`curl -I`) on 2026-11-17. `On_Time_Reporting_Carrier_On_Time_Performance_1987_present_2025_12.zip` returns HTTP 200, `Content-Length: 30337431`, `Last-Modified: Fri, 20 Mar 2026`, confirming December 2025 (the last month of calendar year 2025) has been published and is a complete, final file, not a placeholder. 2026 is not a candidate: it is the current, in-progress calendar year as of this check (today is 2026-11-17), so it cannot be a "full calendar year" yet. This matches the brief's own instruction to recommend "the most recent full calendar year BTS has published in full" rather than defaulting to the 2024 fallback, since 2025 is more recent and is verified complete. Recorded in `.env` / `.env.example` as `DATA_YEAR=2025`. | 2026-11-17 |
| 2 | Destination weather (`dest_weather_key` on `fact_flight`) | **Yes, add it.** | The brief's own guide recommends this (section 3 discusses destination weather for arrival analysis, but the fact table FK list only named `origin_weather_key`). Confirmed directly with the user during Phase 3 plan-mode review before writing the DDL (AskUserQuestion, 2026-11-17): symmetric with `origin_weather_key`, both FKs to `dim_weather_condition`. See `sql/03_create_warehouse.sql`. | 2026-11-17 |
| P4 | `is_outlier_delay` on `fact_flight` | **Yes, add it.** | Beyond the brief's literal `fact_flight` measure list, but directly motivated by real Phase 2 evidence (110,121 of 7,001,619 rows, 1.57%, have an arrival delay over 180 minutes; max 4,336 minutes) and the brief's own problem-9 proposed rule ("add outlier and diverted flags"; diverted is already covered by `dim_flight_status`). Confirmed with the user during Phase 3 plan-mode review (AskUserQuestion, 2026-11-17). A nullable boolean; the actual threshold is set in Phase 4, not guessed here. | 2026-11-17 |
| 3 | Wind (AWND) coverage | **NULL, no secondary-station lookup.** | Of 1,225 distinct nearest stations used, only 711 (58.0%) report AWND (Phase 2 evidence). Confirmed with the user during Phase 4 planning (AskUserQuestion, 2026-11-17): if the single nearest station does not report AWND, `fact_airport_weather_daily.avg_wind_ms` is NULL, rather than searching further out for a second station that does report it (which would mean using a station chosen for wind coverage, not proximity, for that one measure). | 2026-11-17 |
| 4 | Midnight (2400) handling | **2400 maps to hour 0 / HHMM value 0, flight date never rolled forward.** | `fact_flight` has no full-timestamp column (only `date_key` plus the literal `scheduled_dep_time` HHMM value), so the brief's "roll the date forward only when building a full timestamp" clause never triggers in this schema. Confirmed with the user during Phase 4 planning (AskUserQuestion, 2026-11-17). Implemented in `etl/clean.normalize_hhmm` and mirrored in `etl/load_facts.py`'s SQL. 4,470 of 7,001,619 rows (0.064%) were affected (Phase 2 evidence). | 2026-11-17 |
| 5 | Airport-to-station distance threshold | **75km.** | Phase 2's histogram: 98.7% of airports within 50km, 100% within 100km (after excluding 2 mislabeled OpenFlights rows), with the tail at 7 airports in the 50-75km band and 7 more in 75-100km. Confirmed with the user during Phase 4 planning (AskUserQuestion, 2026-11-17): 75km flags only the most remote tail, keeping the 50-75km band as a reasonable local-climate proxy. After widening `dim_airport` to include US territories (see `docs/walkthrough/phase4.md`, finding 3), the real count beyond 75km is 27 of 1,269 airports. Implemented as `STATION_DISTANCE_THRESHOLD_KM` in `etl/load_dims.py`. | 2026-11-17 |
| 6 | SCD Type 2 evidence for `dim_carrier` | **No real change in the 2025 data; demonstrated on a synthetic test case instead.** | Checked directly: `dim_carrier` has exactly one version per carrier code for all of 2025 (14 carriers, `effective_to` NULL for every one), which is expected since S4 (the source that would carry carrier history dates) is blocked and a single year cannot show a real mid-year change either way. Per the brief's own instruction, the SCD2 lookup logic itself is exercised in `tests/test_conform.py` against a clearly labelled, made-up carrier history (code `ZX`, explicitly flagged as synthetic in the test file), not against real data. | 2026-11-17 |

## Open decisions from the brief (still OPEN)

| # | Topic | Brief's recommendation | Status |
|---|---|---|---|
| 7 | Dashboard tool (Power BI vs Tableau vs neither) | Subject to lecturer approval | OPEN. Needs the professor's confirmation (brief section 11, point 1). This is the only decision left open. |

## Blockers needing human action

| # | Topic | What was tried | What is needed |
|---|---|---|---|
| B1 | S4 BTS lookup tables (carrier names, airport IDs, cancellation codes) | On 2026-11-17, `data/download_sources.py` tried `https://www.transtats.bts.gov/Download_Lookup.asp?Lookup=L_UNIQUE_CARRIERS` (and `L_AIRPORT_ID`, `L_CANCELLATION`). Every attempt returns HTTP 302 to `Homepage.asp`, including with a session cookie carried from a prior request to the same page with no `Lookup=` parameter. A request with a realistic browser user agent and referer was not attempted automatically (the harness running this session blocks sending a spoofed browser identity as a matter of policy), so it is possible, but not confirmed, that the page still works for an actual human browsing it normally. | A human should open the three URLs above in a real browser, and if the file downloads there, save the three CSVs into `data/raw/bts_lookup/` using the filenames `L_UNIQUE_CARRIERS.csv`, `L_AIRPORT_ID.csv`, `L_CANCELLATION.csv`. If the browser also fails or shows the same redirect, say so and we will look for BTS's current documented path to these lookup tables rather than guessing at one. Per the brief's own instruction, no mirror or third-party copy should be substituted without asking first. |

Per hard rule 2 (no row is silently dropped) this does not block S1-S3,
which downloaded successfully and are not affected by this.
