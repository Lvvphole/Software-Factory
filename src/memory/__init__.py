"""Memory layer: persist factory runs to SQLite.

v1.1 schema migration: adds target_repo, executor, tests_passed, diff_size_bytes
columns. Migration is idempotent.
"""
from __future__ import annotations
import json
import os
import sqlite3
from pathlib import Path
from typing import Any
from utils import get_logger

log = get_logger("memory")

DEFAULT_DB = os.environ.get("FACTORY_DB_PATH", ".factory-memory/factory.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    signal_id TEXT,
    plan_id TEXT,
    started_at TEXT,
    completed_at TEXT,
    verifier_decision TEXT,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_signal ON runs(signal_id);
"""

V1_1_COLUMNS = [
    ("target_repo", "TEXT"),
    ("executor", "TEXT"),
    ("tests_passed", "INTEGER"),
    ("diff_size_bytes", "INTEGER"),
]


def _migrate(conn: sqlite3.Connection) -> list[str]:
    """Add v1.1 columns if missing. Returns the list of columns added."""
    added: list[str] = []
    existing = {r[1] for r in conn.execute("PRAGMA table_info(runs)").fetchall()}
    for name, kind in V1_1_COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {name} {kind}")
            added.append(name)
    if added:
        log.info("memory migration: added columns %s", added)
    return added


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    p = Path(db_path or DEFAULT_DB)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()
    return conn


def persist_run(run_record: dict[str, Any], db_path: str | Path | None = None) -> str:
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT OR REPLACE INTO runs
               (run_id, signal_id, plan_id, started_at, completed_at,
                verifier_decision, payload_json,
                target_repo, executor, tests_passed, diff_size_bytes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                run_record["run_id"],
                run_record.get("signal_id"),
                run_record.get("plan_id"),
                run_record.get("started_at"),
                run_record.get("completed_at"),
                run_record.get("verifier_decision"),
                json.dumps(run_record),
                run_record.get("target_repo"),
                run_record.get("executor"),
                1 if (run_record.get("test_report") or {}).get("overall") == "pass" else 0,
                (run_record.get("coding_report") or {}).get("diff_size_bytes", 0),
            ),
        )
        conn.commit()
        log.info("run persisted: %s db=%s", run_record["run_id"], db_path or DEFAULT_DB)
        return run_record["run_id"]
    finally:
        conn.close()


def fetch_run(run_id: str, db_path: str | Path | None = None) -> dict[str, Any] | None:
    conn = _connect(db_path)
    try:
        cur = conn.execute("SELECT payload_json FROM runs WHERE run_id=?", (run_id,))
        row = cur.fetchone()
        return json.loads(row[0]) if row else None
    finally:
        conn.close()


def count_runs(db_path: str | Path | None = None) -> int:
    conn = _connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    finally:
        conn.close()
