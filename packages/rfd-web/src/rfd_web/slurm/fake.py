"""FakeSlurmAdapter -- the other half of NFR-18.

Shipped in src/, not tests/, on purpose: U4 can run the whole application offline
against it, and U3's definition of done ("the full suite passes against a fake Slurm
with no cluster access") is this class plus the C-21 Protocol.

It counts status() calls, which is how BR-3 ("a terminal state is written back once and
never re-queried") is asserted rather than assumed.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..errors import SlurmSubmitError, SlurmUnavailable
from .partitions import PartitionInfo
from .states import JobStatus, SlurmState

DEFAULT_PARTITIONS = [
    PartitionInfo(name="gpu", has_gpu=True, max_walltime="7-00:00:00", is_default=True),
    PartitionInfo(name="agpu", has_gpu=True, max_walltime="3-00:00:00"),
    PartitionInfo(name="lgpu", has_gpu=True, max_walltime="7-00:00:00"),
    PartitionInfo(name="skylake", has_gpu=False, max_walltime="7-00:00:00"),
]


class FakeSlurmAdapter:
    """A scripted Slurm.

    - submit() hands out increasing job ids and records (script, cwd).
    - status() walks a programmed sequence per job, holding on the last entry.
    - cancel() moves a job to CANCELLED.
    - unavailable=True makes every call raise SlurmUnavailable, so BR-4's
      "controller unreachable" branch is reachable in tests.
    """

    def __init__(
        self,
        partitions_fixture: Optional[List[PartitionInfo]] = None,
        first_job_id: int = 1000,
    ) -> None:
        self.submissions: List[Tuple[Path, Path]] = []
        self.cancelled: List[str] = []
        self.status_calls: List[str] = []
        self.unavailable = False
        self.submit_error: Optional[str] = None
        self._next_id = first_job_id
        self._sequences: Dict[str, List[JobStatus]] = {}
        self._partitions = (
            DEFAULT_PARTITIONS if partitions_fixture is None else list(partitions_fixture)
        )

    # -- scripting ---------------------------------------------------------------

    def set_sequence(self, job_id: str, statuses: List[JobStatus]) -> None:
        """Program the statuses status() will return, in order. The final entry
        repeats forever, which is what a terminal state does in reality."""
        self._sequences[str(job_id)] = list(statuses)

    def set_state(self, job_id: str, state: SlurmState, **kwargs) -> None:
        self.set_sequence(str(job_id), [JobStatus(state=state, **kwargs)])

    @property
    def status_call_count(self) -> int:
        return len(self.status_calls)

    # -- SlurmAdapter ------------------------------------------------------------

    def submit(self, script: Path, cwd: Path) -> str:
        if self.unavailable:
            raise SlurmUnavailable("fake: slurm unavailable")
        if self.submit_error is not None:
            raise SlurmSubmitError("fake: sbatch rejected the job", stderr=self.submit_error)
        job_id = str(self._next_id)
        self._next_id += 1
        self.submissions.append((Path(script), Path(cwd)))
        self._sequences.setdefault(job_id, [JobStatus(state=SlurmState.PENDING)])
        return job_id

    def status(self, job_id: str) -> JobStatus:
        if self.unavailable:
            raise SlurmUnavailable("fake: slurm unavailable")
        key = str(job_id)
        self.status_calls.append(key)
        seq = self._sequences.get(key)
        if not seq:
            return JobStatus(state=SlurmState.UNKNOWN, known=False)
        if len(seq) == 1:
            return seq[0]
        return seq.pop(0)

    def cancel(self, job_id: str) -> None:
        if self.unavailable:
            raise SlurmUnavailable("fake: slurm unavailable")
        key = str(job_id)
        self.cancelled.append(key)
        self.set_state(key, SlurmState.CANCELLED)

    def partitions(self) -> List[PartitionInfo]:
        if self.unavailable:
            raise SlurmUnavailable("fake: slurm unavailable")
        return list(self._partitions)
