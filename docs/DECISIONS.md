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

## Open decisions from the brief (still OPEN, need the team or profiling evidence)

| # | Topic | Brief's recommendation | Status |
|---|---|---|---|
| 1 | Data year | Most recent full calendar year BTS has published in full, fallback 2024 | OPEN. Needs verification of BTS's actual current release status before Phase 1. |
| 2 | Destination weather (`dest_weather_key` on `fact_flight`) | Brief recommends adding it, needs team agreement | OPEN. Needs team sign-off before Phase 3 DDL. |
| 3 | Wind (AWND) coverage threshold | Decide after profiling | OPEN. Needs Phase 2 profiling evidence. |
| 4 | Midnight (2400) handling detail | Decide after counting occurrences | OPEN. Needs Phase 2 profiling evidence. |
| 5 | Airport-to-station distance threshold | Set from the profiled distance histogram | OPEN. Needs Phase 2 profiling evidence. |
| 6 | SCD Type 2 evidence for `dim_carrier` | Use BTS carrier history dates; if no real change appears, demonstrate on a labelled test case | OPEN. Needs Phase 4 implementation and a look at the actual year's carrier history. |
| 7 | Dashboard tool (Power BI vs Tableau vs neither) | Subject to lecturer approval | OPEN. Needs the professor's confirmation (brief section 11, point 1). |

None of these are decided yet. Each gets a row added above with a date,
reason and who decided it, once resolved.
