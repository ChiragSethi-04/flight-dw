# Phase 5 walkthrough: validation

## What was built

- **`sql/06_validation_checks.sql`**: the six checks from brief
  section 6, each a standalone, re-runnable `SELECT`. Its own output
  is the evidence; nothing is computed separately from what MySQL
  actually returns.
- **`etl/audit.py`** extended with `run_validation_checks()` (runs
  every statement in the SQL file, skipping the leading `USE
  flight_dw` which returns no rows) and a `main()` that prints the
  results and saves them to both `logs/validation_<timestamp>.txt`
  and `docs/evidence/validation_<timestamp>.txt`.
- **`etl/load_facts.py`** gained `log_exceptions()`, called from
  `load_fact_flight()`: every distinct code that fails to match a
  dimension (and so resolves to the `-1` Unknown member) is now
  actually written to `exception_log`, which the brief promises but
  which Phase 4's original implementation never did.

## Why each choice was made

- **Checks 2 (orphan keys) and 3 (uniqueness) are structurally
  guaranteed to pass**, since `fact_flight` has real `FOREIGN KEY`
  and `UNIQUE KEY` constraints that would reject a violating row at
  insert time. They are still written as explicit queries and run for
  real, because the brief's evidence list wants to see the zero, not
  only be told a constraint exists that would prevent a nonzero one.
- **`log_exceptions()` groups by code first, then compares in
  Python**, not a `LEFT JOIN ... WHERE IS NULL` against 7 million
  rows. The first version of this function used exactly that
  anti-pattern and was caught doing it (see below): the third time
  this project has hit the same mistake, after Phase 2's `NOT IN`
  stall and Phase 4's territory investigation.
- **Check 6 counts every row in each dimension, including the `-1`
  row**, rather than reusing the "real rows only" counts
  `etl/load_dims.py`'s own functions print. This is deliberate: a
  snapshot meant to be diffed between two runs should capture the
  whole table, not a subset, even though it means the numbers here
  are consistently one higher than the ones Phase 4's walkthrough
  quotes for the same tables.

## What went wrong and why (real debugging, not hypothetical)

1. **`exception_log` had been sitting at 0 rows since Phase 4, which
   turned out to be a real gap, not a sign that nothing was ever
   unmatched.** Checking it directly as part of preparing this phase's
   evidence found it empty despite Phase 4 and Phase 2 both having
   already found two genuinely unmatched airport codes (`XWA`, `EAR`).
   The `-1` Unknown fallback was working; the brief's separate promise
   to also log the code ("written to an exception report") had simply
   never been implemented. Fixed by adding `log_exceptions()`.

2. **The first version of `log_exceptions()` repeated the exact
   performance mistake this project had already found and fixed
   twice.** It used `LEFT JOIN dim_airport d ON ... WHERE d.airport_key
   IS NULL GROUP BY s.Origin` directly against `stg_bts_flights`
   (7 million rows), and did not return within a reasonable time.
   Rewritten the same way both earlier instances were fixed: group the
   source column down to its few hundred distinct values first, pull
   the small set of known dimension codes separately, and compare the
   two small sets in Python. Completed in under a minute.

## How the pieces connect

`log_exceptions()` runs as part of `etl/load_facts.py`'s
`load_fact_flight()`, right after the fact load, using the same
`load_id` as the rest of that `run_all.py` run, so an exception row can
be traced back to the exact run that produced it.
`run_validation_checks()` is independent of any particular load: it
always reads whatever is currently in the warehouse, which is why it
can be re-run on its own (`python -m etl.audit`) without re-running the
whole pipeline.

## Acceptance check run

```
$ python -m etl.audit
== check1_row_reconciliation ==
check_name  staged_rows  fact_rows  rejected_rows  fact_plus_rejected  result
check1_row_reconciliation  7001619  7001619  0  7001619  PASS

== check2_orphan_keys ==
check_name  fk_column  orphan_count
... (all nine FK columns)  0

== check3_uniqueness ==
check3_uniqueness  0

== check4_cause_totals ==
check4_cause_totals  1534638  14

== check5_dimension_counts ==
dim_carrier  14  14  0
dim_airport  352  1269  2

== check6_rerun_snapshot ==
366  25  1270  15  6939  10  266  1269  334896  7001619

Saved to logs/validation_20261117T105315Z.txt and
docs/evidence/validation_20261117T105315Z.txt
```

**All six checks pass, with no exceptions needed.** Check 4's 14
mismatches out of 1,534,638 qualifying rows exactly reproduces Phase
2's profiling finding on the raw staging data (`docs/profiling/summary.md`),
now confirmed again on the loaded warehouse data: the cause-sum rule
holds 99.999% of the time, and the 14 real exceptions are reported, not
hidden, exactly as the brief asks. Check 5 confirms `dim_carrier` is
exactly complete (14 source codes, 14 dimension rows, 0 unmatched) and
`dim_airport` has exactly 2 unmatched codes (`XWA`, `EAR`), both now
also present in `exception_log`. Check 6's snapshot, taken after two
confirmed-identical full `run_all.py` runs (Phase 4), stands as the
re-run evidence.

## What is still [HUMAN]-only

Per `docs/BUILD_PLAN.md` Phase 5: taking the actual screenshots for the
report (table creation, row counts, the orphan-key query returning
zero, in MySQL Workbench) is explicitly not something this tooling can
do. The queries and their real text output above are the evidence
Claude Code can produce; the screenshots of your own screen running
them are yours to take.

## Likely examiner questions

1. **If checks 2 and 3 can never fail because of the database's own
   constraints, why run them at all?**
   Because "a constraint exists that should prevent this" and "this
   query returns zero, checked directly" are different kinds of
   evidence. The brief's evidence list specifically asks for the
   second kind: a query that returns zero, not an assurance.

2. **Why does `exception_log` have 4 rows for only 2 distinct bad
   codes?**
   Each code is checked against two roles (`Origin` and `Dest`)
   separately, since a code can appear in either position and the
   check is written per-column. `XWA` and `EAR` each appear as both an
   origin and a destination somewhere in the real 2025 data, so each
   gets one row per role: 2 codes x 2 roles = 4 rows.

3. **Check 6 says `dim_date` has 366 rows, but Phase 4 said 365. Which
   is right?**
   Both, for what each is counting. 365 is the real generated calendar
   rows for 2025; 366 is that plus the dimension's permanent `-1`
   Unknown row. Check 6 deliberately counts the whole table, since a
   snapshot meant to catch any kind of change between two runs should
   not quietly exclude a row just because it is not a "real" one.

4. **How do you know check 4's 1,534,638 and 14 are not coincidentally
   repeating a bug from Phase 2, rather than confirming the number is
   right?**
   They are independent computations over different data: Phase 2's
   version ran in Python-adjacent SQL against the raw text `stg_bts_flights`
   columns, casting on the fly; this phase's version runs against
   `fact_flight`'s already-typed `SMALLINT` columns, populated by a
   completely separate `INSERT ... SELECT` in Phase 4. Getting the same
   answer from two different code paths over the same underlying
   facts is exactly the kind of agreement that builds confidence,
   not a sign of a shared bug (a shared bug would need the same
   mistake made twice, independently, with the same effect on the
   answer, which is a much less likely coincidence than the rule
   simply being right).

5. **Why was the `LEFT JOIN ... WHERE IS NULL` mistake made a third
   time, if it had already been found and fixed twice?**
   Because each instance was a new piece of code solving what looked
   like a new, specific problem, not a copy-paste of the earlier
   broken query. The lesson ("group first, then compare small sets")
   was understood abstractly after the first fix but still had to be
   actively remembered and applied by hand each time a new query
   needed it, rather than being enforced automatically. Worth naming
   directly: this is a real limitation of fixing a problem case by
   case instead of building a reusable, safe helper for "find distinct
   values in a huge table not present in a small reference set" once
   and reusing it everywhere.
