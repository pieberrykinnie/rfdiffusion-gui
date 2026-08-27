"""The M1 lesson, tested by EXECUTION rather than by reading.

aidlc-state.md records that M1 job 7556080 died at exit 127 -- an entire GPU allocation
spent discovering something not GPU-dependent at all -- because the job script hardcoded
the CCEnv binary name `apptainer` while Grex's `singularity` module provides
`singularity`. That bug was invisible to every existing test, and `bash -n` would not
have caught it either: the script was syntactically perfect.

So these tests run the generated script under real bash with a stub engine on PATH,
across the same four scenarios the M1 fix was verified against.
"""
from __future__ import annotations

import os
import subprocess

import pytest

from rfd_web.slurm.script import JobStage, write_job_script

from conftest import make_record, write_stub


# The version probe must NOT be recorded: the script echoes `$ENGINE --version` into the
# job log before the precondition checks, and the "engine was never invoked" assertions
# below are about the exec, not about that probe.
ENGINE_STUB = """
if [ "$1" = "--version" ]; then echo "{name} version 3.8.0-stub"; exit 0; fi
printf '%s\\n' "$@" > {argv_dump}
exit 0
"""


@pytest.fixture
def prepared(layout, config, tmp_path, stub_bin, monkeypatch):
    """A run directory with run.json and job.sh, plus a scratch TMPDIR."""
    run_dir = layout.run_dir("smoke")
    run_dir.mkdir(parents=True)
    record = make_record(run_dir, run_id="smoke")
    record.save(run_dir)
    script = write_job_script(record, layout, config, stage=JobStage.ALL)

    # nvidia-smi and `module` do not exist on a dev box; stub them so the script runs
    # to the point that actually matters -- the exec line.
    write_stub(stub_bin, "nvidia-smi", "echo 'stub nvidia-smi'")
    write_stub(stub_bin, "module", "exit 1")
    monkeypatch.setenv("TMPDIR", str(tmp_path / "scratch"))
    return script, run_dir


def run_script(script, extra_env=None):
    env = dict(os.environ)
    env.update(extra_env or {})
    return subprocess.run(
        ["bash", str(script)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        env=env,
        timeout=30,
    )


def install_engine(stub_bin, name, argv_dump):
    write_stub(stub_bin, name, ENGINE_STUB.format(argv_dump=argv_dump, name=name))


# -- scenario 1: Grex -- only `singularity` exists ----------------------------


def test_grex_case_resolves_singularity_and_execs(prepared, stub_bin, tmp_path):
    script, run_dir = prepared
    argv_dump = tmp_path / "argv.txt"
    install_engine(stub_bin, "singularity", argv_dump)

    result = run_script(script)
    assert result.returncode == 0, result.stderr
    assert "Engine: " in result.stdout and "singularity" in result.stdout

    argv = argv_dump.read_text().splitlines()
    assert argv[0] == "exec"
    assert "--nv" in argv
    assert "--bind" in argv
    joined = " ".join(argv)
    assert "{0}:/opt/outputs/run".format(run_dir) in joined
    assert "/opt/rfdgui:ro" in joined
    assert "/opt/weights:ro" in joined
    assert "/scratch" in joined
    assert argv[-3:] == ["-m", "rfd_runner", "/opt/outputs/run"] or argv[-1] == "all"
    assert "/app/RFdiffusion/.venv/bin/python" in joined
    assert "--stage" in argv and "all" in argv


# -- scenario 2: CCEnv -- only `apptainer` exists -----------------------------


def test_ccenv_case_resolves_apptainer_and_execs(prepared, stub_bin, tmp_path):
    script, run_dir = prepared
    argv_dump = tmp_path / "argv.txt"
    install_engine(stub_bin, "apptainer", argv_dump)

    result = run_script(script)
    assert result.returncode == 0, result.stderr
    assert "apptainer" in result.stdout
    assert "--nv" in argv_dump.read_text()


# -- scenario 3: neither engine present ---------------------------------------


def test_no_engine_exits_127_with_the_g15_message(prepared, tmp_path, monkeypatch):
    script, _ = prepared
    # An empty PATH except for coreutils would break the script for the wrong reason;
    # instead point PATH at a directory holding only the non-engine stubs.
    minimal = tmp_path / "minimal"
    minimal.mkdir()
    write_stub(minimal, "nvidia-smi", "echo stub")
    write_stub(minimal, "module", "exit 1")
    result = run_script(script, {"PATH": "{0}:/usr/bin:/bin".format(minimal)})
    assert result.returncode == 127
    assert "no singularity/apptainer on PATH" in result.stderr
    assert "(G-15)" in result.stderr


# -- scenario 4: prerequisites missing ----------------------------------------


def test_missing_run_json_exits_2_before_the_exec(prepared, stub_bin, tmp_path):
    script, run_dir = prepared
    argv_dump = tmp_path / "argv.txt"
    install_engine(stub_bin, "singularity", argv_dump)
    (run_dir / "run.json").unlink()

    result = run_script(script)
    assert result.returncode == 2
    assert "required path missing" in result.stderr
    assert not argv_dump.exists(), "the engine must not have been invoked"


def test_missing_image_exits_2_before_the_exec(prepared, stub_bin, layout, tmp_path):
    script, _ = prepared
    argv_dump = tmp_path / "argv.txt"
    install_engine(stub_bin, "singularity", argv_dump)
    layout.image_path.unlink()

    result = run_script(script)
    assert result.returncode == 2
    assert not argv_dump.exists()


def test_missing_weights_dir_exits_2(prepared, stub_bin, layout, tmp_path):
    script, _ = prepared
    argv_dump = tmp_path / "argv.txt"
    install_engine(stub_bin, "singularity", argv_dump)
    (layout.weights_root / "bin").rmdir()
    layout.weights_root.rmdir()

    result = run_script(script)
    assert result.returncode == 2
    assert "weights dir missing" in result.stderr


# -- the exit code actually survives ------------------------------------------


def test_runner_failure_exit_code_is_propagated(prepared, stub_bin, tmp_path):
    """FR-19 depends on sacct reporting the real code, which depends on `rc=$?`."""
    script, _ = prepared
    write_stub(stub_bin, "singularity", 'if [ "$1" = "--version" ]; then echo v; exit 0; fi\nexit 42')
    result = run_script(script)
    assert result.returncode == 42
    assert "Job finished with exit code 42" in result.stdout


def test_script_is_syntactically_valid(prepared):
    script, _ = prepared
    check = subprocess.run(["bash", "-n", str(script)], stderr=subprocess.PIPE)
    assert check.returncode == 0, check.stderr


def test_validate_stage_script_execs_with_stage_validate(layout, config, stub_bin, tmp_path, monkeypatch):
    run_dir = layout.run_dir("smoke2")
    run_dir.mkdir(parents=True)
    record = make_record(run_dir, run_id="smoke2")
    record.save(run_dir)
    script = write_job_script(record, layout, config, stage=JobStage.VALIDATE)

    argv_dump = tmp_path / "argv.txt"
    install_engine(stub_bin, "singularity", argv_dump)
    write_stub(stub_bin, "nvidia-smi", "echo stub")
    write_stub(stub_bin, "module", "exit 1")
    monkeypatch.setenv("TMPDIR", str(tmp_path / "scratch2"))

    result = run_script(script)
    assert result.returncode == 0, result.stderr
    argv = argv_dump.read_text().splitlines()
    assert argv[-1] == "validate"
