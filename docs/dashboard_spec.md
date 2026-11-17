# Dashboard build spec

Five pages, one BI tool (Power BI or Tableau, pending the lecturer's
approval per `docs/DECISIONS.md` item 7) connected either directly to the
MySQL warehouse or to the CSV exports in `exports/` as a fallback. Every
chart below ties to one of the brief's six business questions (section
8) and must carry the one-line interpretation shown, taken verbatim from
the real query output, not reworded or guessed.

Connecting Power BI or Tableau to MySQL needs an ODBC driver or
connector (Power BI: MySQL connector, built in; Tableau: the MySQL
connector, which needs the MySQL Connector/ODBC driver installed
separately). If that connector is not available, every view below also
has a matching CSV in `exports/`, refreshed by `python -m etl.export_olap`,
which any BI tool can read with no driver at all.

## Page 1: Overview KPIs

- **Source**: `vw_kpi_overview` (or `exports/vw_kpi_overview.csv`), grain = one row per month.
- **Fields**: `year`, `month_num`, `month_name`, `total_flights`, `on_time_rate`, `cancellation_rate`, `avg_arr_delay_min`, `avg_dep_delay_min`, `avg_taxi_out_min`, `weather_delay_share`, `late_aircraft_share`.
- **Chart types**: 4-6 KPI cards (on-time rate, cancellation rate, avg arrival delay, total flights, summed or averaged across the year) plus one line chart of `on_time_rate` by month to show the seasonal trend.
- **Filters**: year, month.
- **Interpretation line**: state the full-year on-time rate and cancellation rate, and whether the trend line rises or falls across the year, from the real numbers in the view, not estimated.

## Page 2: Routes and carriers (ties to Q1 and Q6)

- **Source**: `vw_routes_carriers` for the full network; `exports/q1a_worst_routes.csv`, `exports/q1b_worst_routes_by_carrier.csv` and `exports/q6_carrier_vs_route_avg_delay.csv` for the two specific business questions.
- **Fields**: `origin_iata`, `dest_iata`, `carrier_code`, `flight_count`, `on_time_rate`, `cancellation_rate`, `avg_arr_delay_min`, `distance_miles`, `distance_band`.
- **Chart types**:
  - Ranked bar chart (Q1): the 10 worst routes by on-time rate, minimum 500 flights. Matches `exports/charts/q1_worst_routes_ranked_bar.png`.
  - Table or small-multiples (Q1b): per-carrier on-time rate on those same 10 routes.
  - Diverging bar chart (Q6): each carrier's average arrival delay minus its route's own average, on routes flown by 2+ carriers. Matches `exports/charts/q6_carrier_vs_route_diverging_bar.png`.
- **Filters**: carrier, minimum flight count, origin/destination airport.
- **Interpretation line**: name the single worst route and its on-time rate against the system-wide rate (Q1), and the carrier that most outperforms or underperforms its own route average (Q6). See the real captions in `exports/charts/q1_worst_routes_ranked_bar.txt` and `q6_carrier_vs_route_diverging_bar.txt`.

## Page 3: Delay causes (ties to Q2)

- **Source**: `vw_delay_causes` (or `exports/q2_delay_causes_by_month.csv`, which also carries the quarter and year `WITH ROLLUP` subtotal rows).
- **Fields**: `year`, `month_num`, `carrier_delay_min`, `weather_delay_min`, `nas_delay_min`, `security_delay_min`, `late_aircraft_delay_min`, `total_delay_min`.
- **Chart type**: stacked bar chart, one bar per month, five cause segments. Matches `exports/charts/q2_delay_causes_stacked_bar.png`. A toggle or second visual rolled up to quarter/year uses the superaggregate rows already in the CSV (rows where `month_num` is NULL).
- **Filters**: year, quarter.
- **Interpretation line**: name the largest cause of delay minutes across the year and its share of the total, from `exports/charts/q2_delay_causes_stacked_bar.txt`.

## Page 4: Weather impact (ties to Q3 and part of Q4)

- **Source**: `vw_weather_impact` (or `exports/q3_weather_impact.csv`) for Q3; `exports/q4a_airport_departure_band_matrix.csv` and `exports/q4b_ontime_rollup_year_to_weekday.csv` for Q4.
- **Fields**: `precip_band`, `snow_band`, `wind_band`, `temp_band`, `avg_arr_delay_min`, `cancellation_rate`, `flight_count`.
- **Chart types**:
  - Grouped bar chart (Q3): average arrival delay by precipitation band, grouped by wind band. Matches `exports/charts/q3_weather_impact_grouped_bar.png`.
  - Heat map (Q4a): on-time rate by airport (20 busiest) x departure band. Matches `exports/charts/q4_airport_time_heatmap.png`.
- **Filters**: snow band, drill into the Q4b rollup (year to quarter to month to weekday) for a specific airport or period.
- **Interpretation line**: name the worst weather-band combination for arrival delay (Q3) and the worst airport/time-band cell in the heat map (Q4). See the real captions in the matching `.txt` files.

## Page 5: Time patterns (ties to Q4 rollup and Q5)

- **Source**: `vw_time_patterns` (or `exports/q5_late_aircraft_share_by_hour.csv` and `exports/q4b_ontime_rollup_year_to_weekday.csv`).
- **Fields**: `airport`, `departure_band`, `hour_of_day`, `day_of_week_name`, `on_time_rate`, `late_aircraft_share`.
- **Chart types**:
  - Line chart (Q5): late-aircraft delay share by hour of day, one line per busiest-10 airport. Matches `exports/charts/q5_late_aircraft_share_line.png`.
  - Drill-down table or bar (Q4b): on-time rate from year down to weekday, using the `WITH ROLLUP` subtotal rows already in `exports/q4b_ontime_rollup_year_to_weekday.csv`.
- **Filters**: airport, day of week.
- **Interpretation line**: name the hour and airport where late-aircraft delay peaks (Q5), from `exports/charts/q5_late_aircraft_share_line.txt`.

## Sensitivity check (not a dashboard page, but referenced on Page 1)

`exports/sensitivity_check.csv` (from `etl/export_olap.py`'s
`run_sensitivity_check()`) shows total flights, cancellation rate,
on-time rate and average arrival delay under four conditions: all
flights, excluding `is_outlier_delay` flights, excluding diverted
flights, and excluding both. This answers the brief's profiling problem
9 promise ("report results with and without them") and should be footnoted
on Page 1 so a reviewer can see how much the headline KPIs move.

## Reproducing all of the above

```
python -m etl.export_olap
```

Regenerates every CSV in `exports/`, every PNG and caption `.txt` in
`exports/charts/`, and reruns the sensitivity check and the 3-number
spot-check, printing the real recomputed values so a mismatch cannot be
missed.
