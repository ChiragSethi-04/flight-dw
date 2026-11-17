# Task 7: OLAP and analytics plan

All six business questions are implemented in `sql/07_olap_queries.sql`
and run against the real warehouse; every number below is from
`exports/` (see `docs/walkthrough/phase6.md` for the full run).

## Q1: worst routes and carriers

The worst route by on-time rate, with a 500-flight minimum to avoid
small samples, is **ORD-ASE at 55.2%** (959 flights), against a
system-wide on-time rate of 77.5%. Chart: `exports/charts/
q1_worst_routes_ranked_bar.png`.

## Q2: delay causes

Across the full year, late-aircraft delay is the single largest cause:

| Cause | Share of 111,934,625 total delay-cause minutes |
|---|---|
| Late aircraft | 39.2% |
| Carrier | 32.5% |
| NAS (air traffic system) | 21.9% |
| Weather | 6.4% |
| Security | 0.1% |

Chart: `exports/charts/q2_delay_causes_stacked_bar.png`, rolled up
month to quarter to year with `GROUP BY ... WITH ROLLUP`.

## Q3: weather impact

Average arrival delay and cancellation rate both rise with
precipitation severity: 4.4 minutes / 0.94% cancellation rate at
"none" versus 27.4 minutes / 5.13% at "extreme"
(`exports/q3_weather_impact.csv`, weighted across 7,001,619 flights).
Chart: `exports/charts/q3_weather_impact_grouped_bar.png`.

## Q4: riskiest airports and times

Early-morning departures are reliably good across every one of the 20
busiest airports (on-time rate 87-93%); afternoon and evening are
worse everywhere, worst at **DCA at night, 60.4%** on-time.
Chart: `exports/charts/q4_airport_time_heatmap.png`. The year-to-
weekday rollup is `exports/q4b_ontime_rollup_year_to_weekday.csv`.

## Q5: delay propagation

Late-aircraft delay share, among the 10 busiest airports, rises
through the operating day and peaks at **8 p.m. at LAS, 62.8%** of
that hour's delay-cause minutes (one earlier, 2 a.m. reading of 100%
was excluded from this headline number: it was a single flight, 21
total delay-cause minutes, not a pattern; see
`docs/walkthrough/phase6.md`). Chart: `exports/charts/
q5_late_aircraft_share_line.png`.

## Q6: carrier comparison

On routes flown by 2 or more carriers, the widest spread is **OO on
BWI-ORD, 102.4 minutes worse than that route's own average**, against
**OO on GUC-DFW, 43.8 minutes better**. Chart: `exports/charts/
q6_carrier_vs_route_diverging_bar.png`.

## Sensitivity check (profiling problem 9)

| Condition | Total flights | On-time rate | Avg arrival delay (min) |
|---|---|---|---|
| All flights | 7,001,619 | 77.48% | 8.50 |
| Excluding outliers | 6,891,498 | 78.73% | 3.28 |
| Excluding diverted | 6,982,361 | 77.69% | 8.50 (unchanged) |
| Excluding both | 6,872,240 | 78.96% | 3.28 |

Outlier flights move the headline KPIs substantially; diverted flights
barely move them, because every one of the 19,258 diverted,
non-cancelled flights in 2025 has `arr_delay_min = NULL` in the
source data (checked directly), so an average that already ignores
NULLs cannot be moved by excluding rows it was never counting.

## Dashboard

Five pages, one per the brief's own list (overview KPIs, routes and
carriers, delay causes, weather impact, time patterns), specified in
full in `docs/dashboard_spec.md`: data source, fields, chart type,
filters and interpretation line for each. Building the actual
dashboard in Power BI or Tableau is human-only and still blocked on
decision 7 (which tool the lecturer approves); the five reporting
views (`vw_kpi_overview`, `vw_routes_carriers`, `vw_delay_causes`,
`vw_weather_impact`, `vw_time_patterns`) and their CSV exports are
ready either way.

## Query performance

The full `sql/07_olap_queries.sql` batch (8 queries + 5 view
creations) ran against the real 7,001,619-row `fact_flight` table in
8 minutes 40 seconds via the raw `mysql` client, using only the
single-column FK indexes already in `sql/03_create_warehouse.sql`.
Reasonable for a one-time batch export; no new indexes were added, see
`docs/walkthrough/phase6.md` for why.
