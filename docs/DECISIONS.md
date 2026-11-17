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

## Open decisions from the brief (still OPEN, need the team or profiling evidence)

| # | Topic | Brief's recommendation | Status |
|---|---|---|---|
| 3 | Wind (AWND) coverage threshold | Decide after profiling | **Evidence ready, still OPEN.** Phase 2 profiling (`docs/profiling/summary.md`, 2026-11-17): of 1,225 distinct nearest stations actually used across US airports, only 711 (58.0%) report AWND at all. The team needs to pick: take wind from the nearest station that has it within the distance threshold (decision 5), or accept NULL and flag for the other 42%. |
| 4 | Midnight (2400) handling detail | Decide after counting occurrences | **Evidence ready, still OPEN.** Phase 2 profiling: 4,470 of 7,001,619 rows (0.064%) have a 2400 value in at least one time field (CRSDepTime=1, DepTime=747, CRSArrTime=2, ArrTime=3720). A preview mapping (2400 to 0000, FlightDate unchanged) is shown in `docs/profiling/problem2_after_10rows_proposed.csv`, but this is not the decided rule; the team still needs to confirm the exact handling, especially whether any downstream full-timestamp construction needs the date rolled forward. |
| 5 | Airport-to-station distance threshold | Set from the profiled distance histogram | **Evidence ready, still OPEN.** Phase 2 profiling: across 1,249 US airports (2 excluded as mislabeled OpenFlights reference rows, see Phase 2 walkthrough), distances to the nearest GHCN station are heavily concentrated near zero (median 0.70km, p90 3.03km), with a long thin tail out to 94.60km for a handful of rural Alaska airports. See `docs/profiling/problem7_distance_histogram.csv`. The team needs to pick the actual cutoff (for example 75km or 100km) and what happens to airports beyond it (fallback station vs flagged no-weather). |
| 6 | SCD Type 2 evidence for `dim_carrier` | Use BTS carrier history dates; if no real change appears, demonstrate on a labelled test case | OPEN. Needs Phase 4 implementation and a look at the actual year's carrier history. |
| 7 | Dashboard tool (Power BI vs Tableau vs neither) | Subject to lecturer approval | OPEN. Needs the professor's confirmation (brief section 11, point 1). |

None of these are decided yet. Each gets a row added above with a date,
reason and who decided it, once resolved.

## Blockers needing human action

| # | Topic | What was tried | What is needed |
|---|---|---|---|
| B1 | S4 BTS lookup tables (carrier names, airport IDs, cancellation codes) | On 2026-11-17, `data/download_sources.py` tried `https://www.transtats.bts.gov/Download_Lookup.asp?Lookup=L_UNIQUE_CARRIERS` (and `L_AIRPORT_ID`, `L_CANCELLATION`). Every attempt returns HTTP 302 to `Homepage.asp`, including with a session cookie carried from a prior request to the same page with no `Lookup=` parameter. A request with a realistic browser user agent and referer was not attempted automatically (the harness running this session blocks sending a spoofed browser identity as a matter of policy), so it is possible, but not confirmed, that the page still works for an actual human browsing it normally. | A human should open the three URLs above in a real browser, and if the file downloads there, save the three CSVs into `data/raw/bts_lookup/` using the filenames `L_UNIQUE_CARRIERS.csv`, `L_AIRPORT_ID.csv`, `L_CANCELLATION.csv`. If the browser also fails or shows the same redirect, say so and we will look for BTS's current documented path to these lookup tables rather than guessing at one. Per the brief's own instruction, no mirror or third-party copy should be substituted without asking first. |

Per hard rule 2 (no row is silently dropped) this does not block S1-S3,
which downloaded successfully and are not affected by this.
