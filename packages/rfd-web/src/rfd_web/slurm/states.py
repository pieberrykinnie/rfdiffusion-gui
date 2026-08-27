"""Slurm's state vocabulary, mapped onto the seven values Application Design defines.

business-logic-model.md section 3.1 and business-rules.md BR-7: the map is TOTAL, and
its fallback is UNKNOWN -- never COMPLETED (which fabricates success) and never FAILED
(which cries wolf). Slurm gains states across versions; UNKNOWN is the only honest
answer to a word this code has not seen.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


class SlurmState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"


#: UNKNOWN is deliberately NOT terminal.
TERMINAL_STATES = frozenset(
    {
        SlurmState.COMPLETED,
        SlurmState.FAILED,
        SlurmState.CANCELLED,
        SlurmState.TIMEOUT,
    }
)


_STATE_MAP = {
    # queued, or holding an allocation it has not started using
    "PENDING": SlurmState.PENDING,
    "CONFIGURING": SlurmState.PENDING,
    "REQUEUED": SlurmState.PENDING,
    "REQUEUE_HOLD": SlurmState.PENDING,
    "RESV_DEL_HOLD": SlurmState.PENDING,
    "SUSPENDED": SlurmState.PENDING,
    "SIGNALING": SlurmState.RUNNING,
    # executing; COMPLETING and STAGE_OUT still occupy the allocation
    "RUNNING": SlurmState.RUNNING,
    "COMPLETING": SlurmState.RUNNING,
    "STAGE_OUT": SlurmState.RUNNING,
    "RESIZING": SlurmState.RUNNING,
    # ended
    "COMPLETED": SlurmState.COMPLETED,
    "FAILED": SlurmState.FAILED,
    "NODE_FAIL": SlurmState.FAILED,
    "BOOT_FAIL": SlurmState.FAILED,
    "OUT_OF_MEMORY": SlurmState.FAILED,
    "DEADLINE": SlurmState.FAILED,
    "PREEMPTED": SlurmState.FAILED,
    "REVOKED": SlurmState.FAILED,
    "SPECIAL_EXIT": SlurmState.FAILED,
    "CANCELLED": SlurmState.CANCELLED,
    "TIMEOUT": SlurmState.TIMEOUT,
}


def normalise_state_word(raw: str) -> str:
    """Reduce a Slurm state field to the bare state word.

    Handles the two forms seen in practice:
      - sacct's "CANCELLED by 1234"  -> "CANCELLED"  (first whitespace token)
      - a width-truncated "CANCELLED+" -> "CANCELLED" (trailing '+')
    """
    word = raw.strip().split()[0] if raw.strip() else ""
    return word.rstrip("+").upper()


def map_state(raw: str) -> SlurmState:
    """Total map from a Slurm state string to SlurmState (BR-7)."""
    return _STATE_MAP.get(normalise_state_word(raw), SlurmState.UNKNOWN)


@dataclass(frozen=True)
class JobStatus:
    """What the adapter knows about one job.

    Refinement R-1 over component-methods.md's `state(job_id) -> SlurmState`, which
    cannot carry the exit code FR-19 requires.

    `known=False` means both squeue and sacct RAN and returned no row -- Slurm has
    genuinely forgotten this job (accounting retention). A command that fails, times
    out, or is missing raises SlurmUnavailable instead (BR-4).
    """

    state: SlurmState
    exit_code: Optional[int] = None
    signal: Optional[int] = None
    reason: Optional[str] = None
    known: bool = True

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES


def parse_exit_code(raw: str) -> Tuple[Optional[int], Optional[int]]:
    """Decode sacct's ExitCode field, which has the form "X:Y" (BR-10).

    Returns (exit_code, signal). Either may be None when the field is absent or
    malformed -- FR-19 wants the number the user can act on, not a parse error.
    """
    text = raw.strip()
    if not text:
        return None, None
    parts = text.split(":", 1)
    try:
        code = int(parts[0])
    except ValueError:
        return None, None
    sig: Optional[int] = None
    if len(parts) == 2:
        try:
            sig = int(parts[1])
        except ValueError:
            sig = None
    return code, sig
