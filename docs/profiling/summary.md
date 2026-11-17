# Data quality profiling summary

Generated 2026-11-17T08:00:03+00:00 by `etl/profile.py`, against the real staged data
loaded by `etl/extract.py` (7,001,619 rows in `stg_bts_flights`,
7,698 rows in `stg_airports`) and the real NOAA reference files.
Every number below comes from a query or script run against real
data; none is invented (hard rule 3).

## The nine expected problems from section 4 of the brief

| # | Problem | Confirmed? | Count found | % of rows | Proposed rule |
|---|---|---|---|---|---|
| 1 | Cancelled flights have empty time/delay fields | **Confirmed** | 102876 cancelled rows (0 unexpectedly had a non-empty ArrDelay) | 1.47% | Keep row, set a cancelled flag, keep delay measures NULL, exclude from delay averages, include in cancellation rate. See `problem1_before_10rows.csv` / `problem1_after_10rows_proposed.csv`. |
| 2 | Midnight stored as 2400 in time fields | **Confirmed** | 4470 rows (CRSDepTime=1, DepTime=747, CRSArrTime=2, ArrTime=3720) | 0.064% | **Open decision 4, not yet decided.** Preview only: map 2400 to 0000, flight date unchanged (per the locked date rule), roll forward only when a full timestamp is built. See `problem2_before_10rows.csv` / `problem2_after_10rows_proposed.csv`. |
| 3 | Delay cause fields blank when ArrDelay < 15 | **Confirmed** | 5344846 rows; of 1534638 rows with ArrDelay >= 15 and all five causes populated, 14 do not sum to ArrDelay | mismatch 0.001% of qualifying rows | Set causes to 0 for non-cancelled rows with ArrDelay < 15, keep NULL for cancelled rows, report (not hide) any cause-sum mismatch for ArrDelay >= 15. See `problem3_before_10rows.csv` / `problem3_after_10rows_proposed.csv`. |
| 4 | Airport codes with no match in the airport reference | **Confirmed** | 2 distinct unmatched Origin/Dest codes | n/a | Map to the Unknown airport member (key -1), log the code in the exception table. See `problem4_unmatched_airport_codes.csv`. |
| 5 | Duplicate flight records | **Refuted** | 0 rows share a business key with at least one other row | 0.0% | Keep the first row by business key, move the rest to the reject table with reason DUPLICATE. See `problem5_duplicate_business_keys.csv`. |
| 6 | Weather values in tenths of units, -9999 as missing flag | **Deferred to Phase 4** | n/a: no NOAA per-station daily values are staged yet (station selection happens in Phase 3; see `sql/02_create_staging.sql` scope note) | n/a | Will divide by 10 for mm/C/m-s, convert -9999 to NULL, once real per-station data is loaded. Not fabricated here. |
| 7 | Station too far from airport to represent its weather | **Confirmed as a real spread, threshold still open** | distance histogram over 1249 US airports; see `problem7_distance_histogram.csv` | n/a | **Open decision 5, not yet decided.** Evidence produced; threshold to be set by the team from the histogram, not guessed. |
| 8 | Most recent BTS months incomplete due to release lag | **Not found in the chosen year** | all 12 months of 2025 loaded with staged row count exactly matching the source CSV line count (see Phase 1 walkthrough and `row_counts_per_month.csv`); 2025 was verified complete before selecting it (`docs/DECISIONS.md`, decision 1) | 0% | No cut-off needed for 2025; re-check this when adding any later month. |
| 9 | Extreme delay values and diverted flights | **Confirmed** | 19258 diverted rows (0.275%), 110121 rows with arrival delay over 180 minutes (1.5728%), max arrival delay 4336.0 minutes | see above | Keep these rows, add outlier and diverted flags, report OLAP results with and without them (Phase 6 sensitivity check). |
| 10 (new, not in the brief) | OpenFlights rows with a mislabeled `country` field | **Confirmed** | 2 airport(s): ['TZR', 'OEL'], flagged with a raw haversine distance over 500.0km to the nearest US station because their real location (per latitude/longitude) is not in the US at all, despite `country = "United States"` in the source file | 0 real flight rows reference them (checked directly against `stg_bts_flights`; see `problem10_mislabeled_country_outliers.csv`) | Exclude from `dim_airport`/`airport_station_map` by location plausibility, not by trusting the `country` field alone; flag in the exception log if ever referenced by a real flight (none are, in 2025). |

## Open decision 3: wind (AWND) coverage

Of 1225 distinct nearest stations found across US airports, 711 (58.0%) report AWND (average wind speed) at all, per `ghcnd-inventory.txt`. This is real coverage evidence for the team to decide open decision 3 (take wind from the nearest station that has it within the threshold, or accept NULL and flag); not decided here.

## Row reconciliation

`stg_bts_flights` holds 7,001,619 rows across all 12 months of 2025. Every month's staged row count exactly matched its source CSV's data-row count during `etl/extract.py` (no mismatches were logged); since staging performs no filtering, rejected rows = 0 at this stage, so source rows = loaded rows + rejected rows holds trivially (rejection happens during cleaning in Phase 4, against the rules this phase evidenced above).

## What still needs a human decision

Per `docs/BUILD_PLAN.md` Phase 2, open decisions 3 (wind coverage), 4 (midnight handling) and 5 (distance threshold) are informed by the evidence above but not decided by this script. See `docs/DECISIONS.md`.
