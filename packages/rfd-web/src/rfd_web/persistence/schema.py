"""SQLite schema for the run index.

The database is an INDEX, never the source of truth (D-3, AD-6, BR-18). Every column is
derivable from a run directory, except job_id_history and cancel_requested_at, which are
index-only by design and whose loss is documented in domain-entities.md section 5.1.

RFD_DB defaults to /home because SQLite locking misbehaves on Lustre (env.example).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

DDL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id              TEXT PRIMARY KEY,
    name                TEXT    NOT NULL,
    run_dir             TEXT    NOT NULL,
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL,

    contigs             TEXT    NOT NULL,
    mode                TEXT,
    num_designs         INTEGER NOT NULL DEFAULT 1,
    partition           TEXT    NOT NULL,

    slurm_job_id        TEXT,
    job_id_history      TEXT    NOT NULL DEFAULT '[]',
    slurm_state         TEXT,
    exit_code           INTEGER,

    backbone_state      TEXT    NOT NULL,
    validate_state      TEXT    NOT NULL,
    status              TEXT    NOT NULL,

    terminal            INTEGER NOT NULL DEFAULT 0,
    missing             INTEGER NOT NULL DEFAULT 0,
    cancel_requested_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_live       ON runs (terminal, slurm_job_id);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    """Open the index, creating its parent directory if needed.

    WAL plus an explicit busy timeout is what keeps an HTMX status poll from failing
    with "database is locked" while a submission commits (BR-21). The app is
    single-user (AD-7) but not single-threaded.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialise(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    conn.execute("PRAGMA user_version = {0}".format(SCHEMA_VERSION))
    conn.commit()


def read_schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row is not None else 0
