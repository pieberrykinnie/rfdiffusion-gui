"""C-23: G-1 ... G-18 conformance, rule by rule, plus BR-12 and BR-13.

Success criterion 9 in requirements.md: "Every generated job script is one a Grex user
could have written by hand ... and passes review against https://um-grex.github.io/docs/
requirement-by-requirement (G-1 ... G-20)." These are that review, executable.
"""
from __future__ import annotations

import pytest

from rfd_web.errors import JobScriptError
from rfd_web.slurm.script import (
    SCRIPT_NAMES,
    JobStage,
    generate_job_script,
    write_job_script,
)

from conftest import make_record, make_request


@pytest.fixture
def record(layout):
    run_dir = layout.run_dir("smoke")
    run_dir.mkdir(parents=True)
    return make_record(run_dir, run_id="smoke")


@pytest.fixture
def script(record, layout, config):
    return generate_job_script(record, layout, config)


def directives(text):
    return [ln for ln in text.splitlines() if ln.startswith("#SBATCH")]


# -- G-1: documented template shape -------------------------------------------


def test_g1_shape(script):
    lines = script.splitlines()
    assert lines[0] == "#!/bin/bash"
    assert any(ln.startswith("cd ") for ln in lines)
    assert 'echo "Starting run at: $(date)"' in lines
    assert 'echo "Job finished with exit code $rc at: $(date)"' in lines
    assert "rc=$?" in lines
    assert lines[-1] == "exit $rc"
    assert script.endswith("\n")


def test_g1_cd_expands_slurm_submit_dir_rather_than_quoting_it_literally(script, record):
    """shlex.quote here would single-quote the whole expression and defeat it."""
    cd_line = [ln for ln in script.splitlines() if ln.startswith("cd ")][0]
    assert cd_line == 'cd "${{SLURM_SUBMIT_DIR:-{0}}}"'.format(record.run_dir)


# -- G-2: retained and hand-resubmittable -------------------------------------


def test_g2_script_is_written_into_the_run_directory(record, layout, config):
    path = write_job_script(record, layout, config)
    assert path == layout.run_dir("smoke") / "job.sh"
    assert path.read_text().startswith("#!/bin/bash")
    assert path.stat().st_mode & 0o111


def test_g2_run_dir_is_literal_not_an_argument(script, record):
    """A generated script belongs to one run and must run with a bare `sbatch job.sh`."""
    assert "$1" not in script
    assert record.run_dir in script


def test_g2_resubmission_writes_alongside_never_over(record, layout, config):
    first = write_job_script(record, layout, config, stage=JobStage.ALL)
    second = write_job_script(record, layout, config, stage=JobStage.VALIDATE)
    assert first.name == "job.sh"
    assert second.name == "job-validate.sh"
    assert first.exists() and second.exists()
    assert "--stage all" in first.read_text()
    assert "--stage validate" in second.read_text()


def test_every_stage_has_its_own_script_name():
    assert set(SCRIPT_NAMES) == set(JobStage)
    assert len(set(SCRIPT_NAMES.values())) == len(JobStage)


# -- G-3: --qos is never emitted ----------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"account": None},
        {"partition": "agpu"},
        {"gpus": 2, "cpus_per_task": 12, "mem_per_cpu": "8000M"},
    ],
)
def test_g3_qos_never_appears_under_any_configuration(layout, config, overrides):
    run_dir = layout.run_dir("smoke")
    run_dir.mkdir(parents=True, exist_ok=True)
    record = make_record(run_dir, request=make_request(**overrides))
    text = generate_job_script(record, layout, config)
    assert "--qos" not in text.replace(
        '# NOTE: --qos is deliberately never emitted (Grex docs: "Not to be used on Grex!")', ""
    )


def test_g3_the_reason_is_recorded_in_the_script(script):
    assert 'Not to be used on Grex!' in script


# -- G-4 ... G-8: explicit resources ------------------------------------------


def test_g4_time_and_memory_are_always_explicit(script):
    assert "#SBATCH --time=0-00:30:00" in script
    assert "#SBATCH --mem-per-cpu=6000M" in script


def test_g5_gpus_always_requested(script):
    assert "#SBATCH --gpus=1" in script


def test_g6_partition_always_explicit(script):
    assert "#SBATCH --partition=gpu" in script


def test_g7_g8_defaults_follow_grex_gpu_guidance(script):
    assert "#SBATCH --gpus=1" in script
    assert "#SBATCH --cpus-per-task=6" in script
    assert "#SBATCH --mem-per-cpu=6000M" in script


def test_account_is_emitted_only_when_configured(layout, config):
    run_dir = layout.run_dir("smoke")
    run_dir.mkdir(parents=True, exist_ok=True)

    with_account = make_record(run_dir, request=make_request(account="def-cardona"))
    assert "#SBATCH --account=def-cardona" in generate_job_script(with_account, layout, config)

    without = make_record(run_dir, request=make_request(account=None))
    assert "--account" not in generate_job_script(without, layout, config)


# -- G-11 ... G-13: scratch and staging ---------------------------------------


def test_g11_tmpdir_is_bound_as_scratch(script):
    assert '--bind "$TMPDIR":/scratch' in script


def test_g12_slurm_tmpdir_is_exported(script):
    assert "export SLURM_TMPDIR=$TMPDIR" in script


def test_g13_outputs_land_in_the_persistent_run_directory(script, record):
    assert "--bind {0}:/opt/outputs/run".format(record.run_dir) in script


# -- G-15 / BR-13: engine detection, never a binary name ----------------------


def test_g15_module_load_tries_both_names(script):
    assert (
        "module load singularity 2>/dev/null || module load apptainer 2>/dev/null || true"
        in script
    )


def test_br13_no_hardcoded_engine_command(script):
    """M1 job 7556080 died at exit 127 because a script named the CCEnv binary while
    Grex's module provides `singularity`. This generator must not reproduce that."""
    assert "apptainer exec" not in script
    assert "singularity exec" not in script
    assert 'ENGINE=$(command -v singularity || command -v apptainer || true)' in script
    assert '"$ENGINE" exec --nv' in script


def test_g15_missing_engine_exits_127_with_the_documented_message(script):
    assert "exit 127" in script
    assert "(G-15)" in script


# -- G-16 / G-17 / G-18 -------------------------------------------------------


def test_g16_image_is_referenced_by_path_never_pulled(script, layout):
    assert str(layout.image_path) in script
    assert "docker://" not in script and "pull" not in script


def test_g17_nv_flag_present(script):
    assert "--nv" in script


def test_g18_both_cache_dirs_are_set(script, config):
    assert "export APPTAINER_CACHEDIR={0}".format(config.apptainer_cachedir) in script
    assert "export SINGULARITY_CACHEDIR={0}".format(config.apptainer_cachedir) in script


# -- the runner invocation (finding F-1) --------------------------------------


def test_runner_is_invoked_the_way_the_shipped_cli_actually_works(script):
    """The pre-correction template used `python3.9 -m rfd_runner --run-dir ... --scratch`.
    The real CLI takes a POSITIONAL run dir, has no --scratch, and the container's
    interpreter is the venv one."""
    assert (
        "/app/RFdiffusion/.venv/bin/python -m rfd_runner /opt/outputs/run --stage all"
        in script
    )
    assert "--run-dir" not in script
    assert "--scratch" not in script
    assert "python3.9" not in script


def test_fail_fast_preconditions_precede_the_exec(script):
    body = script.splitlines()
    exec_line = next(i for i, ln in enumerate(body) if ln.startswith('"$ENGINE" exec'))
    checks = next(i for i, ln in enumerate(body) if "required path missing" in ln)
    assert checks < exec_line


def test_no_set_e_so_the_exit_code_survives(script):
    # As executable lines, not as substrings -- the script explains in a comment WHY
    # `set -e` is absent, and that comment must not fail the test.
    executable = [ln.strip() for ln in script.splitlines() if not ln.strip().startswith("#")]
    assert "set -u" in executable
    assert "set -e" not in executable


# -- BR-12: whitelist, then quote ---------------------------------------------


@pytest.mark.parametrize(
    "field,value",
    [
        ("partition", "gpu; rm -rf /"),
        ("partition", "gpu\nmalicious"),
        ("walltime", "not-a-walltime"),
        ("walltime", "0-00:30"),
        ("mem_per_cpu", "6000MB"),
        ("gpus", 0),
        ("cpus_per_task", -1),
        ("account", "acct with space"),
    ],
)
def test_br12_bad_values_raise_rather_than_being_sanitised(layout, config, field, value):
    run_dir = layout.run_dir("smoke")
    run_dir.mkdir(parents=True, exist_ok=True)
    record = make_record(run_dir, request=make_request(**{field: value}))
    with pytest.raises(JobScriptError):
        generate_job_script(record, layout, config)


def test_br12_bad_run_id_raises(layout, config):
    run_dir = layout.run_dir("ok")
    run_dir.mkdir(parents=True, exist_ok=True)
    record = make_record(run_dir, run_id="../escape")
    with pytest.raises(JobScriptError):
        generate_job_script(record, layout, config)


def test_br12_a_path_that_cannot_be_written_unquoted_is_refused(layout, config, tmp_path):
    """#SBATCH lines are read by Slurm, not by a shell, so quoting there would put
    literal quote characters into the filename. Refuse loudly instead."""
    spaced = tmp_path / "run dir with spaces"
    spaced.mkdir()
    record = make_record(spaced, run_id="smoke")
    with pytest.raises(JobScriptError) as exc:
        generate_job_script(record, layout, config)
    assert "#SBATCH" in str(exc.value)


def test_br12_relative_paths_are_refused(layout, config):
    record = make_record("relative/run/dir", run_id="smoke")
    with pytest.raises(JobScriptError):
        generate_job_script(record, layout, config)


def test_generation_is_pure(record, layout, config, tmp_path):
    """generate_job_script touches no filesystem, which is what makes the whole
    #SBATCH block and exec argv assertable directly."""
    before = sorted(p.name for p in layout.run_dir("smoke").iterdir())
    generate_job_script(record, layout, config)
    after = sorted(p.name for p in layout.run_dir("smoke").iterdir())
    assert before == after
