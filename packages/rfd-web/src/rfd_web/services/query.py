"""S-2 RunQueryService -- the reconciler.

The only place in the system that answers "which source wins". Scattering that across
routes is how status displays start lying, which is why services.md isolates it and
deferred the rules to U3 Functional Design; business-logic-model.md sections 9.1-9.3 and
business-rules.md BR-1..BR-6 are what this module implements.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from rfd_core import DesignMode, ProgressState, RunOutputs, RunRecord, StageState

from ..config import WebConfig
from ..errors import SlurmUnavailable
from ..persistence.reader import RunDirectoryReader
from ..persistence.repository import RunRepository, RunSummary
from ..slurm.adapter import SlurmAdapter
from ..slurm.states import JobStatus, SlurmState
from ..status import TERMINAL_RUN_STATUSES, RunStatus

__all__ = [
    "ProgressView",
    "RunQueryService",
    "RunStatus",
    "RunView",
]

#: The stage states that mean "this stage will not change again".
_FINAL_STAGE_STATES = frozenset(
    {
        StageState.COMPLETED,
        StageState.FAILED,
        StageState.CANCELLED,
        StageState.SKIPPED,
    }
)

#: The sentence rfd-runner's SIGTERM handler writes. It is a guess -- scancel and a
#: walltime kill are the same signal to the runner -- and Slurm can tell the two apart.
#: When Slurm says CANCELLED the guess is simply wrong, so it is suppressed (BR-8).
_RUNNER_SIGTERM_MARKER = "terminated (SIGTERM)"


@dataclass(frozen=True)
class ProgressView:
    stage: str
    design_index: int
    total_designs: int
    step: int
    total_steps: int
    stale: bool = False
    note: Optional[str] = None


@dataclass(frozen=True)
class RunView:
    run_id: str
    name: str
    created_at: Optional[datetime]
    status: RunStatus
    slurm_job_id: Optional[str] = None
    slurm_state: Optional[SlurmState] = None
    exit_code: Optional[int] = None
    mode: Optional[DesignMode] = None
    backbone_state: Optional[StageState] = None
    validate_state: Optional[StageState] = None
    progress: Optional[ProgressView] = None
    frame_available: bool = False
    message: Optional[str] = None
    log_tail: Optional[str] = None
    outputs: Optional[RunOutputs] = None
    stale: bool = False
    cancel_requested_at: Optional[datetime] = None
    run_dir: Optional[str] = None


def record_is_finalised(record: RunRecord) -> bool:
    """Both stages have reached a state that will not change again.

    "Finalised" is what BR-2 turns on: Slurm COMPLETED plus a non-finalised record means
    the runner died before writing its terminal state, and that is reported as FAILURE,
    never as success.
    """
    return (
        record.backbone_state in _FINAL_STAGE_STATES
        and record.validate_state in _FINAL_STAGE_STATES
    )


class RunQueryService:
    def __init__(
        self,
        layout,
        config: WebConfig,
        adapter: SlurmAdapter,
        repository: RunRepository,
        reader: Optional[RunDirectoryReader] = None,
        clock=None,
    ) -> None:
        self.layout = layout
        self.config = config
        self.adapter = adapter
        self.repository = repository
        self.reader = reader or RunDirectoryReader(config.log_tail_lines)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    # -- the algorithm (business-logic-model.md section 9.1) ----------------------

    def get(self, run_id: str) -> Optional[RunView]:
        summary = self.repository.get(run_id)
        run_dir = Path(summary.run_dir) if summary and summary.run_dir else self.layout.run_dir(run_id)
        record = self.reader.read_record(run_dir)

        if summary is None and record is None:
            return None

        # Step 2: a finished run never triggers another Slurm call, ever (BR-3, D-4).
        if summary is not None and summary.terminal:
            return self._terminal_view_from_index(summary, run_dir, record)

        if record is None:
            # Indexed but the directory is unreadable right now: report what the index
            # knows rather than inventing a state.
            return self._view_from_summary(summary, run_dir, stale=True,
                                           message="run directory is not readable")

        # Step 3: never queued -- report from the record alone. A FAILED record here is
        # a submission failure, and its error is the sbatch stderr (BR-15).
        if not record.slurm_job_id:
            status = RunStatus.FAILED if record.backbone_state == StageState.FAILED else RunStatus.QUEUED
            return self._build_view(
                record,
                run_dir,
                status=status,
                slurm=None,
                summary=summary,
                message=record.error,
            )

        # Step 4: ask Slurm.
        try:
            slurm = self.adapter.status(record.slurm_job_id)
        except SlurmUnavailable as exc:
            # BR-4: a controller hiccup must never downgrade a running job to failed.
            last = summary.status if summary is not None else RunStatus.UNKNOWN
            return self._build_view(
                record,
                run_dir,
                status=last,
                slurm=None,
                summary=summary,
                message="Slurm is not reachable right now ({0}); showing the last known state".format(exc),
                stale=True,
            )

        # Steps 5-7.
        status, message = self._reconcile(record, slurm, summary)
        view = self._build_view(
            record, run_dir, status=status, slurm=slurm, summary=summary, message=message
        )

        # Step 8: write a terminal reconciliation back once.
        if status in TERMINAL_RUN_STATUSES:
            self.repository.upsert_from_record(record, status)
            self.repository.mark_terminal(
                record.run_id, status, slurm_state=slurm.state.value, exit_code=slurm.exit_code
            )
        elif summary is not None:
            self.repository.update_state(
                record.run_id, status=status.value, slurm_state=slurm.state.value
            )
        return view

    def list_runs(self, limit: int = 100) -> List[RunSummary]:
        """Run list (FR-27). Deliberately index-only: no directory read and no Slurm
        call per row (BR-23). Callers refresh individual runs through get()."""
        return self.repository.list(limit=limit)

    # -- the reconciliation table (business-logic-model.md section 9.2) -----------

    def _reconcile(self, record: RunRecord, slurm: JobStatus, summary: Optional[RunSummary]):
        finalised = record_is_finalised(record)

        if slurm.state == SlurmState.PENDING:
            return RunStatus.QUEUED, (slurm.reason or "queued, waiting for an allocation")

        if slurm.state == SlurmState.RUNNING:
            return RunStatus.RUNNING, None

        if slurm.state == SlurmState.COMPLETED:
            if not finalised:
                # The central rule (BR-2). A job killed after its last checkpoint but
                # before writing its terminal record exits 0 and looks, to Slurm alone,
                # exactly like a success.
                return (
                    RunStatus.FAILED,
                    "the job ended without writing a terminal run record -- "
                    "treating it as a failure rather than reporting a false success",
                )
            if record.error:
                # The runner caught its own failure and exited 0 for Slurm's purposes;
                # the record is authoritative about the science (BR-1).
                return RunStatus.FAILED, record.error
            return RunStatus.COMPLETED, None

        if slurm.state == SlurmState.FAILED:
            return RunStatus.FAILED, record.error or slurm.reason

        if slurm.state == SlurmState.CANCELLED:
            return RunStatus.CANCELLED, self._cancel_message(summary)

        if slurm.state == SlurmState.TIMEOUT:
            # BR-9: here the runner's message is CORRECT and is the more informative of
            # the two -- it names the stage and step the run had reached.
            detail = record.error or "the job exceeded its requested walltime"
            return RunStatus.TIMEOUT, detail

        # UNKNOWN
        if not slurm.known:
            if finalised:
                return self._status_from_record(record), record.error
            return (
                RunStatus.UNKNOWN,
                "the scheduler no longer has a record of job {0}, and the run never "
                "wrote a final state".format(record.slurm_job_id),
            )
        return RunStatus.UNKNOWN, slurm.reason

    def _cancel_message(self, summary: Optional[RunSummary]) -> str:
        """BR-8. The runner's "likely walltime exceeded" sentence is never shown here:
        Slurm has established that it is wrong."""
        if summary is not None and summary.cancel_requested_at is not None:
            return "cancelled from this app at {0}".format(
                summary.cancel_requested_at.strftime("%Y-%m-%d %H:%M")
            )
        return "cancelled by the scheduler or an administrator"

    @staticmethod
    def _status_from_record(record: RunRecord) -> RunStatus:
        if StageState.FAILED in (record.backbone_state, record.validate_state):
            return RunStatus.FAILED
        if StageState.CANCELLED in (record.backbone_state, record.validate_state):
            return RunStatus.CANCELLED
        if record.error:
            return RunStatus.FAILED
        return RunStatus.COMPLETED

    # -- progress overlay (business-logic-model.md section 9.3, BR-5) -------------

    def _progress_view(self, record: RunRecord, run_dir: Path) -> Optional[ProgressView]:
        progress: Optional[ProgressState] = self.reader.read_progress(run_dir)
        if progress is None:
            return ProgressView(
                stage="backbone",
                design_index=0,
                total_designs=record.request.num_designs,
                step=0,
                total_steps=record.request.iterations,
                note="starting",
            )

        updated = progress.updated_at
        now = self._clock()
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        age = (now - updated).total_seconds()
        stale = age > self.config.progress_stale_seconds

        note = None
        if stale and record.backbone_state == StageState.COMPLETED:
            # The M1 finding, resolved here rather than left for U4 to rediscover:
            # ProgressReporter is wired into _run_backbone only, so progress.json
            # NECESSARILY freezes when backbone ends and stays frozen for the whole
            # validation stage. That is healthy work, not a stall.
            note = "validating (no step-level progress available)"
        elif stale:
            note = "running -- no progress update for {0} minutes".format(int(age // 60))

        return ProgressView(
            stage=progress.stage,
            design_index=progress.design_index,
            total_designs=progress.total_designs,
            step=progress.step,
            total_steps=progress.total_steps,
            stale=stale,
            note=note,
        )

    # -- view construction --------------------------------------------------------

    def _build_view(
        self,
        record: RunRecord,
        run_dir: Path,
        status: RunStatus,
        slurm: Optional[JobStatus],
        summary: Optional[RunSummary],
        message: Optional[str] = None,
        stale: bool = False,
    ) -> RunView:
        progress = self._progress_view(record, run_dir) if status == RunStatus.RUNNING else None
        tail = None
        if status in (RunStatus.FAILED, RunStatus.TIMEOUT, RunStatus.UNKNOWN):
            tail = self.reader.log_tail(run_dir) or None
        return RunView(
            run_id=record.run_id,
            name=record.name,
            created_at=record.created_at,
            status=status,
            slurm_job_id=record.slurm_job_id,
            # `known=False` means nobody has actually asked Slurm (or Slurm had no row),
            # so reporting a state word would be claiming knowledge this view does not
            # have. Observed on real Grex data: runs recovered from disk were displaying
            # slurm=UNKNOWN when no query had been made at all.
            slurm_state=slurm.state if (slurm is not None and slurm.known) else None,
            exit_code=slurm.exit_code if slurm is not None else None,
            mode=record.mode,
            backbone_state=record.backbone_state,
            validate_state=record.validate_state,
            progress=progress,
            # BR-6: the FILE decides, not ProgressState.frame_path, which the M1 run
            # proved is never populated.
            frame_available=self.reader.current_frame(run_dir) is not None,
            message=self._clean_message(message, status),
            log_tail=tail,
            outputs=record.outputs,
            stale=stale,
            cancel_requested_at=summary.cancel_requested_at if summary else None,
            run_dir=str(run_dir),
        )

    @staticmethod
    def _clean_message(message: Optional[str], status: RunStatus) -> Optional[str]:
        if message and status == RunStatus.CANCELLED and _RUNNER_SIGTERM_MARKER in message:
            return None
        return message

    def _terminal_view_from_index(
        self, summary: RunSummary, run_dir: Path, record: Optional[RunRecord]
    ) -> RunView:
        if record is not None:
            cached = JobStatus(
                state=SlurmState(summary.slurm_state)
                if summary.slurm_state
                else SlurmState.UNKNOWN,
                exit_code=summary.exit_code,
                # A run indexed straight from run.json (startup reconciliation) has never
                # been asked about; say so rather than presenting a fabricated state.
                known=bool(summary.slurm_state),
            )
            return self._build_view(
                record,
                run_dir,
                status=summary.status,
                slurm=cached,
                summary=summary,
                message=self._terminal_message(summary, record),
            )
        return self._view_from_summary(summary, run_dir)

    def _terminal_message(self, summary: RunSummary, record: RunRecord) -> Optional[str]:
        if summary.status == RunStatus.CANCELLED:
            return self._cancel_message(summary)
        return record.error

    def _view_from_summary(
        self,
        summary: RunSummary,
        run_dir: Path,
        stale: bool = False,
        message: Optional[str] = None,
    ) -> RunView:
        return RunView(
            run_id=summary.run_id,
            name=summary.name,
            created_at=summary.created_at,
            status=summary.status,
            slurm_job_id=summary.slurm_job_id,
            slurm_state=SlurmState(summary.slurm_state) if summary.slurm_state else None,
            exit_code=summary.exit_code,
            mode=summary.mode,
            backbone_state=summary.backbone_state,
            validate_state=summary.validate_state,
            frame_available=self.reader.current_frame(run_dir) is not None,
            message=message,
            stale=stale,
            cancel_requested_at=summary.cancel_requested_at,
            run_dir=summary.run_dir,
        )
