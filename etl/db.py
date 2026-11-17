"""Shared MySQL connection helper for the ETL pipeline.

Every script that touches the database goes through get_engine() so the
connection string is defined in exactly one place.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

REQUIRED_VARS = (
    "MYSQL_HOST",
    "MYSQL_PORT",
    "MYSQL_DATABASE",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
)


def get_engine() -> Engine:
    missing = [v for v in REQUIRED_VARS if not os.environ.get(v)]
    if missing:
        raise RuntimeError(
            f"Missing required .env variables: {', '.join(missing)}. "
            "Copy .env.example to .env and fill in real values."
        )
    host = os.environ["MYSQL_HOST"]
    port = os.environ["MYSQL_PORT"]
    database = os.environ["MYSQL_DATABASE"]
    user = os.environ["MYSQL_USER"]
    password = os.environ["MYSQL_PASSWORD"]
    url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
    return create_engine(url, pool_pre_ping=True)
