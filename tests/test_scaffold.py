"""Sanity checks for the Phase 0 scaffold. Transformation-logic tests are
added in Phase 4 once etl/clean.py exists.
"""
import os

from etl.db import REQUIRED_VARS, get_engine


def test_get_engine_reports_missing_vars_clearly(monkeypatch):
    for var in REQUIRED_VARS:
        monkeypatch.delenv(var, raising=False)
    try:
        get_engine()
    except RuntimeError as exc:
        assert "Missing required .env variables" in str(exc)
    else:
        raise AssertionError("expected RuntimeError when .env variables are missing")


def test_get_engine_builds_when_vars_present(monkeypatch):
    monkeypatch.setenv("MYSQL_HOST", "127.0.0.1")
    monkeypatch.setenv("MYSQL_PORT", "3306")
    monkeypatch.setenv("MYSQL_DATABASE", "flight_dw")
    monkeypatch.setenv("MYSQL_USER", "flight_dw_user")
    monkeypatch.setenv("MYSQL_PASSWORD", "test_password")
    engine = get_engine()
    assert engine.url.database == "flight_dw"


def test_env_example_has_no_real_secrets():
    content = (
        __import__("pathlib")
        .Path(__file__)
        .resolve()
        .parent.parent.joinpath(".env.example")
        .read_text()
    )
    assert "change_me" in content
    assert os.linesep.join(["DATA_YEAR="]) in content or "DATA_YEAR=\n" in content
