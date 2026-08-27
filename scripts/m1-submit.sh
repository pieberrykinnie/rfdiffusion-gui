#!/bin/bash
#SBATCH --job-name=rfd-m1-smoke
#SBATCH --partition=gpu
#SBATCH --gpus=1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=6
#SBATCH --mem-per-cpu=6000M
#SBATCH --time=0-00:30:00
#SBATCH --output=%x-%j.out
#SBATCH --error=%x-%j.err
# NOTE: --qos is deliberately never emitted (Grex docs: "Not to be used on Grex!")
#
# Milestone M1 (unit-of-work.md): a hand-written job script, submitted with
# plain `sbatch`, running U1's image + U2a/U2b's rfd-runner together for the
# first time on a real Grex GPU node. This script is the concrete instance of
# the template documented in
# aidlc-docs/construction/u1-runtime-container/infrastructure-design/deployment-architecture.md
# section 3 -- U3's JobScriptGenerator (C-23) will later emit scripts like
# this one programmatically, per run.
#
# Usage (run scripts/m1-prepare-run.sh first to get a run_dir):
#
#   sbatch scripts/m1-submit.sh <run_dir>

# Deliberately no `set -e`: the apptainer exec below must be allowed to fail
# so its exit code can be captured into `rc` and reported via `sacct`, per
# deployment-architecture.md section 3's "rc=$?" note.
set -u

if [ $# -ne 1 ]; then
  echo "usage: sbatch scripts/m1-submit.sh <run_dir>" >&2
  exit 2
fi
RUN_DIR=$(readlink -f "$1")

# G-1: cd to the submit dir first (sbatch runs on the allocated node, not
# necessarily with "$0" resolvable the way a directly-invoked script would
# have it -- submit this from the repo root, as scripts/m1-prepare-run.sh's
# own usage instructions assume).
cd "${SLURM_SUBMIT_DIR:-$(dirname "$0")/..}"
ROOT=$(pwd)
[ -f "${ROOT}/env.example" ] && [ -f "${ROOT}/.env" ] && . "${ROOT}/.env"

RFD_PROJECT_ROOT=${RFD_PROJECT_ROOT:-$ROOT}
RFD_WEIGHTS=${RFD_WEIGHTS:-$HOME/rfd-weights}
RFD_IMAGE=${RFD_IMAGE:-$HOME/rfd-images/rfdiffusion.sif}
APPTAINER_CACHEDIR=${APPTAINER_CACHEDIR:-$HOME/.cache/apptainer}
SINGULARITY_CACHEDIR=${SINGULARITY_CACHEDIR:-$APPTAINER_CACHEDIR}
export APPTAINER_CACHEDIR SINGULARITY_CACHEDIR   # G-18

echo "Starting run at: $(date)"
echo "Job ID: ${SLURM_JOB_ID:-none} on host: $(hostname)"
echo "RUN_DIR: ${RUN_DIR}"

# Grex sets TMPDIR; CCEnv scripts may expect SLURM_TMPDIR
export TMPDIR=${TMPDIR:-/tmp}
export SLURM_TMPDIR=$TMPDIR
# The bind source must exist or the engine refuses to start. Slurm normally
# creates $TMPDIR itself; this only covers the case where it did not.
mkdir -p "$TMPDIR"

# G-15. Grex's module is named `singularity` and puts a `singularity` binary on
# PATH; CCEnv exposes `apptainer` instead. Job 7556080 died with exit 127
# ("apptainer: command not found") because this script hardcoded the CCEnv name
# after `module load singularity` had already succeeded. Detect the binary the
# same way scripts/build-image.sh and scripts/verify-image.sh already do -- the
# two names are the same program, and every flag used below is common to both.
module load singularity 2>/dev/null || module load apptainer 2>/dev/null || true
ENGINE=$(command -v singularity || command -v apptainer || true)
if [ -z "$ENGINE" ]; then
  echo "ERROR: no singularity/apptainer on PATH after module load (G-15)" >&2
  exit 127
fi
echo "Engine: $ENGINE ($($ENGINE --version 2>&1))"

# Fail before the exec rather than inside it, so a missing prerequisite reports
# itself instead of surfacing as an opaque non-zero rc from the runner.
for p in "${RFD_IMAGE}" "${RUN_DIR}/run.json"; do
  [ -f "$p" ] || { echo "ERROR: required path missing: $p" >&2; exit 2; }
done
[ -d "${RFD_WEIGHTS}" ] || { echo "ERROR: weights dir missing: ${RFD_WEIGHTS} (run scripts/stage-weights.sh)" >&2; exit 2; }

nvidia-smi

"$ENGINE" exec --nv \
  --bind "${RFD_PROJECT_ROOT}:/opt/rfdgui:ro" \
  --bind "${RFD_WEIGHTS}:/opt/weights:ro" \
  --bind "${RUN_DIR}:/opt/outputs/run" \
  --bind "${TMPDIR}:/scratch" \
  "${RFD_IMAGE}" \
  /app/RFdiffusion/.venv/bin/python -m rfd_runner /opt/outputs/run --stage all

rc=$?
echo "Job finished with exit code $rc at: $(date)"
exit $rc
