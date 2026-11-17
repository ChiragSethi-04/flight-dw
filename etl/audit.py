"""Basic per-stage row-count logging to audit_log and logs/, per hard
rule: "every ETL stage writes row counts in and out to logs/ and to an
audit_log table." This is the Phase 4 version (count in/out per stage);
Phase 5 extends it with the six formal validation checks
(sql/06_validation_checks.sql) on top of what is recorded here.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.engine import Engine

ROOT_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT_DIR / "logs"


def _insert_audit_row(
    engine: Engine,
    load_id: str,
    stage_name: str,
    started_at: datetime,
    finished_at: Optional[datetime],
    rows_in: Optional[int],
    rows_out: Optional[int],
    rows_rejected: Optional[int],
    status: str,
    message: Optional[str],
) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            INSERT INTO audit_log
                (load_id, stage_name, rows_in, rows_out, rows_rejected, started_at, finished_at, status, message)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (load_id, stage_name, rows_in, rows_out, rows_rejected, started_at, finished_at, status, message),
        )


def _log_line(line: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    path = LOG_DIR / f"audit_{date_str}.log"
    with open(path, "a") as f:
        f.write(line + "\n")
    print(line, flush=True)


@contextmanager
def stage(engine: Engine, load_id: str, stage_name: str, rows_in: Optional[int] = None):
    """Usage:

        with stage(engine, load_id, "load_dim_carrier") as s:
            s.rows_out = load_dim_carrier(engine)

    Records started_at/finished_at and writes one audit_log row and one
    logs/ line, whether the stage succeeds or raises.
    """
    started_at = datetime.now(timezone.utc)

    class _StageResult:
        rows_out: Optional[int] = None
        rows_rejected: Optional[int] = None

    result = _StageResult()
    try:
        yield result
    except Exception as exc:
        finished_at = datetime.now(timezone.utc)
        _insert_audit_row(
            engine, load_id, stage_name, started_at, finished_at,
            rows_in, result.rows_out, result.rows_rejected, "failed", str(exc),
        )
        _log_line(
            f"[{finished_at.isoformat(timespec='seconds')}] FAILED  {stage_name}: "
            f"rows_in={rows_in} rows_out={result.rows_out} error={exc}"
        )
        raise
    else:
        finished_at = datetime.now(timezone.utc)
        duration = (finished_at - started_at).total_seconds()
        _insert_audit_row(
            engine, load_id, stage_name, started_at, finished_at,
            rows_in, result.rows_out, result.rows_rejected, "success", None,
        )
        _log_line(
            f"[{finished_at.isoformat(timespec='seconds')}] OK      {stage_name}: "
            f"rows_in={rows_in} rows_out={result.rows_out} ({duration:.1f}s)"
        )
