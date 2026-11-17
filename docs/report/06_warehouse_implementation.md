# Task 6: Warehouse implementation

## What is built

`sql/03_create_warehouse.sql` creates the full star schema: 2 fact
tables, 7 dimensions, `airport_station_map`, plus three traceability
tables required by hard rules 1 and 2: `reject_flights`,
`exception_log`, `audit_log`. The script is idempotent (`DROP TABLE IF
EXISTS` in dependency order, then recreate); applying it twice against
an already-built database produces no errors and no duplicate
structures, confirmed directly in Phase 3.

Real row counts, from `docs/evidence/validation_20261117T105315Z.txt`
(check 6) and MySQL Workbench screenshots in
`docs/evidence/screenshots/`:

| Table | Rows |
|---|---|
| `fact_flight` | 7,001,619 |
| `fact_airport_weather_daily` | 334,896 |
| `dim_route` | 6,939 |
| `dim_weather_condition` | 266 |
| `dim_airport` | 1,270 |
| `airport_station_map` | 1,269 |
| `dim_date` | 366 |
| `dim_time_of_day` | 25 |
| `dim_carrier` | 15 |
| `dim_flight_status` | 10 |
| `reject_flights` | 0 |

## Constraints doing real work, not just documentation

Every foreign key above is a real InnoDB `FOREIGN KEY`, not a comment.
`fact_flight` has a real `UNIQUE KEY` on its business key. Both are
demonstrated, not just asserted, by Phase 5's validation checks:

- **Check 2 (orphan keys):** 0 across all nine foreign keys on both
  fact tables.
- **Check 3 (uniqueness):** 0 duplicate business-key groups.

## The six validation checks (brief section 6)

All six pass against the real warehouse, re-run and saved as evidence
in `docs/evidence/validation_20261117T105315Z.txt`:

1. **Row reconciliation:** 7,001,619 staged rows = 7,001,619 fact rows
   + 0 rejected rows.
2. **Orphan keys:** 0.
3. **Uniqueness:** 0 duplicate groups.
4. **Cause totals:** of 1,534,638 qualifying rows (non-cancelled,
   ArrDelay >= 15, all five causes present), 14 do not sum to
   ArrDelay, exactly reproducing profiling problem 3's independent
   count from Phase 2 against a different table and a different query.
5. **Dimension counts:** `dim_carrier` exactly complete (14 source
   codes, 14 dimension rows, 0 unmatched); `dim_airport` exactly 2
   unmatched codes (`XWA`, `EAR`), both logged to `exception_log`.
6. **Re-run test:** two full `run_all.py` runs produced identical row
   counts everywhere (Phase 4).

## Exception handling

`exception_log` records every distinct source code that could not be
matched to a dimension, with the run's `load_id`, the natural key, and
a count of how many fact rows reference it, rather than only silently
resolving it to the `-1` Unknown member. This is a real gap found and
fixed during Phase 5: `exception_log` sat at 0 rows through all of
Phase 4 despite two known unmatched airport codes, because the
logging itself had never been implemented, only the Unknown-member
fallback. See `docs/walkthrough/phase5.md`.
