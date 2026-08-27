"""FakeSlurmAdapter honours the C-21 protocol (NFR-18, D-5)."""
from __future__ import annotations

import pytest

from rfd_web.errors import SlurmSubmitError, SlurmUnavailable
from rfd_web.slurm.adapter import SlurmAdapter
from rfd_web.slurm.fake import FakeSlurmAdapter
from rfd_web.slurm.states import JobStatus, SlurmState


def test_fake_satisfies_the_protocol():
    assert isinstance(FakeSlurmAdapter(), SlurmAdapter)


def test_submit_records_script_and_cwd_and_hands_out_ids(tmp_path):
    fake = FakeSlurmAdapter(first_job_id=42)
    script = tmp_path / "job.sh"
    script.write_text("#!/bin/bash\n")
    assert fake.submit(script, tmp_path) == "42"
    assert fake.submit(script, tmp_path) == "43"
    assert fake.submissions == [(script, tmp_path), (script, tmp_path)]


def test_sequences_advance_then_hold_on_the_last_entry():
    fake = FakeSlurmAdapter()
    fake.set_sequence(
        "1",
        [
            JobStatus(state=SlurmState.PENDING),
            JobStatus(state=SlurmState.RUNNING),
            JobStatus(state=SlurmState.COMPLETED, exit_code=0),
        ],
    )
    assert fake.status("1").state is SlurmState.PENDING
    assert fake.status("1").state is SlurmState.RUNNING
    # a terminal state repeats forever, as it does in reality
    assert fake.status("1").state is SlurmState.COMPLETED
    assert fake.status("1").state is SlurmState.COMPLETED


def test_unknown_job_is_known_false():
    status = FakeSlurmAdapter().status("nope")
    assert status.state is SlurmState.UNKNOWN and status.known is False


def test_cancel_moves_the_job_to_cancelled():
    fake = FakeSlurmAdapter()
    fake.set_state("1", SlurmState.RUNNING)
    fake.cancel("1")
    assert fake.cancelled == ["1"]
    assert fake.status("1").state is SlurmState.CANCELLED


def test_status_calls_are_counted(tmp_path):
    """BR-3 is asserted by call counting, so the fake has to keep the count."""
    fake = FakeSlurmAdapter()
    fake.set_state("1", SlurmState.RUNNING)
    fake.status("1")
    fake.status("1")
    assert fake.status_call_count == 2


def test_unavailable_mode_reaches_the_br4_branch(tmp_path):
    fake = FakeSlurmAdapter()
    fake.unavailable = True
    for call in (
        lambda: fake.status("1"),
        lambda: fake.cancel("1"),
        lambda: fake.partitions(),
        lambda: fake.submit(tmp_path / "job.sh", tmp_path),
    ):
        with pytest.raises(SlurmUnavailable):
            call()


def test_submit_error_mode(tmp_path):
    fake = FakeSlurmAdapter()
    fake.submit_error = "sbatch: error: Invalid partition name specified"
    with pytest.raises(SlurmSubmitError) as exc:
        fake.submit(tmp_path / "job.sh", tmp_path)
    assert "Invalid partition" in exc.value.stderr
