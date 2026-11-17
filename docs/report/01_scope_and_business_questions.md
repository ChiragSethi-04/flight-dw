# Task 1: Scope, users, business questions and KPIs

## Intended users and decisions

| User | Decision they make |
|---|---|
| Operations control managers | Where to add recovery capacity and buffers during disruption |
| Network and schedule planners | Which routes and departure times need schedule changes |
| Airport station managers | Staffing and turnaround planning by airport and hour |
| Executives | Which carriers, hubs and seasons drive the most delay cost |

## Business questions

| # | Question | Main users | Answered by |
|---|---|---|---|
| Q1 | Which routes and carriers have the highest delay and cancellation rates? | Planners, executives | `sql/07_olap_queries.sql` Q1a/Q1b, `exports/q1a_worst_routes.csv`, `exports/q1b_worst_routes_by_carrier.csv` |
| Q2 | What share of total arrival delay comes from each cause? | Operations, executives | Q2, `exports/q2_delay_causes_by_month.csv` |
| Q3 | How do precipitation, snow and wind at an airport change its delay and cancellation rates? | Operations, station managers | Q3, `exports/q3_weather_impact.csv` |
| Q4 | Which airports, hours, days and months are riskiest? | Station managers, planners | Q4a/Q4b, `exports/q4a_airport_departure_band_matrix.csv`, `exports/q4b_ontime_rollup_year_to_weekday.csv` |
| Q5 | How much delay is passed on by late inbound aircraft, and where does it build up? | Operations, planners | Q5, `exports/q5_late_aircraft_share_by_hour.csv` |
| Q6 | Which carriers perform better or worse than peers on the same routes? | Executives, planners | Q6, `exports/q6_carrier_vs_route_avg_delay.csv` |

All six are implemented and run against the real 2025 warehouse; see
`docs/walkthrough/phase6.md` for the full acceptance run.

## KPIs

Every KPI below is computed exactly as defined here throughout the
project (`CLAUDE.md`), with no exceptions. Non-cancelled flights unless
stated.

$$\text{On-time rate} = \frac{\#\{\text{ArrDelay} < 15\}}{\#\{\text{non-cancelled flights}\}}$$

$$\text{Cancellation rate} = \frac{\#\{\text{cancelled}\}}{\#\{\text{scheduled flights}\}}$$

$$\text{Weather delay share} = \frac{\sum \text{WeatherDelay}}{\sum \text{(Carrier+Weather+NAS+Security+LateAircraft)}}$$

$$\text{Late-aircraft share} = \frac{\sum \text{LateAircraftDelay}}{\sum \text{all five causes}}$$

Average arrival delay, average departure delay and average taxi-out are
plain means over non-cancelled flights. Delay minutes by cause is the
sum of the five reported cause fields. All eight KPIs (the four above
plus average arrival delay, average departure delay, average taxi-out,
and delay minutes by cause) are available in `exports/vw_kpi_overview.csv`
and `exports/vw_delay_causes.csv`, by month for the full 2025 calendar
year.

The full-year, all-flight values, from `exports/sensitivity_check.csv`:
on-time rate 77.48%, cancellation rate 1.47%, average arrival delay
8.50 minutes (non-cancelled flights).

## Scope

In scope, as built: US domestic flights for one calendar year (2025),
daily weather at origin and destination airports, airport and carrier
reference data, batch loading (`run_all.py`), historical analysis
(`sql/07_olap_queries.sql`). 7,001,619 flight rows and 334,896
airport-day weather rows are loaded; see `docs/walkthrough/phase4.md`.

Out of scope, as built: real-time streaming, ticket prices and
revenue, passenger and crew data, international flights, and
predictive machine learning. None of these were added at any point in
the build; see "If the project continued" in
`docs/report/08_findings_and_limitations.md`.
