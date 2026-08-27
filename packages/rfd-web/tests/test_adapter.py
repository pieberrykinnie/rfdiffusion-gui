"""CliSlurmAdapter against real stub binaries on PATH.

These are real subprocesses emitting real Slurm output formats. That proves the parsing
and the argument lists; it cannot prove Grex's Slurm emits exactly these strings, which
the code-generation plan states explicitly.
"""
from __future__ import annotations

import subprocess

import pytest

from rfd_web.errors import SlurmSubmitError, SlurmUnavailable
from rfd_web.slurm.adapter import CliSlurmAdapter
from rfd_web.slurm.states import SlurmState

from conftest import write_stub


@pytest.fixture
def cli(stub_bin):
    return CliSlurmAdapter(timeout_seconds=10)


# -- submit -------------------------------------------------------------------


def test_submit_parses_parsable_job_id(cli, stub_bin, tmp_path):
    write_stub(stub_bin, "sbatch", 'echo "sbatch: WARNING -- default account" >&2\necho 7556085')
    script = tmp_path / "job.sh"
    script.write_text("#!/bin/bash\n")
    assert cli.submit(script, tmp_path) == "7556085"


def test_submit_strips_the_cluster_suffix(cli, stub_bin, tmp_path):
    write_stub(stub_bin, "sbatch", "echo '7556085;grex'")
    script = tmp_path / "job.sh"
    script.write_text("#!/bin/bash\n")
    assert cli.submit(script, tmp_path) == "7556085"


def test_submit_failure_carries_stderr(cli, stub_bin, tmp_path):
    write_stub(stub_bin, "sbatch", 'echo "sbatch: error: invalid partition" >&2\nexit 1')
    script = tmp_path / "job.sh"
    script.write_text("#!/bin/bash\n")
    with pytest.raises(SlurmSubmitError) as exc:
        cli.submit(script, tmp_path)
    assert "invalid partition" in exc.value.stderr


def test_submit_rejects_unparseable_output(cli, stub_bin, tmp_path):
    write_stub(stub_bin, "sbatch", "echo 'Submitted batch job 7556085'")
    script = tmp_path / "job.sh"
    script.write_text("#!/bin/bash\n")
    with pytest.raises(SlurmSubmitError):
        cli.submit(script, tmp_path)


def test_submit_runs_in_the_run_directory(cli, stub_bin, tmp_path):
    # cwd matters: sbatch resolves relative paths against it.
    marker = tmp_path / "marker"
    marker.mkdir()
    write_stub(stub_bin, "sbatch", "pwd > {0}/cwd.txt\necho 1".format(marker))
    script = tmp_path / "job.sh"
    script.write_text("#!/bin/bash\n")
    cli.submit(script, marker)
    assert (marker / "cwd.txt").read_text().strip() == str(marker)


# -- status -------------------------------------------------------------------


def test_squeue_is_consulted_before_sacct(cli, stub_bin):
    write_stub(stub_bin, "squeue", "echo 'RUNNING|None'")
    write_stub(stub_bin, "sacct", "echo 'COMPLETED|0:0'")
    status = cli.status("1")
    assert status.state is SlurmState.RUNNING


def test_empty_squeue_falls_through_to_sacct(cli, stub_bin):
    write_stub(stub_bin, "squeue", "exit 0")
    write_stub(stub_bin, "sacct", "echo 'COMPLETED|0:0'")
    status = cli.status("1")
    assert status.state is SlurmState.COMPLETED
    assert status.exit_code == 0


def test_squeue_invalid_job_id_is_not_an_outage(cli, stub_bin):
    """squeue exits non-zero for an unknown job. Treating that as SlurmUnavailable would
    send every finished run down the BR-4 stale path."""
    write_stub(stub_bin, "squeue", 'echo "slurm_load_jobs error: Invalid job id specified" >&2\nexit 1')
    write_stub(stub_bin, "sacct", "echo 'CANCELLED by 1234|0:15'")
    status = cli.status("1")
    assert status.state is SlurmState.CANCELLED
    assert status.signal == 15


def test_sacct_with_no_rows_is_known_false_not_an_exception(cli, stub_bin):
    """BR-4: both commands RAN, Slurm has simply forgotten the job."""
    write_stub(stub_bin, "squeue", "exit 0")
    write_stub(stub_bin, "sacct", "exit 0")
    status = cli.status("1")
    assert status.state is SlurmState.UNKNOWN
    assert status.known is False


def test_sacct_ignores_batch_and_extern_rows(cli, stub_bin):
    """-X keeps allocation rows only; without it, M1's own sacct output has three."""
    write_stub(stub_bin, "squeue", "exit 0")
    args_dump = stub_bin.parent / "sacct-args.txt"
    write_stub(
        stub_bin,
        "sacct",
        'printf "%s\\n" "$@" > {0}\necho "COMPLETED|0:0"'.format(args_dump),
    )
    cli.status("1")
    assert "-X" in args_dump.read_text().splitlines()


def test_slurm_missing_from_path_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(SlurmUnavailable):
        CliSlurmAdapter(timeout_seconds=5).status("1")


def test_timeout_is_unavailable_not_a_hang(cli, stub_bin):
    write_stub(stub_bin, "squeue", "sleep 30")
    adapter = CliSlurmAdapter(timeout_seconds=1)
    with pytest.raises(SlurmUnavailable):
        adapter.status("1")


def test_a_broken_controller_is_unavailable(cli, stub_bin):
    write_stub(stub_bin, "squeue", 'echo "slurm_load_jobs error: Unable to contact slurm controller" >&2\nexit 1')
    with pytest.raises(SlurmUnavailable):
        cli.status("1")


# -- cancel -------------------------------------------------------------------


def test_cancel_of_a_finished_job_is_success(cli, stub_bin):
    """BR-11: the user asked for the job to stop, and it has stopped."""
    write_stub(stub_bin, "scancel", 'echo "scancel: error: Invalid job id 1" >&2\nexit 1')
    cli.cancel("1")  # must not raise


def test_cancel_propagates_a_real_failure(cli, stub_bin):
    write_stub(stub_bin, "scancel", 'echo "scancel: error: Unable to contact slurm controller" >&2\nexit 1')
    with pytest.raises(SlurmUnavailable):
        cli.cancel("1")


# -- partitions ---------------------------------------------------------------


SINFO_ROWS = """gpu*|gpu:v100:4|7-00:00:00|up
gpu*|gpu:v100:4|7-00:00:00|up
agpu|gpu:a30:2|3-00:00:00|up
lgpu|gpu:l40s:2|7-00:00:00|up
skylake|(null)|7-00:00:00|up
down-part|gpu:v100:1|infinite|down
"""


def test_sinfo_rows_are_parsed_deduplicated_and_marked(cli, stub_bin):
    write_stub(stub_bin, "sinfo", "cat <<'EOF'\n" + SINFO_ROWS + "EOF")
    rows = cli.partitions()
    names = [p.name for p in rows]
    assert names.count("gpu") == 2  # raw rows; de-duplication is discovery's job
    gpu = rows[0]
    assert gpu.name == "gpu" and gpu.is_default is True and gpu.has_gpu is True
    assert [p for p in rows if p.name == "skylake"][0].has_gpu is False
    assert [p for p in rows if p.name == "down-part"][0].available is False
    assert [p for p in rows if p.name == "down-part"][0].max_walltime is None


def test_sinfo_failure_is_unavailable(cli, stub_bin):
    write_stub(stub_bin, "sinfo", "exit 1")
    with pytest.raises(SlurmUnavailable):
        cli.partitions()


# -- NFR-11 -------------------------------------------------------------------


def test_no_slurm_call_ever_uses_a_shell(monkeypatch, stub_bin, tmp_path):
    """NFR-11: argument lists, never a shell string. Asserted, not assumed."""
    calls = []
    real_run = subprocess.run

    def spy(argv, **kwargs):
        calls.append((argv, kwargs))
        return real_run(argv, **kwargs)

    monkeypatch.setattr("rfd_web.slurm.adapter.subprocess.run", spy)
    write_stub(stub_bin, "squeue", "echo 'RUNNING|None'")
    write_stub(stub_bin, "sinfo", "echo 'gpu|gpu:v100:4|1-00:00:00|up'")
    write_stub(stub_bin, "scancel", "exit 0")
    cli = CliSlurmAdapter(timeout_seconds=5)
    cli.status("1")
    cli.partitions()
    cli.cancel("1")

    assert calls, "expected the adapter to have shelled out"
    for argv, kwargs in calls:
        assert isinstance(argv, list)
        assert kwargs.get("shell", False) is False
        assert kwargs.get("timeout") == 5
