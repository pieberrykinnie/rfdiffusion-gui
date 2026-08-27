"""Q5=A / BR-18, BR-19, BR-20: the index is rebuildable, and startup rebuilds it."""
from __future__ import annotations

import shutil

from rfd_core import StageState

from rfd_web.persistence.reconcile import RunIndexReconciler, status_from_record
from rfd_web.persistence.repository import RunRepository
from rfd_web.status import RunStatus

from conftest import make_record


def _seed(layout, run_id, **overrides):
    run_dir = layout.run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    record = make_record(run_dir, run_id=run_id, **overrides)
    record.save(run_dir)
    return record


def test_a_deleted_database_costs_nothing(layout, repository):
    """FR-29 and FR-33: the run directories ARE the source of truth, and something
    actually reads them back."""
    _seed(layout, "a")
    _seed(layout, "b", backbone_state=StageState.COMPLETED, validate_state=StageState.COMPLETED)

    layout.database_path.unlink(missing_ok=True)
    fresh = RunRepository(layout.database_path)
    assert fresh.list() == []

    report = RunIndexReconciler(layout, fresh).reconcile_all()
    assert report.indexed == 2
    assert {s.run_id for s in fresh.list()} == {"a", "b"}
    assert fresh.get("b").status is RunStatus.COMPLETED


def test_a_directory_copied_in_from_elsewhere_appears(layout, repository, tmp_path):
    external = tmp_path / "elsewhere" / "imported"
    external.mkdir(parents=True)
    record = make_record(layout.run_dir("imported"), run_id="imported")
    record.save(external)
    shutil.copytree(str(external), str(layout.run_dir("imported")))

    RunIndexReconciler(layout, repository).reconcile_all()
    assert repository.get("imported") is not None


def test_a_corrupt_run_json_is_skipped_without_aborting_the_scan(layout, repository):
    _seed(layout, "good")
    bad = layout.run_dir("bad")
    bad.mkdir(parents=True)
    (bad / "run.json").write_text("{ truncated")

    report = RunIndexReconciler(layout, repository).reconcile_all()
    assert report.indexed == 1
    assert report.skipped and "bad" in report.skipped[0]
    assert repository.get("good") is not None
    assert repository.get("bad") is None


def test_an_empty_run_json_is_skipped(layout, repository):
    empty = layout.run_dir("empty")
    empty.mkdir(parents=True)
    (empty / "run.json").write_text("")
    report = RunIndexReconciler(layout, repository).reconcile_all()
    assert report.indexed == 0 and report.skipped


def test_a_vanished_directory_is_flagged_never_deleted(layout, repository):
    _seed(layout, "gone")
    RunIndexReconciler(layout, repository).reconcile_all()
    shutil.rmtree(str(layout.run_dir("gone")))

    report = RunIndexReconciler(layout, repository).reconcile_all()
    assert report.flagged_missing == 1
    summary = repository.get("gone")
    assert summary is not None, "deleting the row destroys the only trace of the run"
    assert summary.missing is True


def test_a_returning_directory_clears_the_missing_flag(layout, repository):
    _seed(layout, "back")
    RunIndexReconciler(layout, repository).reconcile_all()
    repository.mark_missing("back", True)
    RunIndexReconciler(layout, repository).reconcile_all()
    assert repository.get("back").missing is False


def test_a_missing_output_root_is_not_a_startup_failure(layout, repository):
    shutil.rmtree(str(layout.output_root))
    report = RunIndexReconciler(layout, repository).reconcile_all()
    assert report.indexed == 0


def test_non_run_directories_are_ignored(layout, repository):
    (layout.output_root / "scratch").mkdir()
    (layout.output_root / "notes.txt").write_text("hello")
    report = RunIndexReconciler(layout, repository).reconcile_all()
    assert report.indexed == 0


def test_reconciliation_is_repeatable(layout, repository):
    _seed(layout, "a")
    reconciler = RunIndexReconciler(layout, repository)
    reconciler.reconcile_all()
    reconciler.reconcile_all()
    assert len(repository.list()) == 1


# -- status_from_record -------------------------------------------------------


def test_status_from_record_never_calls_a_non_finalised_record_completed(layout):
    """BR-2 still governs here, where no Slurm knowledge is available at all."""
    record = make_record(layout.run_dir("x"), backbone_state=StageState.COMPLETED)
    assert record.validate_state is StageState.PENDING
    assert status_from_record(record) is not RunStatus.COMPLETED


def test_status_from_record_maps_the_stage_states(layout):
    run_dir = layout.run_dir("x")
    cases = [
        (dict(backbone_state=StageState.FAILED), RunStatus.FAILED),
        (dict(backbone_state=StageState.CANCELLED), RunStatus.CANCELLED),
        (dict(backbone_state=StageState.RUNNING), RunStatus.RUNNING),
        (dict(), RunStatus.QUEUED),
        (
            dict(
                backbone_state=StageState.COMPLETED,
                validate_state=StageState.SKIPPED,
            ),
            RunStatus.COMPLETED,
        ),
    ]
    for overrides, expected in cases:
        assert status_from_record(make_record(run_dir, **overrides)) is expected


def test_a_completed_record_carrying_an_error_is_a_failure(layout):
    record = make_record(
        layout.run_dir("x"),
        backbone_state=StageState.COMPLETED,
        validate_state=StageState.COMPLETED,
        error="validation produced no designs",
    )
    assert status_from_record(record) is RunStatus.FAILED
