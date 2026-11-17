"""Pipeline orchestrator for the flight-dw warehouse.

Each numbered step below is filled in during its own phase of
docs/BUILD_PLAN.md. Running this file with no flags lists the current
status of every step. Running with --check-db only verifies the MySQL
connection, which is the Phase 0 acceptance check.

Usage:
    python run_all.py              # show step status
    python run_all.py --check-db   # verify the MySQL connection and exit
"""
import argparse
import sys

from etl.db import get_engine

# (step name, callable or None if not yet implemented)
STEPS = [
    ("01_create_schemas", None),
    ("02_create_staging", None),
    ("03_create_warehouse", None),
    ("04_load_dimensions", None),
    ("05_load_facts", None),
    ("06_validation_checks", None),
]


def check_db() -> None:
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.exec_driver_sql("SELECT 1").scalar()
        print(f"MySQL connection OK, SELECT 1 returned: {result}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the flight-dw ETL pipeline.")
    parser.add_argument(
        "--check-db",
        action="store_true",
        help="only verify the MySQL connection, do not run any step",
    )
    args = parser.parse_args()

    if args.check_db:
        check_db()
        return 0

    print("flight-dw pipeline steps (status reflects which phase has been built):")
    for name, fn in STEPS:
        status = "pending" if fn is None else "ready"
        print(f"  [{status}] {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
