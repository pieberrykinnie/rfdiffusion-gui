"""C-24 RunRepository -- the SQLite index.

It exists to answer the run-list query (FR-27) without stat-ing every directory, and to
cache terminal states so a finished run never triggers another sacct (BR-3). It is an
index and a cache; it is authoritative for nothing (BR-1).
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from rfd_core import DesignMode, RunRecord, StageState

from ..status import RunStatus
from .schema import connect, initialise

#: Columns update_state() will accept. An explicit allowlist because these names are
#: interpolated into SQL -- there is no bound-parameter form for a column name, so the
#: safety has to come from never accepting one that did not originate here.
_UPDATABLE = frozenset(
    {
        "name",
        "run_dir",
        "updated_at",
        "contigs",
        "mode",
        "num_designs",
        "partition",
        "slurm_job_id",
        "job_id_history",
        "slurm_state",
        "exit_code",
        "backbone_state",
        "validate_state",
        "status",
        "terminal",
        "missing",
        "cancel_requested_at",
    }
)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@dataclass(frozen=True)
class RunSummary:
    """The list-row projection: cheap for a hundred runs, no directory read, no Slurm call."""

    run_id: str
    name: str
    created_at: Optional[datetime]
    status: RunStatus
    mode: Optional[DesignMode]
    partition: str
    num_designs: int
    contigs: str
    slurm_job_id: Optional[str]
    terminal: bool
    missing: bool = False
    run_dir: Optional[str] = None
    backbone_state: Optional[StageState] = None
    validate_state: Optional[StageState] = None
    slurm_state: Optional[str] = None
    exit_code: Optional[int] = None
    cancel_requested_at: Optional[datetime] = None
    job_id_history: tuple = ()

    @classmethod
    def from_record(cls, record: RunRecord, status: RunStatus) -> "RunSummary":
        return cls(
            run_id=record.run_id,
            name=record.name,
            created_at=record.created_at,
            status=status,
            mode=record.mode,
            partition=record.request.partition,
            num_designs=record.request.num_designs,
            contigs=record.request.contigs,
            slurm_job_id=record.slurm_job_id,
            terminal=status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.TIMEOUT},
            run_dir=record.run_dir,
            backbone_state=record.backbone_state,
            validate_state=record.validate_state,
        )


def _row_to_summary(row: sqlite3.Row) -> RunSummary:
    try:
        history = tuple(json.loads(row["job_id_history"] or "[]"))
    except (ValueError, TypeError):
        history = ()
    return RunSummary(
        run_id=row["run_id"],
        name=row["name"],
        created_at=_parse_dt(row["created_at"]),
        status=RunStatus(row["status"]),
        mode=DesignMode(row["mode"]) if row["mode"] else None,
        partition=row["partition"],
        num_designs=row["num_designs"],
        contigs=row["contigs"],
        slurm_job_id=row["slurm_job_id"],
        terminal=bool(row["terminal"]),
        missing=bool(row["missing"]),
        run_dir=row["run_dir"],
        backbone_state=StageState(row["backbone_state"]) if row["backbone_state"] else None,
        validate_state=StageState(row["validate_state"]) if row["validate_state"] else None,
        slurm_state=row["slurm_state"],
        exit_code=row["exit_code"],
        cancel_requested_at=_parse_dt(row["cancel_requested_at"]),
        job_id_history=history,
    )


class RunRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        conn = connect(self.db_path)
        try:
            initialise(conn)
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        return connect(self.db_path)

    # -- writes ------------------------------------------------------------------

    def create(self, record: RunRecord, status: RunStatus = RunStatus.QUEUED) -> None:
        self.upsert_from_record(record, status)

    def upsert_from_record(self, record: RunRecord, status: RunStatus) -> None:
        """Insert or refresh the index row for `record` (BR-18, BR-21).

        A single statement so a concurrent reader never sees a half-updated row.
        job_id_history and cancel_requested_at are index-only, so the upsert
        deliberately does NOT touch them -- a reconciliation pass from disk must not
        erase what only the index knows.
        """
        now = datetime.now().isoformat()
        terminal = status in {
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.TIMEOUT,
        }
        params = {
            "run_id": record.run_id,
            "name": record.name,
            "run_dir": str(record.run_dir),
            "created_at": _iso(record.created_at) or now,
            "updated_at": now,
            "contigs": record.request.contigs,
            "mode": record.mode.value if record.mode else None,
            "num_designs": record.request.num_designs,
            "partition": record.request.partition,
            "slurm_job_id": record.slurm_job_id,
            "backbone_state": record.backbone_state.value,
            "validate_state": record.validate_state.value,
            "status": status.value,
            "terminal": 1 if terminal else 0,
        }
        sql = """
            INSERT INTO runs (
                run_id, name, run_dir, created_at, updated_at, contigs, mode,
                num_designs, partition, slurm_job_id, backbone_state, validate_state,
                status, terminal, missing
            ) VALUES (
                :run_id, :name, :run_dir, :created_at, :updated_at, :contigs, :mode,
                :num_designs, :partition, :slurm_job_id, :backbone_state,
                :validate_state, :status, :terminal, 0
            )
            ON CONFLICT(run_id) DO UPDATE SET
                name = excluded.name,
                run_dir = excluded.run_dir,
                updated_at = excluded.updated_at,
                contigs = excluded.contigs,
                mode = excluded.mode,
                num_designs = excluded.num_designs,
                partition = excluded.partition,
                slurm_job_id = excluded.slurm_job_id,
                backbone_state = excluded.backbone_state,
                validate_state = excluded.validate_state,
                status = excluded.status,
                terminal = excluded.terminal,
                missing = 0
        """
        conn = self._connect()
        try:
            conn.execute(sql, params)
            conn.commit()
        finally:
            conn.close()

    def update_state(self, run_id: str, **fields: Any) -> None:
        unknown = set(fields) - _UPDATABLE
        if unknown:
            raise ValueError("not updatable columns: {0}".format(sorted(unknown)))
        if not fields:
            return
        payload: Dict[str, Any] = {}
        for key, value in fields.items():
            if isinstance(value, datetime):
                payload[key] = value.isoformat()
            elif isinstance(value, bool):
                payload[key] = 1 if value else 0
            elif hasattr(value, "value") and not isinstance(value, (int, str)):
                payload[key] = value.value
            else:
                payload[key] = value
        payload.setdefault("updated_at", datetime.now().isoformat())
        assignments = ", ".join("{0} = :{0}".format(k) for k in payload)
        payload["run_id"] = run_id
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE runs SET {0} WHERE run_id = :run_id".format(assignments), payload
            )
            conn.commit()
        finally:
            conn.close()

    def mark_terminal(
        self,
        run_id: str,
        status: RunStatus,
        slurm_state: Optional[str] = None,
        exit_code: Optional[int] = None,
    ) -> None:
        """Write back a terminal reconciliation once, so later reads skip Slurm (BR-3)."""
        self.update_state(
            run_id,
            status=status.value,
            slurm_state=slurm_state,
            exit_code=exit_code,
            terminal=1,
        )

    def mark_missing(self, run_id: str, missing: bool = True) -> None:
        """Flag a run whose directory has gone away -- never delete the row (BR-19)."""
        self.update_state(run_id, missing=1 if missing else 0)

    def mark_cancel_requested(self, run_id: str, when: Optional[datetime] = None) -> None:
        """Record that a human pressed Cancel in this app, BEFORE scancel is called
        (Q6=A, BR-8) -- a crash between the two then still leaves the evidence."""
        self.update_state(run_id, cancel_requested_at=when or datetime.now())

    def append_job_id(self, run_id: str, job_id: str) -> None:
        """Keep the previous job ids of a resubmitted run. Index-only: RunRecord has a
        single slurm_job_id field and this unit does not reopen an approved rfd-core
        model for a convenience (business-logic-model.md section 8)."""
        current = self.get(run_id)
        history = list(current.job_id_history) if current else []
        if job_id not in history:
            history.append(job_id)
        self.update_state(run_id, job_id_history=json.dumps(history))

    # -- reads -------------------------------------------------------------------

    def get(self, run_id: str) -> Optional[RunSummary]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        finally:
            conn.close()
        return _row_to_summary(row) if row is not None else None

    def list(self, limit: int = 100) -> List[RunSummary]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        finally:
            conn.close()
        return [_row_to_summary(r) for r in rows]

    def live_job_ids(self, limit: int = 500) -> List[str]:
        """Job ids of every non-terminal indexed run, for one batched squeue (BR-23)."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT slurm_job_id FROM runs "
                "WHERE terminal = 0 AND slurm_job_id IS NOT NULL LIMIT ?",
                (limit,),
            ).fetchall()
        finally:
            conn.close()
        return [r[0] for r in rows]

    def all_run_ids(self) -> List[str]:
        conn = self._connect()
        try:
            rows = conn.execute("SELECT run_id FROM runs").fetchall()
        finally:
            conn.close()
        return [r[0] for r in rows]
