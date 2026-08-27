"""S-1: validate first, create nothing on rejection, and never race on a run id."""
from __future__ import annotations

from pathlib import Path

import pytest
from rfd_core import RunRecord, StageState

from rfd_web.services.submission import (
    MAX_COLLISION_ATTEMPTS,
    SubmissionService,
    sanitise_run_id,
)
from rfd_web.slurm.script import JobStage
from rfd_web.status import RunStatus

from conftest import make_request


@pytest.fixture
def service(layout, config, adapter, repository):
    return SubmissionService(layout, config, adapter, repository)


# -- validation gate (FR-5, G-9, BR-11) ---------------------------------------


def test_an_invalid_request_creates_absolutely_nothing(service, layout, adapter, repository):
    outcome = service.submit(make_request(contigs="this is not a contig string"))
    assert outcome.ok is False
    assert outcome.errors
    assert list(layout.output_root.iterdir()) == [], "no run directory may be created"
    assert adapter.submissions == [], "no GPU may be queued"
    assert repository.list() == []


def test_validation_errors_are_values_not_exceptions(service):
    outcome = service.submit(make_request(order=99, symmetry="cyclic"))
    assert outcome.ok is False and outcome.run_id is None


# -- the happy path -----------------------------------------------------------


def test_submit_writes_record_script_and_index_in_that_order(service, layout, adapter, repository):
    outcome = service.submit(make_request(name="my-binder"))
    assert outcome.ok is True
    run_dir = Path(outcome.run_dir)

    assert (run_dir / "run.json").is_file()
    assert (run_dir / "job.sh").is_file()

    record = RunRecord.load(run_dir)
    assert record.slurm_job_id == outcome.slurm_job_id
    assert record.backbone_state is StageState.PENDING
    assert record.validate_state is StageState.PENDING

    summary = repository.get(outcome.run_id)
    assert summary.slurm_job_id == outcome.slurm_job_id
    assert summary.status is RunStatus.QUEUED
    assert summary.job_id_history == (outcome.slurm_job_id,)

    script, cwd = adapter.submissions[0]
    assert script == run_dir / "job.sh"
    assert cwd == run_dir


def test_run_json_exists_before_sbatch_is_called(layout, config, repository, adapter):
    """A job that starts instantly must still find its own record."""
    seen = {}
    original = adapter.submit

    def spy(script, cwd):
        seen["run_json_present"] = (Path(cwd) / "run.json").is_file()
        seen["script_present"] = Path(script).is_file()
        return original(script, cwd)

    adapter.submit = spy  # type: ignore[assignment]
    SubmissionService(layout, config, adapter, repository).submit(make_request())
    assert seen == {"run_json_present": True, "script_present": True}


def test_template_is_copied_into_the_run_directory(service, tmp_path):
    template = tmp_path / "6MRR.pdb"
    template.write_text("ATOM      1  N   MET A   1\n")
    outcome = service.submit(make_request(), template_path=template)
    assert (Path(outcome.run_dir) / "input_template.pdb").read_text() == template.read_text()


# -- run id derivation (FR-7, Q4=A, BR-16) ------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("my-binder", "my-binder"),
        ("My Binder 2", "My-Binder-2"),
        ("weird///name", "weird-name"),
        ("...", "run"),
        ("", "run"),
        ("a" * 200, "a" * 64),
    ],
)
def test_sanitisation(raw, expected):
    assert sanitise_run_id(raw) == expected


def test_a_taken_name_gets_a_random_suffix_not_a_collision(service, layout):
    first = service.submit(make_request(name="dup"))
    second = service.submit(make_request(name="dup"))
    assert first.run_id == "dup"
    assert second.run_id != "dup" and second.run_id.startswith("dup_")
    assert first.run_dir != second.run_dir
    assert len({first.run_id, second.run_id}) == 2


def test_the_mkdir_itself_is_the_collision_test(service, layout, monkeypatch):
    """BR-16: exists()-then-mkdir is a race. If mkdir is what detects the clash, a
    directory appearing between the check and the create cannot be shared."""
    calls = []
    real_mkdir = Path.mkdir

    def counting_mkdir(self, *args, **kwargs):
        calls.append(kwargs.get("exist_ok"))
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", counting_mkdir)
    service.submit(make_request(name="race"))
    assert False in calls, "the run directory must be created with exist_ok=False"


def test_collision_attempts_are_bounded(service, layout, monkeypatch):
    monkeypatch.setattr(
        "rfd_web.services.submission.secrets.token_hex", lambda n: "beef"
    )
    service.submit(make_request(name="fixed"))
    service.submit(make_request(name="fixed"))  # -> fixed_beef
    with pytest.raises(RuntimeError):
        service.submit(make_request(name="fixed"))


def test_max_collision_attempts_is_finite():
    assert 1 < MAX_COLLISION_ATTEMPTS < 100


# -- submission failure (NFR-10, BR-15) ---------------------------------------


def test_sbatch_failure_retains_the_run_and_shows_why(service, adapter, layout, repository):
    adapter.submit_error = "sbatch: error: Invalid partition name specified: gpu"
    outcome = service.submit(make_request(name="doomed"))

    assert outcome.ok is False
    run_dir = Path(outcome.run_dir)
    assert run_dir.is_dir(), "the directory is retained so the failure is diagnosable"
    assert (run_dir / "job.sh").is_file(), "and hand-resubmittable once fixed"

    record = RunRecord.load(run_dir)
    assert record.backbone_state is StageState.FAILED
    assert "Invalid partition name" in record.error
    assert repository.get("doomed").status is RunStatus.FAILED
    assert any("Invalid partition name" in e for e in outcome.errors)


def test_an_unreachable_controller_at_submit_time_is_also_surfaced(service, adapter):
    adapter.unavailable = True
    outcome = service.submit(make_request(name="offline"))
    assert outcome.ok is False and outcome.errors


# -- resubmission (FR-11, Q8=A, BR-17) ----------------------------------------


def _completed_run(service, repository, adapter, name="rerun"):
    outcome = service.submit(make_request(name=name))
    run_dir = Path(outcome.run_dir)
    record = RunRecord.load(run_dir)
    record.backbone_state = StageState.COMPLETED
    record.validate_state = StageState.FAILED
    record.error = "validation crashed"
    record.save(run_dir)
    repository.mark_terminal(outcome.run_id, RunStatus.FAILED)
    return outcome.run_id, run_dir


def test_resubmit_writes_alongside_and_resets_only_the_stage(service, repository, adapter):
    run_id, run_dir = _completed_run(service, repository, adapter)
    original_script = (run_dir / "job.sh").read_text()

    outcome = service.resubmit(run_id, stage=JobStage.VALIDATE)
    assert outcome.ok is True

    assert (run_dir / "job.sh").read_text() == original_script, "G-2: never overwritten"
    assert "--stage validate" in (run_dir / "job-validate.sh").read_text()

    record = RunRecord.load(run_dir)
    assert record.validate_state is StageState.PENDING
    assert record.backbone_state is StageState.COMPLETED
    assert record.error is None
    assert record.slurm_job_id == outcome.slurm_job_id

    # Both attempts are remembered in the index, because RunRecord has only one
    # slurm_job_id field and this unit does not reopen an approved rfd-core model.
    history = repository.get(run_id).job_id_history
    assert len(history) == 2
    assert history[-1] == outcome.slurm_job_id


def test_resubmit_refuses_without_a_completed_backbone(service, repository, adapter):
    outcome = service.submit(make_request(name="early"))
    result = service.resubmit(outcome.run_id, stage=JobStage.VALIDATE)
    assert result.ok is False
    assert "backbone" in result.errors[0]


def test_resubmit_refuses_while_a_job_is_live(service, repository, adapter):
    run_id, run_dir = _completed_run(service, repository, adapter, name="live")
    repository.update_state(run_id, terminal=0)
    result = service.resubmit(run_id, stage=JobStage.VALIDATE)
    assert result.ok is False and "terminal" in result.errors[0]


def test_resubmit_of_an_unknown_run_is_a_value_not_a_crash(service):
    assert service.resubmit("nope").ok is False


# -- cancellation (FR-14, BR-8, BR-11) ----------------------------------------


def test_cancel_records_the_request_before_calling_scancel(service, adapter, repository):
    outcome = service.submit(make_request(name="tocancel"))
    order = []
    original = adapter.cancel

    def spy(job_id):
        order.append(("scancel", repository.get(outcome.run_id).cancel_requested_at is not None))
        return original(job_id)

    adapter.cancel = spy  # type: ignore[assignment]
    result = service.cancel(outcome.run_id)

    assert result.ok is True
    assert order == [("scancel", True)], (
        "cancel_requested_at must be written FIRST -- a crash between the two steps "
        "still has to leave the evidence that a human asked for this"
    )


def test_cancel_writes_no_terminal_state_locally(service, adapter, repository):
    """Slurm owns the ending; writing it optimistically would show a run as cancelled
    while a failed scancel let it keep consuming a GPU."""
    outcome = service.submit(make_request(name="tocancel2"))
    service.cancel(outcome.run_id)
    record = RunRecord.load(Path(outcome.run_dir))
    assert record.backbone_state is StageState.PENDING
    assert repository.get(outcome.run_id).terminal is False


def test_cancelling_a_run_with_no_job_is_a_clear_value(service, layout, repository):
    from conftest import make_record

    run_dir = layout.run_dir("nojob")
    run_dir.mkdir(parents=True)
    make_record(run_dir, run_id="nojob").save(run_dir)
    result = service.cancel("nojob")
    assert result.ok is False and "no Slurm job" in result.errors[0]


def test_cancel_surfaces_an_unreachable_controller(service, adapter):
    outcome = service.submit(make_request(name="tocancel3"))
    adapter.unavailable = True
    result = service.cancel(outcome.run_id)
    assert result.ok is False and "scancel failed" in result.errors[0]


def test_a_failed_resubmission_surfaces_its_reason(service, repository, adapter):
    run_id, run_dir = _completed_run(service, repository, adapter, name="badrerun")
    adapter.submit_error = "sbatch: error: Requested time limit exceeds partition limit"
    result = service.resubmit(run_id, stage=JobStage.VALIDATE)
    assert result.ok is False
    assert "time limit" in result.errors[0]
    assert repository.get(run_id).status is RunStatus.FAILED
