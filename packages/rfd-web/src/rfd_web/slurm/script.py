"""C-23 JobScriptGenerator -- programmatic emission of the job script M1 proved.

Q2=A: this emits the shape of scripts/m1-submit.sh, the only version of this script with
a successful real execution behind it (job 7556085), NOT the pre-correction
deployment-architecture.md section 3 template, whose runner invocation could never have
worked (--run-dir and --scratch do not exist; the interpreter is not python3.9 on PATH).

Two deliberate differences from the hand-written M1 script, both documented in
deployment-architecture.md section 3:
  1. Logs go INTO the run directory, so RunDirectoryReader can find them for FR-19.
     The hand-written script wrote %x-%j.out into the submission directory, which is
     fine for one manual smoke test and useless to a program.
  2. run_dir is interpolated literally rather than taken as $1, so a generated script
     is resubmittable with a bare `sbatch job.sh` (G-2).

generate_job_script() is PURE -- a string in, a string out, no filesystem -- so the
#SBATCH block and the exec argv can be asserted directly in tests. write_job_script()
is the only part that touches disk.
"""
from __future__ import annotations

import re
import shlex
from enum import Enum
from pathlib import Path
from typing import Optional, Union

from rfd_core import PathLayout, RunRecord

from ..config import WebConfig
from ..errors import JobScriptError


class JobStage(str, Enum):
    """Mirrors rfd_runner's --stage choices.

    Deliberately re-declared here rather than imported: rfd-web must never depend on
    rfd-runner (DD-1, NFR-2), and this is a three-value command-line contract, not
    shared logic. tests/test_boundaries.py enforces the absence of that import.
    """

    ALL = "all"
    BACKBONE = "backbone"
    VALIDATE = "validate"


#: The script name for each stage. A resubmission writes alongside the original rather
#: than over it (D-6, BR-17) -- G-2 requires the script a run was first submitted with
#: to remain on disk exactly as submitted.
SCRIPT_NAMES = {
    JobStage.ALL: "job.sh",
    JobStage.BACKBONE: "job-backbone.sh",
    JobStage.VALIDATE: "job-validate.sh",
}

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_SLURM_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_WALLTIME_RE = re.compile(r"^(\d+-\d{2}:\d{2}:\d{2}|\d{1,3}:\d{2}:\d{2})$")
_MEM_RE = re.compile(r"^\d+[KMGT]?$")


def _check(value: str, pattern: "re.Pattern[str]", what: str) -> str:
    if not isinstance(value, str) or not pattern.match(value):
        raise JobScriptError(
            "invalid {0} for a job script: {1!r}".format(what, value)
        )
    return value


def _check_int(value: int, what: str, minimum: int = 1) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise JobScriptError(
            "invalid {0} for a job script: {1!r} (must be an integer >= {2})".format(
                what, value, minimum
            )
        )
    return value


def _check_path(value: Union[str, Path], what: str) -> str:
    """Paths are absolute and free of whitespace and quoting characters.

    The whitespace rule is not fussiness: #SBATCH directive lines are read by Slurm,
    NOT by a shell, so shlex.quote() there would put literal quote characters into the
    filename. A path that cannot be written unquoted into a #SBATCH line is therefore
    refused loudly rather than silently mangled (BR-12).
    """
    text = str(value)
    if not text:
        raise JobScriptError("empty {0}".format(what))
    if not text.startswith("/"):
        raise JobScriptError("{0} must be an absolute path: {1!r}".format(what, text))
    for bad in (" ", "\t", "\n", "\r", "\0", "'", '"', "`", "$", "\\"):
        if bad in text:
            raise JobScriptError(
                "{0} contains a character that cannot appear unquoted in an #SBATCH "
                "directive ({1!r}): {2!r}".format(what, bad, text)
            )
    return text


def generate_job_script(
    record: RunRecord,
    layout: PathLayout,
    config: WebConfig,
    stage: JobStage = JobStage.ALL,
) -> str:
    """Render the job script for `record`. Pure: no filesystem access."""
    stage = JobStage(stage)
    request = record.request

    run_id = _check(record.run_id, _RUN_ID_RE, "run id")
    partition = _check(request.partition, _SLURM_NAME_RE, "partition")
    walltime = _check(request.walltime, _WALLTIME_RE, "walltime")
    mem_per_cpu = _check(request.mem_per_cpu, _MEM_RE, "mem-per-cpu")
    gpus = _check_int(request.gpus, "gpus")
    cpus = _check_int(request.cpus_per_task, "cpus-per-task")

    account: Optional[str] = None
    if request.account:
        account = _check(request.account, _SLURM_NAME_RE, "account")

    run_dir = _check_path(record.run_dir, "run directory")
    image_path = _check_path(layout.image_path, "image path")
    weights_root = _check_path(layout.weights_root, "weights root")
    project_root = _check_path(config.project_root, "project root")
    cache_dir = _check_path(config.apptainer_cachedir, "apptainer cache dir")

    q = shlex.quote  # shell body only; never in an #SBATCH line

    lines = [
        "#!/bin/bash",
        "#SBATCH --job-name=rfd-{0}".format(run_id),
        "#SBATCH --partition={0}".format(partition),
        "#SBATCH --gpus={0}".format(gpus),
        "#SBATCH --nodes=1",
        "#SBATCH --ntasks=1",
        "#SBATCH --cpus-per-task={0}".format(cpus),
        "#SBATCH --mem-per-cpu={0}".format(mem_per_cpu),
        "#SBATCH --time={0}".format(walltime),
        "#SBATCH --output={0}/job-%j.out".format(run_dir),
        "#SBATCH --error={0}/job-%j.err".format(run_dir),
    ]
    if account is not None:
        lines.append("#SBATCH --account={0}".format(account))
    lines += [
        '# NOTE: --qos is deliberately never emitted (Grex docs: "Not to be used on Grex!")',
        "#",
        "# Generated by rfd-web (U3, C-23 JobScriptGenerator) for run {0}.".format(run_id),
        "# Retained in the run directory and resubmittable by hand with a bare",
        "# `sbatch job.sh` (G-2).",
        "",
        "# Deliberately no `set -e`: the exec below must be allowed to fail so its exit",
        "# code can be captured into `rc` and reported accurately through sacct, which",
        "# FR-19 depends on.",
        "set -u",
        "",
        # Double quotes, not shlex.quote: single-quoting this would make it a literal
        # string and defeat the parameter expansion. _check_path has already refused
        # any run_dir containing whitespace, quotes, backslash or '$', which is what
        # makes writing it inside double quotes safe.
        'cd "${{SLURM_SUBMIT_DIR:-{0}}}"'.format(run_dir),
        "",
        'echo "Starting run at: $(date)"',
        'echo "Job ID: ${SLURM_JOB_ID:-none} on host: $(hostname)"',
        'echo "Run dir: {0}"'.format(run_dir),
        "",
        "# Grex sets TMPDIR, not SLURM_TMPDIR; CCEnv scripts may expect the latter",
        "# (G-11, G-12). The bind source must exist or the engine refuses to start;",
        "# Slurm normally creates it itself.",
        "export TMPDIR=${TMPDIR:-/tmp}",
        "export SLURM_TMPDIR=$TMPDIR",
        'mkdir -p "$TMPDIR"',
        "",
        "# G-18: set the cache dir deliberately, or it grows silently against the",
        "# 100 GB /home quota.",
        "export APPTAINER_CACHEDIR={0}".format(q(cache_dir)),
        "export SINGULARITY_CACHEDIR={0}".format(q(cache_dir)),
        "",
        "# G-15. Grex's module is named `singularity` and puts a `singularity` binary on",
        "# PATH; CCEnv exposes `apptainer` instead. Same program, same flags -- but the",
        "# name must be DETECTED, not assumed. Assuming `apptainer` killed M1 job 7556080",
        "# with exit 127 before the container ever started.",
        "module load singularity 2>/dev/null || module load apptainer 2>/dev/null || true",
        "ENGINE=$(command -v singularity || command -v apptainer || true)",
        'if [ -z "$ENGINE" ]; then',
        '  echo "ERROR: no singularity/apptainer on PATH after module load (G-15)" >&2',
        "  exit 127",
        "fi",
        'echo "Engine: $ENGINE ($($ENGINE --version 2>&1))"',
        "",
        "# Fail before the exec rather than inside it, so a missing prerequisite reports",
        "# itself by name instead of surfacing as an opaque non-zero rc from the runner.",
        "for p in {0} {1}; do".format(q(image_path), q(run_dir + "/run.json")),
        '  [ -f "$p" ] || { echo "ERROR: required path missing: $p" >&2; exit 2; }',
        "done",
        "if [ ! -d {0} ]; then".format(q(weights_root)),
        '  echo "ERROR: weights dir missing: {0} (run scripts/stage-weights.sh)" >&2'.format(
            weights_root
        ),
        "  exit 2",
        "fi",
        "",
        "nvidia-smi",
        "",
        '"$ENGINE" exec --nv \\',
        "  --bind {0}:/opt/rfdgui:ro \\".format(q(project_root)),
        "  --bind {0}:/opt/weights:ro \\".format(q(weights_root)),
        "  --bind {0}:/opt/outputs/run \\".format(q(run_dir)),
        '  --bind "$TMPDIR":/scratch \\',
        "  {0} \\".format(q(image_path)),
        "  /app/RFdiffusion/.venv/bin/python -m rfd_runner /opt/outputs/run --stage {0}".format(
            stage.value
        ),
        "",
        "rc=$?",
        'echo "Job finished with exit code $rc at: $(date)"',
        "exit $rc",
        "",
    ]
    return "\n".join(lines)


def write_job_script(
    record: RunRecord,
    layout: PathLayout,
    config: WebConfig,
    stage: JobStage = JobStage.ALL,
    run_dir: Optional[Path] = None,
) -> Path:
    """Render and write the script into the run directory, returning its path."""
    stage = JobStage(stage)
    target_dir = Path(run_dir) if run_dir is not None else Path(record.run_dir)
    script = generate_job_script(record, layout, config, stage=stage)
    path = target_dir / SCRIPT_NAMES[stage]
    target_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(script)
    path.chmod(0o755)
    return path


class JobScriptGenerator:
    """Thin object wrapper, so services can be constructed with a fake generator."""

    def __init__(self, layout: PathLayout, config: WebConfig) -> None:
        self.layout = layout
        self.config = config

    def generate(self, record: RunRecord, stage: JobStage = JobStage.ALL) -> str:
        return generate_job_script(record, self.layout, self.config, stage=stage)

    def write(
        self,
        record: RunRecord,
        stage: JobStage = JobStage.ALL,
        run_dir: Optional[Path] = None,
    ) -> Path:
        return write_job_script(
            record, self.layout, self.config, stage=stage, run_dir=run_dir
        )
