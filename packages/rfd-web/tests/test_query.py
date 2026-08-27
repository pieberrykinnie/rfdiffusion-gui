"""S-2: one test per row of the reconciliation table (business-logic-model.md 9.2),
plus the progress-overlay rules (9.3) and BR-2 ... BR-6.

This is the table services.md deferred to U3 Functional Design, executed.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from rfd_core import ProgressState, RunOutputs, StageState

from rfd_web.services.query import RunQueryService, record_is_finalised
from rfd_web.services.submission import SubmissionService
from rfd_web.slurm.states import JobStatus, SlurmState
from rfd_web.status import RunStatus

from conftest import make_request

NOW = datetime(2026, 8, 27, 21, 0, tzinfo=timezone.utc)


@pytest.fixture
def submitter(layout, config, adapter, repository):
    return SubmissionService(layout, config, adapter, repository)


@pytest.fixture
def query(layout, config, adapter, repository):
    return RunQueryService(layout, config, adapter, repository, clock=lambda: NOW)


@pytest.fixture
def submitted(submitter, adapter):
    """A submitted run, with its record on disk and a job id in Slurm."""
    outcome = submitter.submit(make_request(name="run"))
    return outcome.run_id, Path(outcome.run_dir), outcome.slurm_job_id


def finish(run_dir, backbone=StageState.COMPLETED, validate=StageState.COMPLETED, **fields):
    from rfd_core import RunRecord

    record = RunRecord.load(run_dir)
    record.backbone_state = backbone
    record.validate_state = validate
    for key, value in fields.items():
        setattr(record, key, value)
    record.save(run_dir)
    return record


# -- row: PENDING -------------------------------------------------------------


def test_pending_is_queued_and_ignores_any_progress_file(query, adapter, submitted):
    run_id, run_dir, job_id = submitted
    adapter.set_state(job_id, SlurmState.PENDING, reason="Resources")
    ProgressState(
        stage="backbone", design_index=0, total_designs=1, step=10, total_steps=50,
        updated_at=NOW,
    ).save(run_dir)

    view = query.get(run_id)
    assert view.status is RunStatus.QUEUED
    assert view.progress is None, "no progress is expected before the job runs"
    assert "Resources" in view.message


# -- row: RUNNING -------------------------------------------------------------


def test_running_reports_step_progress(query, adapter, submitted):
    run_id, run_dir, job_id = submitted
    adapter.set_state(job_id, SlurmState.RUNNING)
    ProgressState(
        stage="backbone", design_index=0, total_designs=2, step=17, total_steps=50,
        updated_at=NOW,
    ).save(run_dir)

    view = query.get(run_id)
    assert view.status is RunStatus.RUNNING
    assert view.progress.step == 17 and view.progress.total_steps == 50
    assert view.progress.stale is False and view.progress.note is None


def test_running_without_a_progress_file_says_starting(query, adapter, submitted):
    run_id, _, job_id = submitted
    adapter.set_state(job_id, SlurmState.RUNNING)
    view = query.get(run_id)
    assert view.progress.note == "starting"


# -- row: COMPLETED + finalised ----------------------------------------------


def test_completed_and_finalised_is_the_only_success(query, adapter, submitted):
    run_id, run_dir, job_id = submitted
    finish(run_dir, outputs=RunOutputs(best_pdb="run/best.pdb"))
    adapter.set_state(job_id, SlurmState.COMPLETED, exit_code=0)

    view = query.get(run_id)
    assert view.status is RunStatus.COMPLETED
    assert view.exit_code == 0
    assert view.outputs.best_pdb == "run/best.pdb"
    assert view.log_tail is None


# -- row: COMPLETED + NOT finalised (BR-2, the central rule) ------------------


def test_completed_but_unfinalised_is_reported_as_failure_never_success(
    query, adapter, submitted
):
    """A job killed after its last checkpoint but before writing its terminal record
    exits 0 and looks, to Slurm alone, exactly like a success."""
    run_id, run_dir, job_id = submitted
    (run_dir / "job-{0}.err".format(job_id)).write_text("Killed\n")
    adapter.set_state(job_id, SlurmState.COMPLETED, exit_code=0)

    view = query.get(run_id)
    assert view.status is RunStatus.FAILED
    assert "without writing a terminal run record" in view.message
    assert "Killed" in view.log_tail


def test_completed_with_a_recorded_error_is_a_failure(query, adapter, submitted):
    run_id, run_dir, job_id = submitted
    finish(run_dir, error="no designs passed validation")
    adapter.set_state(job_id, SlurmState.COMPLETED, exit_code=0)
    view = query.get(run_id)
    assert view.status is RunStatus.FAILED
    assert view.message == "no designs passed validation"


# -- row: FAILED --------------------------------------------------------------


def test_failed_carries_the_exit_code_and_log_tail(query, adapter, submitted):
    run_id, run_dir, job_id = submitted
    finish(run_dir, backbone=StageState.FAILED, validate=StageState.SKIPPED,
           error="ModuleNotFoundError: No module named 'pydantic'")
    (run_dir / "job-{0}.err".format(job_id)).write_text("Traceback...\nModuleNotFoundError\n")
    adapter.set_state(job_id, SlurmState.FAILED, exit_code=1)

    view = query.get(run_id)
    assert view.status is RunStatus.FAILED
    assert view.exit_code == 1
    assert "pydantic" in view.message
    assert "ModuleNotFoundError" in view.log_tail


# -- row: CANCELLED (BR-8, Q6=A) ---------------------------------------------


def test_cancelled_suppresses_the_runners_misleading_walltime_message(
    query, submitter, adapter, repository, submitted
):
    """The runner cannot tell scancel from a walltime kill -- both are SIGTERM -- so it
    guesses "likely walltime exceeded". Slurm CAN tell them apart, and when it says
    CANCELLED the guess is simply wrong."""
    run_id, run_dir, job_id = submitted
    finish(
        run_dir,
        backbone=StageState.FAILED,
        validate=StageState.PENDING,
        error="terminated (SIGTERM) - likely walltime exceeded",
    )
    submitter.cancel(run_id)  # records cancel_requested_at, then scancel
    adapter.set_state(job_id, SlurmState.CANCELLED)

    view = query.get(run_id)
    assert view.status is RunStatus.CANCELLED
    assert "walltime" not in (view.message or "")
    assert "cancelled from this app" in view.message


def test_a_cancel_nobody_here_requested_says_so(query, adapter, submitted):
    run_id, run_dir, job_id = submitted
    adapter.set_state(job_id, SlurmState.CANCELLED)
    view = query.get(run_id)
    assert view.status is RunStatus.CANCELLED
    assert "scheduler or an administrator" in view.message


# -- row: TIMEOUT (BR-9) ------------------------------------------------------


def test_timeout_keeps_the_runners_message_because_here_it_is_correct(
    query, adapter, submitted
):
    run_id, run_dir, job_id = submitted
    finish(
        run_dir,
        backbone=StageState.FAILED,
        validate=StageState.PENDING,
        error="terminated (SIGTERM) - likely walltime exceeded",
    )
    adapter.set_state(job_id, SlurmState.TIMEOUT)

    view = query.get(run_id)
    assert view.status is RunStatus.TIMEOUT
    assert "walltime" in view.message


# -- rows: UNKNOWN ------------------------------------------------------------


def test_forgotten_but_finalised_run_trusts_the_record(query, adapter, submitted):
    run_id, run_dir, job_id = submitted
    finish(run_dir)
    adapter.set_sequence(job_id, [JobStatus(state=SlurmState.UNKNOWN, known=False)])
    view = query.get(run_id)
    assert view.status is RunStatus.COMPLETED


def test_forgotten_and_unfinalised_run_is_unknown_with_an_explanation(
    query, adapter, submitted
):
    run_id, _, job_id = submitted
    adapter.set_sequence(job_id, [JobStatus(state=SlurmState.UNKNOWN, known=False)])
    view = query.get(run_id)
    assert view.status is RunStatus.UNKNOWN
    assert "no longer has a record" in view.message


# -- BR-4: unreachable is not a state change ---------------------------------


def test_an_unreachable_controller_never_downgrades_a_running_job(
    query, adapter, repository, submitted
):
    run_id, _, job_id = submitted
    adapter.set_state(job_id, SlurmState.RUNNING)
    query.get(run_id)
    assert repository.get(run_id).status is RunStatus.RUNNING

    adapter.unavailable = True
    view = query.get(run_id)
    assert view.status is RunStatus.RUNNING, "a five-second hiccup is not a failure"
    assert view.stale is True
    assert "not reachable" in view.message


# -- BR-3: terminal runs never touch Slurm again ------------------------------


def test_a_terminal_run_issues_zero_slurm_calls_on_re_read(query, adapter, submitted):
    run_id, run_dir, job_id = submitted
    finish(run_dir)
    adapter.set_state(job_id, SlurmState.COMPLETED, exit_code=0)

    query.get(run_id)
    calls_after_first = adapter.status_call_count
    assert calls_after_first >= 1

    for _ in range(5):
        view = query.get(run_id)
        assert view.status is RunStatus.COMPLETED
    assert adapter.status_call_count == calls_after_first, (
        "NFR-16: a finished run must never trigger another sacct"
    )


# -- BR-5: the progress overlay, including the frozen-VALIDATE case -----------


def test_stale_progress_during_validation_is_healthy_work_not_a_stall(
    query, adapter, submitted
):
    """The M1 finding, resolved here so U4 inherits a correct answer: ProgressReporter
    is wired into _run_backbone only, so progress.json NECESSARILY freezes when the
    backbone stage ends."""
    run_id, run_dir, job_id = submitted
    finish(run_dir, backbone=StageState.COMPLETED, validate=StageState.RUNNING)
    ProgressState(
        stage="backbone", design_index=0, total_designs=1, step=49, total_steps=50,
        updated_at=NOW - timedelta(minutes=20),
    ).save(run_dir)
    adapter.set_state(job_id, SlurmState.RUNNING)

    view = query.get(run_id)
    assert view.status is RunStatus.RUNNING
    assert view.progress.stale is True
    assert view.progress.note == "validating (no step-level progress available)"


def test_stale_progress_before_the_backbone_finishes_is_a_warning(query, adapter, submitted):
    run_id, run_dir, job_id = submitted
    ProgressState(
        stage="backbone", design_index=0, total_designs=1, step=3, total_steps=50,
        updated_at=NOW - timedelta(minutes=7),
    ).save(run_dir)
    adapter.set_state(job_id, SlurmState.RUNNING)

    view = query.get(run_id)
    assert view.progress.stale is True
    assert "no progress update for 7 minutes" in view.progress.note


def test_a_naive_timestamp_in_progress_json_is_treated_as_utc(query, adapter, submitted):
    run_id, run_dir, job_id = submitted
    ProgressState(
        stage="backbone", design_index=0, total_designs=1, step=1, total_steps=50,
        updated_at=NOW.replace(tzinfo=None),
    ).save(run_dir)
    adapter.set_state(job_id, SlurmState.RUNNING)
    assert query.get(run_id).progress.stale is False


# -- BR-6: the live frame is decided by the file ------------------------------


def test_frame_available_is_true_even_though_progress_frame_path_is_null(
    query, adapter, submitted
):
    """The other M1 finding: set_frame() is never called, so frame_path stays null for
    an entire successful run while current_frame.pdb is published correctly."""
    run_id, run_dir, job_id = submitted
    progress = ProgressState(
        stage="backbone", design_index=0, total_designs=1, step=5, total_steps=50,
        updated_at=NOW,
    )
    progress.save(run_dir)
    assert progress.frame_path is None
    (run_dir / "current_frame.pdb").write_text("ATOM\n")
    adapter.set_state(job_id, SlurmState.RUNNING)

    assert query.get(run_id).frame_available is True


def test_frame_unavailable_when_the_file_is_absent(query, adapter, submitted):
    run_id, _, job_id = submitted
    adapter.set_state(job_id, SlurmState.RUNNING)
    assert query.get(run_id).frame_available is False


# -- submission failures and missing runs -------------------------------------


def test_a_run_that_was_never_queued_reports_the_sbatch_error(
    layout, config, adapter, repository, submitter, query
):
    adapter.submit_error = "sbatch: error: Invalid account"
    outcome = submitter.submit(make_request(name="nojob"))
    view = query.get(outcome.run_id)
    assert view.status is RunStatus.FAILED
    assert "Invalid account" in view.message


def test_an_unknown_run_is_none(query):
    assert query.get("does-not-exist") is None


# -- list (FR-27, BR-23) ------------------------------------------------------


def test_list_runs_makes_no_slurm_calls(query, adapter, submitter):
    for i in range(3):
        submitter.submit(make_request(name="r{0}".format(i)))
    before = adapter.status_call_count
    rows = query.list_runs()
    assert len(rows) == 3
    assert adapter.status_call_count == before


# -- helper -------------------------------------------------------------------


def test_record_is_finalised_requires_both_stages(layout, submitter):
    from rfd_core import RunRecord

    outcome = submitter.submit(make_request(name="fin"))
    run_dir = Path(outcome.run_dir)
    record = RunRecord.load(run_dir)
    assert record_is_finalised(record) is False

    record.backbone_state = StageState.COMPLETED
    assert record_is_finalised(record) is False

    record.validate_state = StageState.SKIPPED
    assert record_is_finalised(record) is True


# -- degraded reads -----------------------------------------------------------


def test_an_indexed_run_whose_directory_became_unreadable_reports_stale(
    query, repository, submitted
):
    """The index still knows the run exists; inventing a state would be worse than
    saying the directory cannot be read."""
    run_id, run_dir, _ = submitted
    (run_dir / "run.json").unlink()
    view = query.get(run_id)
    assert view is not None
    assert view.stale is True
    assert "not readable" in view.message


def test_a_terminal_run_whose_directory_vanished_still_lists(
    query, adapter, repository, submitted
):
    import shutil

    run_id, run_dir, job_id = submitted
    finish(run_dir)
    adapter.set_state(job_id, SlurmState.COMPLETED, exit_code=0)
    query.get(run_id)  # writes the terminal state back

    shutil.rmtree(str(run_dir))
    view = query.get(run_id)
    assert view.status is RunStatus.COMPLETED
    assert view.frame_available is False


def test_a_terminal_cancelled_run_keeps_its_explanation_on_re_read(
    query, submitter, adapter, submitted
):
    run_id, run_dir, job_id = submitted
    finish(
        run_dir,
        backbone=StageState.FAILED,
        validate=StageState.PENDING,
        error="terminated (SIGTERM) - likely walltime exceeded",
    )
    submitter.cancel(run_id)
    adapter.set_state(job_id, SlurmState.CANCELLED)
    first = query.get(run_id)
    second = query.get(run_id)  # served entirely from the index
    assert first.message == second.message
    assert "walltime" not in second.message


def test_a_run_recovered_from_disk_does_not_claim_a_slurm_state(
    layout, config, adapter, repository, written_record
):
    """Observed on real Grex data: runs indexed by startup reconciliation displayed
    slurm=UNKNOWN when no query had been made at all. Absence of knowledge is None."""
    from rfd_web.persistence.reconcile import RunIndexReconciler

    written_record(
        "recovered",
        backbone_state=StageState.COMPLETED,
        validate_state=StageState.COMPLETED,
    )
    RunIndexReconciler(layout, repository).reconcile_all()

    query = RunQueryService(layout, config, adapter, repository)
    view = query.get("recovered")
    assert view.status is RunStatus.COMPLETED
    assert view.slurm_state is None, "nobody asked Slurm; do not present a state word"
    assert adapter.status_call_count == 0
