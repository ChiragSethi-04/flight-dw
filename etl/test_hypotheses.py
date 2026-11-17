"""Phase 7: tests the brief's four hypotheses (section 9) against the
real OLAP output from Phase 6, printing and saving the exact numbers
docs/report/08_findings_and_limitations.md cites. H1, H3 and H4 reuse
exports/ files already produced by etl.export_olap; H2 needs one new
query (delay by departure band, fleet-wide, not just the busiest
airports Q5 used), saved to exports/h2_delay_by_departure_band.csv.

Usage:
    python -m etl.test_hypotheses
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from etl.db import get_engine

ROOT_DIR = Path(__file__).resolve().parent.parent
EXPORTS_DIR = ROOT_DIR / "exports"
LOG_DIR = ROOT_DIR / "logs"
EVIDENCE_DIR = ROOT_DIR / "docs" / "evidence"

CAUSES = ["carrier_delay_min", "weather_delay_min", "nas_delay_min", "security_delay_min", "late_aircraft_delay_min"]

H2_SQL = """
    SELECT
        t.departure_band,
        COUNT(*) AS flight_count,
        AVG(CASE WHEN fs.cancelled_flag = FALSE THEN f.arr_delay_min END) AS avg_arr_delay_min,
        SUM(f.late_aircraft_delay_min) / SUM(f.carrier_delay_min + f.weather_delay_min + f.nas_delay_min + f.security_delay_min + f.late_aircraft_delay_min) AS late_aircraft_share,
        SUM(CASE WHEN f.on_time_flag = TRUE THEN 1 ELSE 0 END) / SUM(CASE WHEN fs.cancelled_flag = FALSE THEN 1 ELSE 0 END) AS on_time_rate
    FROM fact_flight f
    JOIN dim_time_of_day t ON t.time_key = f.dep_time_key AND t.time_key <> -1
    JOIN dim_flight_status fs ON fs.flight_status_key = f.flight_status_key
    GROUP BY t.departure_band
    ORDER BY FIELD(t.departure_band, 'early morning','morning','afternoon','evening','night')
"""


def hypothesis_1(lines: list) -> None:
    df = pd.read_csv(EXPORTS_DIR / "q2_delay_causes_by_month.csv")
    grand = df[df["year"].isna()].iloc[0]
    total = grand[CAUSES].sum()
    lines.append("## Hypothesis 1: late-aircraft delay is the largest cause")
    for c in CAUSES:
        lines.append(f"  {c}: {grand[c]:,.0f} ({grand[c] / total:.1%})")
    lines.append(f"  total delay-cause minutes: {total:,.0f}")
    lines.append("")


def hypothesis_2(lines: list) -> None:
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(H2_SQL, conn)
    df.to_csv(EXPORTS_DIR / "h2_delay_by_departure_band.csv", index=False)
    lines.append("## Hypothesis 2: delay builds through the day (fleet-wide, exports/h2_delay_by_departure_band.csv)")
    lines.append(df.to_string(index=False))
    lines.append("")


def hypothesis_3(lines: list) -> None:
    df = pd.read_csv(EXPORTS_DIR / "q3_weather_impact.csv")
    df["cancel_n"] = df["cancellation_rate"] * df["flight_count"]
    df["delay_sum"] = df["avg_arr_delay_min"].fillna(0) * df["flight_count"]
    lines.append("## Hypothesis 3: snow/heavy rain raise cancellations more than delay minutes")
    for band_col in ["precip_band", "snow_band"]:
        g = df.groupby(band_col).agg(
            flight_count=("flight_count", "sum"), cancel_n=("cancel_n", "sum"), delay_sum=("delay_sum", "sum")
        ).reset_index()
        g["cancellation_rate"] = g["cancel_n"] / g["flight_count"]
        g["avg_arr_delay_min"] = g["delay_sum"] / g["flight_count"]
        g.to_csv(EXPORTS_DIR / f"h3_weighted_by_{band_col}.csv", index=False)
        lines.append(f"  weighted by {band_col} (exports/h3_weighted_by_{band_col}.csv):")
        lines.append("  " + g[[band_col, "flight_count", "cancellation_rate", "avg_arr_delay_min"]].to_string(index=False).replace("\n", "\n  "))
    lines.append("")


def hypothesis_4(lines: list) -> None:
    df = pd.read_csv(EXPORTS_DIR / "q6_carrier_vs_route_avg_delay.csv")
    route = df.groupby(["origin_iata", "dest_iata"])
    within = route["carrier_avg_delay"].std().fillna(0)
    route_avg = route["route_avg_delay"].first()
    lines.append("## Hypothesis 4: some routes are late regardless of carrier")
    lines.append(f"  multi-carrier routes: {len(route_avg)}")
    lines.append(f"  mean within-route std of carrier avg delay: {within.mean():.2f} min")
    lines.append(f"  between-route std of route_avg_delay: {route_avg.std():.2f} min")
    lines.append(f"  routes with within-route spread < 10 min: {(within < 10).sum()} / {len(within)} ({(within < 10).mean():.1%})")
    lines.append("  widest 5 within-route carrier spreads:")
    lines.append("  " + within.sort_values(ascending=False).head(5).to_string().replace("\n", "\n  "))
    lines.append("")


def main() -> int:
    lines = [f"Hypothesis testing run at {datetime.now(timezone.utc).isoformat(timespec='seconds')}", ""]
    hypothesis_1(lines)
    hypothesis_2(lines)
    hypothesis_3(lines)
    hypothesis_4(lines)
    text = "\n".join(lines)
    print(text)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (LOG_DIR / "hypothesis_testing.txt").write_text(text)
    (EVIDENCE_DIR / "hypothesis_testing.txt").write_text(text)
    print(f"Saved to {LOG_DIR / 'hypothesis_testing.txt'} and {EVIDENCE_DIR / 'hypothesis_testing.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
