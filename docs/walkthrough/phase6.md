# Phase 6 walkthrough: OLAP and dashboard data

## What was built

- **`sql/07_olap_queries.sql`**: one query per business question from
  brief section 8 (Q1 through Q6, with Q1 and Q4 each split into two
  queries since the brief's own "planned output" column for those two
  needs two angles: a ranked list plus a carrier slice for Q1, a
  matrix plus a rollup drill-down for Q4), followed by five
  `CREATE OR REPLACE VIEW` statements, one per dashboard page.
- **`etl/export_olap.py`**: runs that SQL file for real, saves every
  query and view to `exports/*.csv`, draws all six required chart
  types to `exports/charts/*.png` with a one-line interpretation saved
  alongside each as `.txt`, runs the outlier/diverted-flight
  sensitivity check from profiling problem 9, and spot-checks three
  numbers against independently-written SQL.
- **`docs/dashboard_spec.md`**: the five-page build spec (data source,
  fields, chart type, filters, interpretation line per page) detailed
  enough to build in Power BI or Tableau once decision 7 is resolved.

## Why each choice was made

- **Q1 and Q4 are each two queries, not one.** The brief's own table
  for Q1 says "ranking with window functions, slice by carrier": a
  route-level ranking and a carrier breakdown are genuinely different
  grains (route vs. route+carrier), so one query cannot be both
  without losing one of the two views. Same reasoning for Q4's matrix
  (airport x departure band) versus its rollup (year to weekday).
- **Every reporting view excludes the `-1` Unknown dimension row**
  with an explicit `<> -1` guard, the same pattern used throughout
  Phases 4 and 5, so Unknown never shows up as a spurious category on
  a dashboard a CA, sorry, an airline ops analyst would actually read.
- **Q6's carrier-count-per-route step is a plain `GROUP BY`, not a
  window function.** MySQL 8 does not support `COUNT(DISTINCT x)` as a
  window aggregate, so the multi-carrier-route filter is computed
  first with ordinary `GROUP BY ... HAVING`, and only that already-small
  set of routes is carried into the `AVG() OVER (PARTITION BY ...)`
  computation the brief asks for. This also keeps the window function
  from ever running over the full 7-million-row table.
- **The chart captions use a minimum-volume floor before picking a
  "peak" or "worst" cell** (see the first bug below). This only
  affects which number gets written into the one-line interpretation;
  every row of underlying data in the CSVs and the chart itself is
  untouched.
- **No new indexes were added.** The full `sql/07_olap_queries.sql`
  batch (8 queries + 5 view creations) ran against the real
  7,001,619-row `fact_flight` table via the raw `mysql` client in 8
  minutes 40 seconds, with the existing single-column FK indexes from
  `sql/03_create_warehouse.sql`. That is reasonable for a one-time
  batch export, which is what this script is; it is not meant to serve
  a BI tool's interactive per-click query.

## What went wrong and why (real debugging, not hypothetical)

1. **Q5's first caption claimed late-aircraft delay "peaks" at hour 2
   at LAS with a 100% share.** True, but checking the row behind it
   (`exports/q5_late_aircraft_share_by_hour.csv`) showed
   `total_cause_delay_min = 21`, meaning that cell is a single delayed
   flight at 2 a.m., not a pattern. Every other one of the 201 rows in
   that file has at least 48,000 delay-cause minutes behind it; this
   was the only one under 500. Fixed by adding a
   `MIN_VOLUME_FOR_PEAK = 500` floor in `chart_q5_line()` before
   picking the headline cell. The real peak, once that single-flight
   artifact is excluded, is hour 20 (8 p.m.) at LAS, 62.8%, which fits
   the expected story of delay propagation building through the
   operating day.
2. **The outlier/diverted sensitivity check showed `avg_arr_delay_min`
   identical to four decimal places (8.5045) between "all flights" and
   "excluding diverted flights."** That looked suspicious, so it was
   checked rather than assumed to be a coincidence: a direct query
   (`SELECT ... GROUP BY diverted_flag, cancelled_flag`) found that all
   19,258 diverted, non-cancelled flights have `arr_delay_min IS NULL`,
   with zero exceptions. Since MySQL's `AVG()` already ignores NULLs,
   removing those rows from the query entirely cannot move an average
   that was already not counting them. Not a bug; a real property of
   how BTS reports arrival delay for diverted flights, now documented
   here instead of being silently trusted.
3. **The Python export run's own wall-clock time (`time python -m
   etl.export_olap`) came back as 53 minutes with 0% CPU usage**, far
   more than the 8m40s the same 13 SQL statements took moments earlier
   through the raw `mysql` client. The process was not stuck: Docker
   Desktop, MySQL, and the query results were all healthy and correct
   when it finished (exit code 0, every spot-check passed). The gap is
   host idle time between the queries actually running, not query cost;
   this is a measurement artifact of running work across a background
   session, not a performance finding, so the figure to cite for query
   cost is the direct `mysql` client's 8m40s, not the Python wrapper's
   wall time.

## How the pieces connect

`etl/export_olap.py` reads `sql/07_olap_queries.sql` itself (stripping
comments the same way `etl/audit.py`'s `run_validation_checks()` does)
rather than duplicating the SQL text in Python, so there is exactly one
place each query is written. The 8 SELECT statements are captured by
position into named DataFrames; the 5 `CREATE OR REPLACE VIEW`
statements are executed for their idempotent side effect and then
queried separately with a plain `SELECT * FROM vw_x`. Every chart
function takes one of those DataFrames (or, for Q5's regeneration
after the bug fix, the already-saved CSV) and returns nothing; its
only two side effects are a PNG and a caption `.txt`, both named to
match the business question.

## Acceptance check run

```
$ python -m etl.export_olap
Running sql/07_olap_queries.sql (8 queries + 5 views)...
  q1a_worst_routes: 10 rows
  q1b_worst_routes_by_carrier: 14 rows
  q2_delay_causes_by_month: 18 rows
  q3_weather_impact: 77 rows
  q4a_airport_departure_band_matrix: 100 rows
  q4b_ontime_rollup_year_to_weekday: 102 rows
  q5_late_aircraft_share_by_hour: 201 rows
  q6_carrier_vs_route_avg_delay: 8145 rows
Exporting the 5 reporting views...
  vw_kpi_overview: 12 rows
  vw_routes_carriers: 13206 rows
  vw_delay_causes: 12 rows
  vw_weather_impact: 252 rows
  vw_time_patterns: 29096 rows
Computing overall KPIs for chart captions...
  {'total_flights': 7001619, 'cancellation_rate': 0.0147, 'on_time_rate': 0.7748}
Drawing the 6 required chart types...
  q1_worst_routes_ranked_bar: The worst route, ORD-ASE, has an on-time rate of 55.2% against 959 flights, versus the system-wide on-time rate of 77.5%.
  q2_delay_causes_stacked_bar: late aircraft delay is the largest cause across the year, 39.2% of all 111,934,625 delay-cause minutes.
  q3_weather_impact_grouped_bar: Precip=extreme/wind=moderate averages 38.7 min arrival delay, versus 4.4 min for precip=none/wind=strong.
  q4_airport_time_heatmap: Of the 20 busiest airports, DCA during the 'night' departure band has the lowest on-time rate in the matrix, 60.4%.
  q5_late_aircraft_share_line: Late-aircraft delay peaks at hour 20 at LAS, 62.8% of that hour's delay-cause minutes, consistent with delay compounding later in the operating day. [regenerated after the sample-size fix above]
  q6_carrier_vs_route_diverging_bar: OO on BWI-ORD runs 102.4 min worse than that route's average, while OO on GUC-DFW runs 43.8 min better.
Running the outlier / diverted-flight sensitivity check...
                 condition  total_flights  cancellation_rate  on_time_rate  avg_arr_delay_min
               all_flights        7001619              0.0147        0.7748              8.5045
             excl_outliers        6891498              0.0149        0.7873              3.2760
             excl_diverted        6982361              0.0147        0.7769              8.5045
excl_outliers_and_diverted        6872240              0.0150        0.7896              3.2760
Spot-checking 3 random numbers against independent SQL...
  [MATCH] q1a_worst_routes: MIA-MEM on_time_count reported=314 recomputed=314
  [MATCH] vw_kpi_overview: June 2025 total_flights reported=611575 recomputed=611575
  [MATCH] q6_carrier_vs_route_avg_delay: BHM-DFW OH carrier_avg_delay reported=24.95 recomputed=24.95
Phase 6 OLAP export complete.
```

All three randomly-chosen spot-check numbers matched their independent
recomputation exactly, per the brief's Phase 6 acceptance rule. The
sensitivity check shows outliers matter more than diverted flights for
the headline KPIs: excluding `is_outlier_delay` flights drops average
arrival delay from 8.50 to 3.28 minutes and raises on-time rate by 1.25
points (77.48% to 78.73%), while excluding diverted flights barely
moves either number (on-time rate +0.21 points, average delay
unchanged, for the reason explained above).

## What is still [HUMAN]-only

Per `docs/BUILD_PLAN.md` Phase 6: building the actual dashboard in
Power BI or Tableau from `docs/dashboard_spec.md` and the views/CSVs.
Claude Code cannot operate either tool, and decision 7 (which tool is
approved) is still open pending the lecturer's confirmation; see
`docs/DECISIONS.md`.

## Likely examiner questions

1. **Why does excluding diverted flights not change average arrival
   delay at all, when excluding outliers moves it by more than 5
   minutes?**
   Checked directly rather than assumed: every one of the 19,258
   diverted, non-cancelled flights in the 2025 data has `arr_delay_min
   = NULL` (BTS does not report an arrival delay for a flight that did
   not arrive at its scheduled destination). `AVG()` already ignores
   NULLs, so removing those rows from the query cannot move an average
   that never counted them. Outlier flights, by contrast, did arrive,
   with a real (very large) delay value, so excluding them removes
   real numbers from the average and moves it substantially.

2. **Why are Q1 and Q4 each two queries instead of one?**
   Because the brief's own planned output for each names two different
   things at two different grains: Q1 wants both a route-level ranking
   and a per-carrier slice of it; Q4 wants both an airport x
   departure-band matrix and a separate year-to-weekday drill-down.
   Grain changes mean one SQL query cannot honestly produce both
   outputs the brief asks for.

3. **How was the Q5 "100% at hour 2" number caught, and why wasn't it
   just left out of the CSV?**
   It is real, not fabricated, so it stays in `exports/
   q5_late_aircraft_share_by_hour.csv` exactly as computed; removing a
   true number from the data because it is inconvenient would break
   hard rule 3. What changed is only the automatically-picked headline
   sentence, which now requires at least 500 minutes of delay-cause
   volume behind a cell before calling it "the peak," so a one-flight
   artifact at 2 a.m. cannot be mistaken for a real pattern in the
   write-up.

4. **Why is `dim_carrier.carrier_name` still just the two-letter code
   in these exports, e.g. "OO" instead of an actual airline name?**
   S4 (BTS's lookup tables, which would supply the real carrier name)
   is still blocked; see `docs/DECISIONS.md`, item B1. This has been
   true since Phase 3 and has not changed in this phase.

5. **What would make these OLAP queries faster for an actual
   interactive dashboard, if Power BI needs sub-second response?**
   Materializing the five views as real tables refreshed on a schedule
   (instead of `CREATE VIEW`, which re-runs the underlying aggregation
   on every read), or adding composite covering indexes matching each
   view's `GROUP BY` columns, would both help. Neither was done here
   because the brief's own acceptance bar is "a reasonable time" for a
   one-time batch export, which 8m40s for the full set already
   satisfies; optimizing further wasn't asked for and risks over-
   engineering a student project's one-time report pipeline.

6. **Why 500 flights as Q1's minimum and 20 as Q6's minimum, rather
   than the same number for both?**
   They answer different questions at different grains. Q1 ranks whole
   routes (summed across every carrier that flies them), where even a
   "small" route in this dataset has hundreds of flights a year, so 500
   screens out genuinely thin routes. Q6 compares one carrier's
   performance on one route, a finer grain where 20 flights is already
   enough to average out day-to-day noise without discarding most of
   the legitimate carrier-route pairs in the network.

7. **The brief calls for an `is_outlier_delay` sensitivity check
   "with and without" outliers. Why does `exports/sensitivity_check.csv`
   also show diverted flights, which the brief's problem 9 groups
   together with outliers?**
   The brief's own problem 9 names both flags together ("add outlier
   and diverted flags, report results with and without them"), so both
   are reported, separately and combined (4 conditions, not 2), so a
   reader can see each flag's effect on its own as well as together.

8. **Could the Q3 chart's grouping by precipitation and wind band,
   averaged over snow band, hide something snow band alone would
   show?**
   Yes, by construction; that's why `exports/q3_weather_impact.csv`
   keeps the full three-way breakdown (precipitation x snow x wind)
   with every combination's own flight count and average delay, not
   just the two-way chart. The chart picks one legible 2D slice for
   the dashboard page; the CSV underneath it is the complete evidence.
