# Task 3: Data quality profiling and cleaning plan

`etl/profile.py` ran all nine of the brief's expected data-quality
problems, plus a tenth found along the way, against the real staged
data (7,001,619 rows in `stg_bts_flights`, 7,698 rows in
`stg_airports`). Full detail and the before/after sample CSVs are in
`docs/profiling/summary.md`; the real counts are summarized here.

| # | Problem | Result | Real count | Rule applied |
|---|---|---|---|---|
| 1 | Cancelled flights have empty time/delay fields | Confirmed | 102,876 rows (1.47%) | Keep the row, flag cancelled, keep delay measures NULL, exclude from delay averages, include in cancellation rate |
| 2 | Midnight stored as 2400 | Confirmed | 4,470 rows (0.064%) | Map 2400 to 0000, flight date unchanged (open decision 4, resolved in Phase 4) |
| 3 | Delay cause fields blank when ArrDelay < 15 | Confirmed | 5,344,846 rows; of 1,534,638 qualifying rows (ArrDelay >= 15), 14 do not sum to ArrDelay (0.001%) | Set causes to 0 below the 15-minute threshold, NULL for cancelled rows, report (not hide) any sum mismatch above it |
| 4 | Airport codes with no match in the reference | Confirmed | 2 distinct unmatched codes | Map to the Unknown member, log to `exception_log` |
| 5 | Duplicate flight records | Refuted | 0 rows share a business key | No rows need the reject path for this reason |
| 6 | Weather values in tenths, -9999 as missing | Deferred to Phase 4 (no per-station data staged yet in Phase 2) | n/a | Divide by 10, convert -9999 to NULL; implemented in `etl/clean.noaa_value` |
| 7 | Station too far from airport | Confirmed as a real spread, threshold open at profiling time | Histogram over 1,249 US airports | Resolved as 75 km in Phase 4 (open decision 5), with real evidence; see `docs/DECISIONS.md` |
| 8 | Most recent BTS months incomplete | Not found in 2025 | All 12 months' staged row counts exactly match their source CSV line counts | No cutoff needed for 2025 |
| 9 | Extreme delay values and diverted flights | Confirmed | 19,258 diverted rows (0.275%), 110,121 rows with arrival delay over 180 minutes (1.573%), max 4,336 minutes | Keep both, add `is_outlier_delay` and use the existing diverted flag, report Phase 6's sensitivity check with and without each |
| 10 (new) | OpenFlights rows with a mislabeled `country` field | Confirmed | 2 airports (`TZR`, `OEL`), real location over 500 km from the nearest US station despite `country = "United States"` in the source | Excluded by location plausibility, not by trusting the `country` field; 0 real 2025 flights reference either, confirmed directly |

## How this fed later phases

Problems 2, 6, 7 and 9 directly produced the real evidence behind four
of this project's seven open design decisions (midnight handling,
wind coverage, the station distance threshold, and the
`is_outlier_delay` addition); see `docs/DECISIONS.md` for exactly how
each number above became a decision. Problem 3's 14-mismatch count
was independently reproduced a second time in Phase 5 against the
already-loaded `fact_flight` table (a different query, different data
state, same answer); see `docs/evidence/validation_20261117T105315Z.txt`,
check 4.
