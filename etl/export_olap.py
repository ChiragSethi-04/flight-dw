"""Phase 6: run the six business questions and five reporting views from
sql/07_olap_queries.sql, export them to exports/, draw the six required
chart types to exports/charts/, run the outlier/diverted sensitivity
check, and spot-check three numbers against independent SQL.

Usage:
    python -m etl.export_olap
"""
import random
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from sqlalchemy.engine import Engine

from etl.db import get_engine

ROOT_DIR = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT_DIR / "sql"
EXPORTS_DIR = ROOT_DIR / "exports"
CHARTS_DIR = EXPORTS_DIR / "charts"

# Positional names for the 8 SELECT statements in sql/07_olap_queries.sql,
# in the order they appear (the 5 CREATE OR REPLACE VIEW statements that
# follow are run for effect, not captured here).
QUERY_NAMES = [
    "q1a_worst_routes",
    "q1b_worst_routes_by_carrier",
    "q2_delay_causes_by_month",
    "q3_weather_impact",
    "q4a_airport_departure_band_matrix",
    "q4b_ontime_rollup_year_to_weekday",
    "q5_late_aircraft_share_by_hour",
    "q6_carrier_vs_route_avg_delay",
]

VIEW_NAMES = [
    "vw_kpi_overview",
    "vw_routes_carriers",
    "vw_delay_causes",
    "vw_weather_impact",
    "vw_time_patterns",
]


def _load_statements() -> list:
    sql_text = (SQL_DIR / "07_olap_queries.sql").read_text()
    kept_lines = [line.split("--", 1)[0] for line in sql_text.splitlines()]
    return [s.strip() for s in "\n".join(kept_lines).split(";") if s.strip()]


def run_olap_queries(engine: Engine) -> dict:
    """Runs every statement in sql/07_olap_queries.sql in order: the 8
    SELECTs are captured as DataFrames (keyed by QUERY_NAMES), the 5
    CREATE OR REPLACE VIEW statements are executed for their side effect
    (idempotent, per hard rule 4) and not captured here.
    """
    statements = _load_statements()
    results = {}
    select_idx = 0
    with engine.begin() as conn:
        for stmt in statements:
            upper = stmt.strip().upper()
            if upper.startswith("USE "):
                conn.exec_driver_sql(stmt)
                continue
            if upper.startswith("CREATE OR REPLACE VIEW"):
                conn.exec_driver_sql(stmt)
                continue
            df = pd.read_sql(stmt, conn)
            if select_idx >= len(QUERY_NAMES):
                raise RuntimeError(
                    f"sql/07_olap_queries.sql has more SELECT statements ({select_idx + 1}) "
                    f"than QUERY_NAMES ({len(QUERY_NAMES)}); update QUERY_NAMES to match."
                )
            results[QUERY_NAMES[select_idx]] = df
            select_idx += 1
    if select_idx != len(QUERY_NAMES):
        raise RuntimeError(
            f"Expected {len(QUERY_NAMES)} SELECT statements in sql/07_olap_queries.sql, found {select_idx}."
        )
    return results


def export_views(engine: Engine) -> dict:
    results = {}
    with engine.connect() as conn:
        for name in VIEW_NAMES:
            results[name] = pd.read_sql(f"SELECT * FROM {name}", conn)
    return results


def save_csv(df: pd.DataFrame, name: str) -> Path:
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORTS_DIR / f"{name}.csv"
    df.to_csv(path, index=False)
    return path


def overall_kpis(engine: Engine) -> dict:
    """One real, independently-computed overall on-time rate and
    cancellation rate, used in chart captions so interpretation lines
    don't average monthly rates (which would be a Simpson's-paradox-
    prone shortcut) when a single-pass total is just as easy to get.
    """
    sql = """
        SELECT
            COUNT(*) AS total_flights,
            SUM(CASE WHEN fs.cancelled_flag = TRUE THEN 1 ELSE 0 END) / COUNT(*) AS cancellation_rate,
            SUM(CASE WHEN f.on_time_flag = TRUE THEN 1 ELSE 0 END)
                / SUM(CASE WHEN fs.cancelled_flag = FALSE THEN 1 ELSE 0 END) AS on_time_rate
        FROM fact_flight f
        JOIN dim_flight_status fs ON fs.flight_status_key = f.flight_status_key
    """
    with engine.connect() as conn:
        row = pd.read_sql(sql, conn).iloc[0]
    return {
        "total_flights": int(row["total_flights"]),
        "cancellation_rate": float(row["cancellation_rate"]),
        "on_time_rate": float(row["on_time_rate"]),
    }


def _save_caption(chart_name: str, text: str) -> None:
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    (CHARTS_DIR / f"{chart_name}.txt").write_text(text + "\n")
    print(f"  {chart_name}: {text}")


def chart_q1_ranked_bar(q1a: pd.DataFrame, overall: dict) -> None:
    df = q1a.sort_values("worst_rank")
    labels = df["origin_iata"] + "-" + df["dest_iata"]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(labels, df["on_time_rate"] * 100, color="#c0392b")
    ax.invert_yaxis()
    ax.set_xlabel("On-time rate (%)")
    ax.set_title("Q1: 10 worst routes by on-time rate (min 500 flights)")
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "q1_worst_routes_ranked_bar.png", dpi=150)
    plt.close(fig)
    worst = df.iloc[0]
    text = (
        f"The worst route, {worst['origin_iata']}-{worst['dest_iata']}, has an on-time rate of "
        f"{worst['on_time_rate']:.1%} against {worst['flight_count']:,.0f} flights, "
        f"versus the system-wide on-time rate of {overall['on_time_rate']:.1%}."
    )
    _save_caption("q1_worst_routes_ranked_bar", text)


def chart_q2_stacked_bar(q2: pd.DataFrame) -> None:
    causes = ["carrier_delay_min", "weather_delay_min", "nas_delay_min", "security_delay_min", "late_aircraft_delay_min"]
    monthly = q2[q2["month_num"].notna()].sort_values("month_num")
    fig, ax = plt.subplots(figsize=(9, 5))
    bottom = pd.Series([0] * len(monthly), index=monthly.index, dtype=float)
    colors = ["#2c3e50", "#2980b9", "#27ae60", "#f39c12", "#8e44ad"]
    for cause, color in zip(causes, colors):
        ax.bar(monthly["month_num"], monthly[cause], bottom=bottom, label=cause.replace("_delay_min", ""), color=color)
        bottom += monthly[cause]
    ax.set_xlabel("Month")
    ax.set_ylabel("Delay minutes")
    ax.set_title("Q2: delay minutes by cause, by month")
    ax.legend()
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "q2_delay_causes_stacked_bar.png", dpi=150)
    plt.close(fig)
    totals = monthly[causes].sum()
    top_cause = totals.idxmax().replace("_delay_min", "")
    year_total = totals.sum()
    text = (
        f"{top_cause.replace('_', ' ')} delay is the largest cause across the year, "
        f"{totals.max() / year_total:.1%} of all {int(year_total):,} delay-cause minutes."
    )
    _save_caption("q2_delay_causes_stacked_bar", text)


def chart_q3_grouped_bar(q3: pd.DataFrame) -> None:
    weighted = q3.copy()
    weighted["weighted_delay"] = weighted["avg_arr_delay_min"].fillna(0) * weighted["flight_count"]
    grouped = weighted.groupby(["precip_band", "wind_band"]).agg(
        weighted_delay=("weighted_delay", "sum"), flight_count=("flight_count", "sum")
    ).reset_index()
    grouped["avg_arr_delay_min"] = grouped["weighted_delay"] / grouped["flight_count"]
    pivot = grouped.pivot(index="precip_band", columns="wind_band", values="avg_arr_delay_min")
    fig, ax = plt.subplots(figsize=(9, 5))
    pivot.plot(kind="bar", ax=ax)
    ax.set_ylabel("Avg arrival delay (min, non-cancelled)")
    ax.set_xlabel("Precipitation band (origin)")
    ax.set_title("Q3: weather impact on arrival delay")
    ax.legend(title="Wind band")
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "q3_weather_impact_grouped_bar.png", dpi=150)
    plt.close(fig)
    worst_cell = grouped.loc[grouped["avg_arr_delay_min"].idxmax()]
    best_cell = grouped.loc[grouped["avg_arr_delay_min"].idxmin()]
    text = (
        f"Precip={worst_cell['precip_band']}/wind={worst_cell['wind_band']} averages "
        f"{worst_cell['avg_arr_delay_min']:.1f} min arrival delay, versus "
        f"{best_cell['avg_arr_delay_min']:.1f} min for precip={best_cell['precip_band']}/wind={best_cell['wind_band']}."
    )
    _save_caption("q3_weather_impact_grouped_bar", text)


def chart_q4_heatmap(q4a: pd.DataFrame) -> None:
    band_order = ["early morning", "morning", "afternoon", "evening", "night"]
    pivot = q4a.pivot(index="airport", columns="departure_band", values="on_time_rate")
    present_bands = [b for b in band_order if b in pivot.columns]
    pivot = pivot[present_bands] if present_bands else pivot
    pivot = pivot.sort_index()
    fig, ax = plt.subplots(figsize=(7, 9))
    im = ax.imshow(pivot.values * 100, cmap="RdYlGn", aspect="auto", vmin=50, vmax=100)
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, rotation=45, ha="right")
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index)
    ax.set_title("Q4: on-time rate (%) by airport x departure band (20 busiest)")
    fig.colorbar(im, ax=ax, label="On-time rate (%)")
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "q4_airport_time_heatmap.png", dpi=150)
    plt.close(fig)
    stacked = pivot.stack()
    worst_airport, worst_band = stacked.idxmin()
    text = (
        f"Of the 20 busiest airports, {worst_airport} during the '{worst_band}' departure band has the lowest "
        f"on-time rate in the matrix, {stacked.min():.1%}."
    )
    _save_caption("q4_airport_time_heatmap", text)


def chart_q5_line(q5: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))
    for airport, grp in q5.groupby("airport"):
        grp = grp.sort_values("hour_of_day")
        ax.plot(grp["hour_of_day"], grp["late_aircraft_share"] * 100, marker="o", markersize=3, label=airport)
    ax.set_xlabel("Hour of day (scheduled departure)")
    ax.set_ylabel("Late-aircraft share of delay minutes (%)")
    ax.set_title("Q5: late-aircraft delay share by hour, 10 busiest airports")
    ax.legend(ncol=2, fontsize=8)
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "q5_late_aircraft_share_line.png", dpi=150)
    plt.close(fig)
    # A handful of overnight hours have only one or two delayed flights total,
    # so their "share" can hit 100% on a single flight; exclude any hour/airport
    # cell below a minimum delay-minute volume before calling it the peak, so
    # the headline number reflects a real pattern, not a one-flight artifact.
    MIN_VOLUME_FOR_PEAK = 500
    candidates = q5[q5["total_cause_delay_min"] >= MIN_VOLUME_FOR_PEAK]
    peak = candidates.loc[candidates["late_aircraft_share"].idxmax()]
    text = (
        f"Late-aircraft delay peaks at hour {int(peak['hour_of_day'])} at {peak['airport']}, "
        f"{peak['late_aircraft_share']:.1%} of that hour's delay-cause minutes, consistent with delay "
        "compounding later in the operating day."
    )
    _save_caption("q5_late_aircraft_share_line", text)


def chart_q6_diverging_bar(q6: pd.DataFrame) -> None:
    df = q6.sort_values("delay_vs_route_avg")
    worst = df.tail(10)
    best = df.head(10)
    combined = pd.concat([best, worst]).sort_values("delay_vs_route_avg")
    labels = combined["origin_iata"] + "-" + combined["dest_iata"] + " (" + combined["carrier_code"] + ")"
    colors = ["#27ae60" if v < 0 else "#c0392b" for v in combined["delay_vs_route_avg"]]
    fig, ax = plt.subplots(figsize=(8, 7))
    ax.barh(labels, combined["delay_vs_route_avg"], color=colors)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Carrier avg arrival delay minus route avg (min)")
    ax.set_title("Q6: carrier delay vs. route average (10 best, 10 worst)")
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "q6_carrier_vs_route_diverging_bar.png", dpi=150)
    plt.close(fig)
    worst_row = df.iloc[-1]
    best_row = df.iloc[0]
    text = (
        f"{worst_row['carrier_code']} on {worst_row['origin_iata']}-{worst_row['dest_iata']} runs "
        f"{worst_row['delay_vs_route_avg']:.1f} min worse than that route's average, while "
        f"{best_row['carrier_code']} on {best_row['origin_iata']}-{best_row['dest_iata']} runs "
        f"{abs(best_row['delay_vs_route_avg']):.1f} min better."
    )
    _save_caption("q6_carrier_vs_route_diverging_bar", text)


def run_sensitivity_check(engine: Engine) -> pd.DataFrame:
    """Brief's profiling problem 9: report on-time rate, cancellation
    rate and average arrival delay with and without outlier-delay flights
    and diverted flights, rather than silently dropping either.
    """
    conditions = {
        "all_flights": "1=1",
        "excl_outliers": "(f.is_outlier_delay IS NULL OR f.is_outlier_delay = FALSE)",
        "excl_diverted": "fs.diverted_flag = FALSE",
        "excl_outliers_and_diverted": (
            "(f.is_outlier_delay IS NULL OR f.is_outlier_delay = FALSE) AND fs.diverted_flag = FALSE"
        ),
    }
    rows = []
    with engine.connect() as conn:
        for name, where in conditions.items():
            sql = f"""
                SELECT
                    COUNT(*) AS total_flights,
                    SUM(CASE WHEN fs.cancelled_flag = TRUE THEN 1 ELSE 0 END) / COUNT(*) AS cancellation_rate,
                    SUM(CASE WHEN f.on_time_flag = TRUE THEN 1 ELSE 0 END)
                        / SUM(CASE WHEN fs.cancelled_flag = FALSE THEN 1 ELSE 0 END) AS on_time_rate,
                    AVG(CASE WHEN fs.cancelled_flag = FALSE THEN f.arr_delay_min END) AS avg_arr_delay_min
                FROM fact_flight f
                JOIN dim_flight_status fs ON fs.flight_status_key = f.flight_status_key
                WHERE {where}
            """
            row = pd.read_sql(sql, conn).iloc[0]
            rows.append({"condition": name, **row.to_dict()})
    return pd.DataFrame(rows)


def spot_check(engine: Engine, results: dict) -> list:
    """Brief's Phase 6 acceptance rule: pick three numbers at random from
    the OLAP output and recompute them directly from the raw/fact tables
    with independent SQL, then show both sides.
    """
    checks = []

    q1a = results["q1a_worst_routes"]
    pick1 = q1a.sample(1, random_state=random.randint(0, 10_000)).iloc[0]
    sql1 = """
        SELECT
            SUM(CASE WHEN fs.cancelled_flag = FALSE THEN 1 ELSE 0 END) AS non_cancelled_count,
            SUM(CASE WHEN f.on_time_flag = TRUE THEN 1 ELSE 0 END) AS on_time_count
        FROM fact_flight f
        JOIN dim_route r ON r.route_key = f.route_key
        JOIN dim_flight_status fs ON fs.flight_status_key = f.flight_status_key
        WHERE r.origin_iata = %(o)s AND r.dest_iata = %(d)s
    """
    with engine.connect() as conn:
        check1 = pd.read_sql(sql1, conn, params={"o": pick1["origin_iata"], "d": pick1["dest_iata"]}).iloc[0]
    checks.append({
        "source": "q1a_worst_routes",
        "label": f"{pick1['origin_iata']}-{pick1['dest_iata']} on_time_count",
        "reported": int(pick1["on_time_count"]),
        "recomputed": int(check1["on_time_count"]),
        "match": int(pick1["on_time_count"]) == int(check1["on_time_count"]),
    })

    kpi = results["vw_kpi_overview"]
    pick2 = kpi.sample(1, random_state=random.randint(0, 10_000)).iloc[0]
    sql2 = """
        SELECT
            COUNT(*) AS total_flights,
            SUM(CASE WHEN fs.cancelled_flag = TRUE THEN 1 ELSE 0 END) AS cancelled_flights
        FROM fact_flight f
        JOIN dim_date d ON d.date_key = f.date_key
        JOIN dim_flight_status fs ON fs.flight_status_key = f.flight_status_key
        WHERE d.full_date >= %(start)s AND d.full_date < DATE_ADD(%(start)s, INTERVAL 1 MONTH)
    """
    start_date = f"{int(pick2['year'])}-{int(pick2['month_num']):02d}-01"
    with engine.connect() as conn:
        check2 = pd.read_sql(sql2, conn, params={"start": start_date}).iloc[0]
    checks.append({
        "source": "vw_kpi_overview",
        "label": f"{pick2['month_name']} {int(pick2['year'])} total_flights",
        "reported": int(pick2["total_flights"]),
        "recomputed": int(check2["total_flights"]),
        "match": int(pick2["total_flights"]) == int(check2["total_flights"]),
    })

    q6 = results["q6_carrier_vs_route_avg_delay"]
    pick3 = q6.sample(1, random_state=random.randint(0, 10_000)).iloc[0]
    sql3 = """
        SELECT AVG(f.arr_delay_min) AS carrier_avg_delay, COUNT(*) AS n
        FROM fact_flight f
        JOIN dim_route r ON r.route_key = f.route_key
        JOIN dim_carrier c ON c.carrier_key = f.carrier_key
        JOIN dim_flight_status fs ON fs.flight_status_key = f.flight_status_key
        WHERE r.origin_iata = %(o)s AND r.dest_iata = %(d)s AND c.carrier_code = %(cc)s
          AND fs.cancelled_flag = FALSE
    """
    with engine.connect() as conn:
        check3 = pd.read_sql(
            sql3, conn,
            params={"o": pick3["origin_iata"], "d": pick3["dest_iata"], "cc": pick3["carrier_code"]},
        ).iloc[0]
    reported3 = round(float(pick3["carrier_avg_delay"]), 2)
    recomputed3 = round(float(check3["carrier_avg_delay"]), 2)
    checks.append({
        "source": "q6_carrier_vs_route_avg_delay",
        "label": f"{pick3['origin_iata']}-{pick3['dest_iata']} {pick3['carrier_code']} carrier_avg_delay",
        "reported": reported3,
        "recomputed": recomputed3,
        "match": abs(reported3 - recomputed3) < 0.01,
    })

    return checks


def main() -> int:
    engine = get_engine()

    print("Running sql/07_olap_queries.sql (8 queries + 5 views)...")
    results = run_olap_queries(engine)
    for name, df in results.items():
        path = save_csv(df, name)
        print(f"  {name}: {len(df)} rows -> {path}")

    print("Exporting the 5 reporting views...")
    view_results = export_views(engine)
    for name, df in view_results.items():
        path = save_csv(df, name)
        print(f"  {name}: {len(df)} rows -> {path}")
    results.update(view_results)

    print("Computing overall KPIs for chart captions...")
    overall = overall_kpis(engine)
    print(f"  {overall}")

    print("Drawing the 6 required chart types...")
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    chart_q1_ranked_bar(results["q1a_worst_routes"], overall)
    chart_q2_stacked_bar(results["q2_delay_causes_by_month"])
    chart_q3_grouped_bar(results["q3_weather_impact"])
    chart_q4_heatmap(results["q4a_airport_departure_band_matrix"])
    chart_q5_line(results["q5_late_aircraft_share_by_hour"])
    chart_q6_diverging_bar(results["q6_carrier_vs_route_avg_delay"])

    print("Running the outlier / diverted-flight sensitivity check...")
    sensitivity = run_sensitivity_check(engine)
    save_csv(sensitivity, "sensitivity_check")
    print(sensitivity.to_string(index=False))

    print("Spot-checking 3 random numbers against independent SQL...")
    checks = spot_check(engine, results)
    for c in checks:
        status = "MATCH" if c["match"] else "MISMATCH"
        print(f"  [{status}] {c['source']}: {c['label']} reported={c['reported']} recomputed={c['recomputed']}")
    if not all(c["match"] for c in checks):
        print("SPOT-CHECK FAILURE: a reported number did not match its independent recomputation.")
        return 1

    print("Phase 6 OLAP export complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
