# Phase 7 walkthrough: findings and report drafts

## What was built

- **`docs/report/01` through `08`**: one markdown file per brief Task
  (Tasks 1-8, corresponding to brief sections 2-9), each drawing only
  on numbers already sitting in `exports/`, `docs/evidence/`,
  `docs/profiling/`, `docs/DECISIONS.md` or a schema artifact, never
  restated from memory.
- **`etl/test_hypotheses.py`**: tests the brief's four hypotheses
  (section 9) for real, against the already-exported Phase 6 output,
  saving the exact evidence to `docs/evidence/hypothesis_testing.txt`.
- **`docs/report/slide_outline.md`**: a 12-minute, 10-slide outline
  with speaker notes and a verbatim live-demo script (one SQL
  drill-down, one dashboard filter), per the brief's own live-demo
  requirement.
- **A real clean-clone test of the README** (this phase's other named
  task): cloned the pushed repository fresh, copied over the
  already-downloaded raw source files (not re-fetched, see below for
  why), and ran every documented command end to end against a brand
  new database.

## Why each choice was made

- **Three of the four hypotheses reuse already-exported CSVs with no
  new database query** (H1 from `q2_delay_causes_by_month.csv`, H3
  from `q3_weather_impact.csv`, H4 from `q6_carrier_vs_route_avg_delay.csv`).
  Only H2 needed one new query (delay by departure band, fleet-wide,
  since Q5 only covered the 10 busiest airports), saved as
  `exports/h2_delay_by_departure_band.csv`. This keeps Phase 7 doing
  what the brief actually asks, "using only the actual query results,"
  rather than re-deriving numbers Phase 6 already computed.
- **None of the four hypotheses was forced to a clean confirm or
  reject.** Two are confirmed with a stated caveat (H1 cleanly; H2 for
  the main operating day, not the overnight hours), and two are
  explicitly called "partly supported" with the specific part that
  does not fit named directly (H3's precipitation data and heavy-snow
  band; H4's near-equal within-route and between-route spread). The
  brief's own instruction ("do not force a result... if the data
  rejects a hypothesis, say so") is treated as a real constraint on
  what gets written, not a disclaimer appended after the fact.
- **The clean-clone test copied `data/raw/` rather than re-downloading
  392 MB of BTS data and 158 MB of NOAA data a third time.** The
  source files themselves do not change, and Phase 1 already verified
  the download logic twice (checksum verification, content-type
  checking, resumability). Re-downloading would cost real time and
  bandwidth while testing something already proven; copying the files
  and then running every other documented step for real, against a
  genuinely new database and a genuinely fresh git checkout, is what
  actually tests the README's accuracy.

## What went wrong and why (real debugging, not hypothetical)

1. **The clean-clone's full `run_all.py` run took 20 minutes, not the
   ~14 minutes the README had claimed from the two Phase 4 runs**, with
   `fact_flight`'s load alone taking 14.3 minutes against ~10 minutes
   before. This was checked rather than silently averaged away: every
   row count matched exactly (7,001,619 `fact_flight` rows, all of
   Phase 5's six validation checks still passing), so this is a real
   timing difference, not a correctness problem. The most likely
   explanation is a cold InnoDB buffer pool on a freshly created
   container and volume, which the two earlier runs did not have
   (they reused an already-warmed-up container). The README now states
   both real numbers instead of only the faster one.
2. Running `pandoc` on `docs/report/` was mentioned as a conversion
   option in the README but `pandoc` is not installed in this project's
   dev environment, and hard rule "do not install system packages
   without asking" applies. The README says so explicitly rather than
   implying the command was run and confirmed.

## How the pieces connect

`etl/test_hypotheses.py` reads `exports/*.csv` the same way a BI tool
reading the dashboard views would, not the database directly, for
three of the four hypotheses, which is a deliberate way of proving the
Phase 6 exports are sufficient on their own to answer the brief's
findings requirement, not merely a byproduct of it. `docs/report/`'s
eight Task files and the hypothesis findings are two different kinds
of writing: Tasks 1-7 describe what was built and why; Task 8 and the
hypothesis evidence describe what the data actually says, kept
separate so a reader can tell "design decision" apart from "finding."

## Acceptance check run: clean-clone test

```
$ git clone https://github.com/ChiragSethi-04/flight-dw.git <clean-dir>
$ cd <clean-dir>
$ cp <main-checkout>/data/raw -r data/raw   # source files only; not re-downloaded
$ cp <main-checkout>/.env .env              # same local dev placeholder values
$ python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
$ docker compose up -d                       # fresh named volume: clean-clone-test_flight_dw_mysql_data
$ python run_all.py --check-db
MySQL connection OK, SELECT 1 returned: 1
$ python run_all.py --status
  [... all 16 step names printed correctly ...]
$ time python run_all.py
  [... real log, matching every number from the original Phase 4/5/6 runs ...]
fact_flight: 7001619 rows
exception_log: 4 distinct unmatched code(s) logged
run_all finished, load_id=97ce48bc-6420-4d67-8549-d77d3a3a05fb
python run_all.py  34.19s user 4.42s system 3% cpu 20:02.08 total
$ python -m pytest -q
42 passed in 0.75s
$ python -m etl.audit
  [... all six checks PASS, identical to docs/evidence/validation_20261117T105315Z.txt ...]
$ python -m etl.export_olap
  [... every CSV, chart and caption identical to the original Phase 6 run,
       a fresh 3-number spot check (different random picks: MIA-MEM,
       February 2025, ORD-IAH/AA) again all MATCH ...]
```

Every documented command in the README ran, in the documented order,
against a database that had never seen this data before, and produced
exactly the same real numbers as the original build. This is the
strongest idempotency evidence in the whole project: not two runs on
the same long-lived container, but a third run on a brand new one,
from a fresh git checkout, following only the written instructions.
`etl/test_hypotheses.py` was written during this same phase, after the
clean clone had already been created from the pushed repository, so it
was not part of this particular clean-clone test; it was run directly
against the main checkout instead (see the Hypothesis 1-4 sections
above), and will be covered by this same clean-clone check the next
time this project clones and tests itself.

## What is still [HUMAN]-only

Everything in `docs/BUILD_PLAN.md` Phase 8: the professor's
confirmation of the five points in brief section 11, confirming the
AI-use policy, reading and reworking this report in the team's own
words, building and exporting the actual dashboard, individual
contribution statements, the peer evaluation, and the live demo
itself. None of this phase's writing substitutes for any of those.

## Likely examiner questions

1. **Why are two of the four hypotheses only "partly supported"
   instead of a clean yes or no?**
   Because the data itself does not support a clean answer for either.
   H3's cancellation-rises-faster-than-delay pattern holds for light
   and moderate snow but not for precipitation alone, and heavy snow
   shows the opposite of the hypothesis (lower disruption than no
   snow at all). H4's "it's the route, not the carrier" holds for
   about three-quarters of multi-carrier routes but not for a real
   tail where one carrier clearly underperforms its peers on the
   identical route. Reporting a forced clean answer would misrepresent
   what was actually found.

2. **Why does heavy snow show less disruption than light or moderate
   snow? Isn't that backwards?**
   Checked, not assumed: heavy-snowfall days (over 50mm in a day) are
   the most common non-zero snow band by flight count (1.1 million
   flights), and a station-level check shows they cluster in states
   with established winter aviation operations (Colorado, Michigan,
   North Dakota, New York). A light dusting of snow at an airport not
   set up to handle any snow at all plausibly causes more
   disproportionate disruption than heavy snowfall at a hub built for
   it. This is association-level reasoning, stated as such, not a
   proven causal claim, since the warehouse has no direct measure of
   an airport's snow-handling capacity.

3. **How is "every number traces to a file in exports/ or
   docs/evidence/" actually enforced, not just claimed?**
   Three of the four hypotheses are computed by scripts
   (`etl/test_hypotheses.py`) reading the committed CSV exports
   directly, not by hand-typing numbers while looking at a terminal.
   The fourth (H2) runs one new SQL query and saves its own result to
   a new CSV before the number is used anywhere. The saved evidence
   file (`docs/evidence/hypothesis_testing.txt`) and the report's
   numbers were cross-checked to match exactly before this phase was
   called done.

4. **Why copy `data/raw/` into the clean clone instead of
   re-downloading, if the point is to test from a truly clean state?**
   The README's own two sections are separate on purpose:
   "Downloading the source data" and "Reproducing the full pipeline"
   are two different steps, and a reviewer who already has the data
   does not re-download it either. The clean-clone test exercises
   every other documented step (schema, staging, all seven dimensions,
   both facts, validation, OLAP export) against a database that had
   genuinely never seen this data before; it is not a test of the
   download logic, which Phase 1 already tested twice, including
   finding and fixing two real bugs there.

5. **The pipeline took 14 minutes twice and then 20 minutes on the
   third run. Doesn't that contradict "idempotent"?**
   No: idempotent means running it again produces the same result, not
   the same wall-clock time. All three runs produced byte-identical
   row counts in every table and passed all six validation checks.
   The timing difference is attributed to a cold container with no
   warmed-up database cache, a reasonable, checkable explanation,
   not waved away or hidden by only reporting the faster number.

6. **Do the slide outline's numbers match the report, or were they
   written separately and could drift?**
   They are the same numbers (39.2% late-aircraft share, 55.2% for
   ORD-ASE, the four hypothesis verdicts), restated for a 1-minute
   slide instead of a paragraph, not independently recalculated or
   rounded differently in the two places.
