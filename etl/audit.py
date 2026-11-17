"""Per-stage row-count logging to audit_log and logs/ (Phase 4), plus
the six formal validation checks from brief section 6 (Phase 5):
row reconciliation, orphan keys, uniqueness, cause totals, dimension
counts, and the re-run test.

Usage:
    python -m etl.audit    # run all six checks, print and save evidence
"""
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.engine import Engine

from etl.db import get_engine

ROOT_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT_DIR / "logs"
SQL_DIR = ROOT_DIR / "sql"
EVIDENCE_DIR = ROOT_DIR / "docs" / "evidence"


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


def run_validation_checks(engine: Engine) -> list:
    """Runs every SELECT in sql/06_validation_checks.sql in order and
    returns their real results as a list of (check_name, columns, rows).
    Each statement's own output is the evidence; nothing here is
    computed independently of what MySQL actually returns.
    """
    sql_text = (SQL_DIR / "06_validation_checks.sql").read_text()
    kept_lines = [line.split("--", 1)[0] for line in sql_text.splitlines()]
    statements = [s.strip() for s in "\n".join(kept_lines).split(";") if s.strip()]

    results = []
    with engine.connect() as conn:
        for stmt in statements:
            result = conn.exec_driver_sql(stmt)
            if not result.returns_rows:
                continue
            columns = list(result.keys())
            rows = result.fetchall()
            check_name = rows[0][0] if rows else "unknown_check"
            results.append((check_name, columns, rows))
    return results


def _format_results(results: list) -> str:
    lines = [f"Validation run at {datetime.now(timezone.utc).isoformat(timespec='seconds')}", ""]
    for check_name, columns, rows in results:
        lines.append(f"== {check_name} ==")
        lines.append("  ".join(columns))
        for row in rows:
            lines.append("  ".join(str(v) for v in row))
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    engine = get_engine()
    results = run_validation_checks(engine)
    text = _format_results(results)
    print(text)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = LOG_DIR / f"validation_{ts}.txt"
    evidence_path = EVIDENCE_DIR / f"validation_{ts}.txt"
    log_path.write_text(text)
    evidence_path.write_text(text)
    print(f"Saved to {log_path} and {evidence_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
