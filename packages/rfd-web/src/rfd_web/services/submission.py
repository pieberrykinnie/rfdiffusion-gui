"""S-1 SubmissionService -- validated form to queued Slurm job and persisted record.

Q1=A: built in U3 minus the browser upload. It takes an ALREADY-RESOLVED template path;
U4 adds C-27 TemplateUploadHandler in front of it. Without this, U3's definition of done
("a run can be submitted, tracked to completion, and cancelled programmatically") is
unreachable and the unit stays unverifiable until U4 lands.
"""
from __future__ import annotations

import re
import secrets
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from rfd_core import DesignRequest, PathLayout, RunRecord, StageState, validate

from ..config import WebConfig
from ..errors import SlurmSubmitError, SlurmUnavailable
from ..persistence.reader import RunDirectoryReader
from ..persistence.repository import RunRepository
from ..slurm.adapter import SlurmAdapter
from ..slurm.script import JobScriptGenerator, JobStage
from ..status import RunStatus

#: Anything outside this set becomes '-' in a run id. rfd_core.validate has already
#: rejected names containing path separators; this makes the rest filesystem-safe.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
_COLLAPSE = re.compile(r"-{2,}")

MAX_RUN_ID_LENGTH = 64
MAX_COLLISION_ATTEMPTS = 8


@dataclass(frozen=True)
class SubmissionOutcome:
    ok: bool
    run_id: Optional[str] = None
    slurm_job_id: Optional[str] = None
    run_dir: Optional[Path] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def sanitise_run_id(name: str) -> str:
    """Make a user-supplied run name safe as a directory name (Q4=A, step 1 of 3)."""
    cleaned = _UNSAFE.sub("-", name or "")
    cleaned = _COLLAPSE.sub("-", cleaned).strip("-.")
    cleaned = cleaned[:MAX_RUN_ID_LENGTH].strip("-.")
    return cleaned or "run"


class SubmissionService:
    def __init__(
        self,
        layout: PathLayout,
        config: WebConfig,
        adapter: SlurmAdapter,
        repository: RunRepository,
        generator: Optional[JobScriptGenerator] = None,
        reader: Optional[RunDirectoryReader] = None,
    ) -> None:
        self.layout = layout
        self.config = config
        self.adapter = adapter
        self.repository = repository
        self.generator = generator or JobScriptGenerator(layout, config)
        self.reader = reader or RunDirectoryReader(config.log_tail_lines)

    # -- submission --------------------------------------------------------------

    def submit(
        self,
        request: DesignRequest,
        template_path: Optional[Path] = None,
        stage: JobStage = JobStage.ALL,
    ) -> SubmissionOutcome:
        # 1. Validate FIRST. On rejection nothing is created: no directory, no record,
        #    no job, no GPU consumed (FR-5, G-9, BR-11).
        outcome = validate(request)
        if not outcome.ok:
            return SubmissionOutcome(
                ok=False, errors=list(outcome.errors), warnings=list(outcome.warnings)
            )

        # 2/3. Derive a collision-free run id by CREATING the directory (BR-16).
        run_id, run_dir = self._create_run_dir(request.name)

        # 4. Persist the resolved template alongside the run, so the directory stays
        #    self-describing (FR-33).
        if template_path is not None:
            shutil.copyfile(str(template_path), str(run_dir / "input_template.pdb"))

        # 5. Initial record, both stages PENDING (FR-28).
        record = RunRecord(
            run_id=run_id,
            name=request.name,
            run_dir=str(run_dir),
            created_at=datetime.now(timezone.utc),
            request=request,
            backbone_state=StageState.PENDING,
            validate_state=StageState.PENDING,
        )
        record.save(run_dir)

        # 6. Job script into the run directory (G-2).
        script_path = self.generator.write(record, stage=stage, run_dir=run_dir)

        # 7. Submit. The directory and run.json already exist, so a job that starts
        #    instantly still finds its own record.
        try:
            job_id = self.adapter.submit(script_path, run_dir)
        except (SlurmSubmitError, SlurmUnavailable) as exc:
            stderr = getattr(exc, "stderr", "") or str(exc)
            record.backbone_state = StageState.FAILED
            record.error = "submission failed: {0}".format(stderr.strip() or exc)
            record.finished_at = datetime.now(timezone.utc)
            record.save(run_dir)
            # BR-15: the directory and its script are deliberately retained -- the user
            # sees WHY, and the run is hand-resubmittable once the cause is fixed.
            self.repository.upsert_from_record(record, RunStatus.FAILED)
            return SubmissionOutcome(
                ok=False,
                run_id=run_id,
                run_dir=run_dir,
                errors=[record.error],
                warnings=list(outcome.warnings),
            )

        # 8. Record the job id, then index. The index is last because it is the only
        #    step reconciliation can rebuild (BR-18).
        record.slurm_job_id = job_id
        record.save(run_dir)
        self.repository.upsert_from_record(record, RunStatus.QUEUED)
        self.repository.append_job_id(run_id, job_id)

        return SubmissionOutcome(
            ok=True,
            run_id=run_id,
            slurm_job_id=job_id,
            run_dir=run_dir,
            warnings=list(outcome.warnings),
        )

    def _create_run_dir(self, name: str):
        """mkdir(exist_ok=False) IS the collision test (BR-16).

        Checking exists() and then creating is a race; two submissions a millisecond
        apart must never share a directory, which would interleave two jobs' run.json
        writes. This is the notebook's own "append a suffix if taken" behaviour, made
        correct.
        """
        base = sanitise_run_id(name)
        candidate = base
        for _ in range(MAX_COLLISION_ATTEMPTS):
            run_dir = self.layout.run_dir(candidate)
            try:
                run_dir.mkdir(parents=True, exist_ok=False)
            except FileExistsError:
                suffix = secrets.token_hex(2)
                candidate = "{0}_{1}".format(base[: MAX_RUN_ID_LENGTH - 5], suffix)
                continue
            return candidate, run_dir
        raise RuntimeError(
            "could not find a free run directory for {0!r} after {1} attempts".format(
                name, MAX_COLLISION_ATTEMPTS
            )
        )

    # -- resubmission (FR-11, Q8=A) ----------------------------------------------

    def resubmit(
        self, run_id: str, stage: JobStage = JobStage.VALIDATE
    ) -> SubmissionOutcome:
        """Resubmit an existing run directory for one stage.

        FR-11 built --stage into the runner precisely so a failed validation can be
        retried without repeating backbone generation. This is that caller.
        """
        stage = JobStage(stage)
        run_dir = self.layout.run_dir(run_id)
        record = self.reader.read_record(run_dir)
        if record is None:
            return SubmissionOutcome(ok=False, errors=["no readable run.json for {0}".format(run_id)])

        # Preconditions checked BEFORE anything is written (BR-17): a second job writing
        # into a directory a live job still owns corrupts both.
        if stage == JobStage.VALIDATE and record.backbone_state != StageState.COMPLETED:
            return SubmissionOutcome(
                ok=False,
                run_id=run_id,
                errors=[
                    "cannot resubmit validation: backbone state is {0}, not completed".format(
                        record.backbone_state.value
                    )
                ],
            )
        summary = self.repository.get(run_id)
        if summary is not None and not summary.terminal and record.slurm_job_id:
            return SubmissionOutcome(
                ok=False,
                run_id=run_id,
                errors=[
                    "cannot resubmit: job {0} is not in a terminal state".format(
                        record.slurm_job_id
                    )
                ],
            )

        if stage == JobStage.VALIDATE:
            record.validate_state = StageState.PENDING
        else:
            record.backbone_state = StageState.PENDING
        record.error = None
        record.finished_at = None
        record.save(run_dir)

        # Written ALONGSIDE job.sh, never over it (D-6, G-2).
        script_path = self.generator.write(record, stage=stage, run_dir=run_dir)
        try:
            job_id = self.adapter.submit(script_path, run_dir)
        except (SlurmSubmitError, SlurmUnavailable) as exc:
            stderr = getattr(exc, "stderr", "") or str(exc)
            record.error = "resubmission failed: {0}".format(stderr.strip() or exc)
            record.save(run_dir)
            self.repository.upsert_from_record(record, RunStatus.FAILED)
            return SubmissionOutcome(ok=False, run_id=run_id, run_dir=run_dir, errors=[record.error])

        record.slurm_job_id = job_id
        record.save(run_dir)
        self.repository.upsert_from_record(record, RunStatus.QUEUED)
        self.repository.append_job_id(run_id, job_id)
        return SubmissionOutcome(
            ok=True, run_id=run_id, slurm_job_id=job_id, run_dir=run_dir
        )

    # -- cancellation (FR-14) ----------------------------------------------------

    def cancel(self, run_id: str) -> SubmissionOutcome:
        """Cancel a queued or running job.

        No terminal state is written locally: Slurm owns the job's ending, and the next
        get() reconciles it. Writing it optimistically would mean a failed scancel
        produces a run the UI shows as cancelled while it keeps consuming a GPU.
        """
        run_dir = self.layout.run_dir(run_id)
        record = self.reader.read_record(run_dir)
        job_id = record.slurm_job_id if record is not None else None
        if job_id is None:
            summary = self.repository.get(run_id)
            job_id = summary.slurm_job_id if summary is not None else None
        if job_id is None:
            return SubmissionOutcome(
                ok=False, run_id=run_id, errors=["run {0} has no Slurm job to cancel".format(run_id)]
            )

        # Written BEFORE scancel (Q6=A, BR-8) so a crash between the two still leaves
        # the evidence that a human asked for this -- which is the whole point of the
        # field, since scancel and a walltime kill are the same signal to the runner.
        self.repository.mark_cancel_requested(run_id)
        try:
            self.adapter.cancel(job_id)
        except SlurmUnavailable as exc:
            return SubmissionOutcome(ok=False, run_id=run_id, errors=["scancel failed: {0}".format(exc)])
        return SubmissionOutcome(ok=True, run_id=run_id, slurm_job_id=job_id, run_dir=run_dir)
