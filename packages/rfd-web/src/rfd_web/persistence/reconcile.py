"""Startup reconciliation of the SQLite index against the run directories (Q5=A).

This is what actually delivers FR-29 and gives FR-33's self-describing run directories a
reader. A deleted database costs nothing; a run directory copied in from elsewhere
appears after a restart.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from rfd_core import PathLayout, RunRecord, StageState

from ..status import RunStatus
from .reader import RunDirectoryReader
from .repository import RunRepository

log = logging.getLogger(__name__)


@dataclass
class ReconcileReport:
    indexed: int = 0
    flagged_missing: int = 0
    skipped: List[str] = field(default_factory=list)


def status_from_record(record: RunRecord) -> RunStatus:
    """Best-effort status from the record alone, with no Slurm knowledge.

    Used at reconciliation time, where querying Slurm for every historical run would be
    exactly the per-row storm BR-23 forbids. S-2 refines this whenever a run is actually
    read, and BR-2 still governs: a non-finalised record is never called COMPLETED here.
    """
    if record.backbone_state == StageState.FAILED or record.validate_state == StageState.FAILED:
        return RunStatus.FAILED
    if record.backbone_state == StageState.CANCELLED or record.validate_state == StageState.CANCELLED:
        return RunStatus.CANCELLED
    if record.backbone_state == StageState.COMPLETED and record.validate_state in (
        StageState.COMPLETED,
        StageState.SKIPPED,
    ):
        return RunStatus.COMPLETED if not record.error else RunStatus.FAILED
    if StageState.RUNNING in (record.backbone_state, record.validate_state):
        return RunStatus.RUNNING
    return RunStatus.QUEUED


class RunIndexReconciler:
    def __init__(
        self,
        layout: PathLayout,
        repository: RunRepository,
        reader: Optional[RunDirectoryReader] = None,
    ) -> None:
        self.layout = layout
        self.repository = repository
        self.reader = reader or RunDirectoryReader()

    def reconcile_all(self) -> ReconcileReport:
        report = ReconcileReport()
        root = Path(self.layout.output_root)

        seen = set()
        if root.is_dir():
            for entry in sorted(root.iterdir()):
                if not entry.is_dir():
                    continue
                if not (entry / "run.json").exists():
                    continue
                record = self.reader.read_record(entry)
                if record is None:
                    # One corrupt directory must never prevent the app from starting
                    # (BR-20). rfd_core.read_json already returns None for exactly
                    # this case rather than raising.
                    log.warning("skipping unreadable run.json in %s", entry)
                    report.skipped.append(str(entry))
                    continue
                self.repository.upsert_from_record(record, status_from_record(record))
                seen.add(record.run_id)
                report.indexed += 1

        for run_id in self.repository.all_run_ids():
            if run_id in seen:
                continue
            summary = self.repository.get(run_id)
            if summary is None:
                continue
            run_dir = Path(summary.run_dir) if summary.run_dir else root / run_id
            if not run_dir.is_dir():
                # Flagged, never deleted (BR-19): deleting the row destroys the only
                # remaining evidence the run existed.
                if not summary.missing:
                    self.repository.mark_missing(run_id, True)
                report.flagged_missing += 1

        return report
