"""RunStatus -- the reconciled, user-facing outcome of a run.

Placement note: domain-entities.md section 4 puts RunStatus in services/query.py.
It lives in its own module because persistence/repository.py stores it (the index
caches the last reconciled status) and services/query.py produces it -- importing
the service from the repository would invert the layering and create a cycle.
services.query re-exports it, so the documented import path still works.

Deliberately a SEPARATE vocabulary from SlurmState: Slurm's COMPLETED becomes
RunStatus.FAILED whenever run.json was never finalised (business-rules.md BR-2).
One enum would make that distinction inexpressible.
"""
from __future__ import annotations

from enum import Enum


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


#: Statuses that will never change again, and so may be cached in the index (BR-3).
#: UNKNOWN is absent on purpose -- a run Slurm cannot currently describe may still
#: be running.
TERMINAL_RUN_STATUSES = frozenset(
    {
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.TIMEOUT,
    }
)
