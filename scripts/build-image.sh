#!/bin/bash
# Build the rfdiffusion-gui Phase 1 container image on Grex.
#
#   bash scripts/build-image.sh [--force]
#
# Run this INSIDE a CPU allocation, not on a login node -- a multi-GB image
# build is exactly the heavy work login nodes are not for (Grex docs). Get one
# with:
#
#   salloc --partition=skylake --cpus-per-task=4 --mem=16000M --time=0-02:00:00
#
# No GPU is needed to build; only to verify (scripts/verify-image.sh).

set -euo pipefail

cd "$(dirname "$0")/.."
ROOT=$(pwd)
[ -f "${ROOT}/env.example" ] && [ -f "${ROOT}/.env" ] && . "${ROOT}/.env"

RFD_IMAGE=${RFD_IMAGE:-$HOME/rfd-images/rfdiffusion.sif}
APPTAINER_CACHEDIR=${APPTAINER_CACHEDIR:-$HOME/.cache/apptainer}
SINGULARITY_CACHEDIR=${SINGULARITY_CACHEDIR:-$APPTAINER_CACHEDIR}
export APPTAINER_CACHEDIR SINGULARITY_CACHEDIR   # G-18

DEF="${ROOT}/containers/rfdiffusion.def"
FORCE=0
[ "${1:-}" = "--force" ] && FORCE=1

say() { printf '\n>>> %s\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

# --- Refuse to build on a login node --------------------------------------
# Grex login nodes are yak and bison. A build here would be antisocial and may
# be killed mid-way, leaving a corrupt SIF.
HOST=$(hostname -s 2>/dev/null || hostname)
case "$HOST" in
  yak*|bison*|grex*)
    if [ -z "${SLURM_JOB_ID:-}" ]; then
      die "Refusing to build on login node '$HOST'.
     Building a multi-GB image on a login node is against Grex usage guidance.
     Get a CPU allocation first:
       salloc --partition=skylake --cpus-per-task=4 --mem=16000M --time=0-02:00:00
     then rerun this script."
    fi
    ;;
esac

[ -f "$DEF" ] || die "definition not found: $DEF"

if [ -f "$RFD_IMAGE" ] && [ "$FORCE" -eq 0 ]; then
  die "image already exists: $RFD_IMAGE
     Rerun with --force to rebuild, or set RFD_IMAGE to a different path."
fi

say "Loading singularity module"
module load singularity 2>/dev/null || module load apptainer 2>/dev/null || \
  die "could not load singularity or apptainer (G-15)"

if command -v singularity >/dev/null 2>&1; then
  ENGINE=singularity
elif command -v apptainer >/dev/null 2>&1; then
  ENGINE=apptainer
else
  die "no singularity/apptainer binary on PATH after module load"
fi
say "Using: $($ENGINE --version)"

mkdir -p "$APPTAINER_CACHEDIR" "$(dirname "$RFD_IMAGE")"

say "Cache dir: $APPTAINER_CACHEDIR"
say "Target:    $RFD_IMAGE"
say "Definition: $DEF"

# --- Quota warning ---------------------------------------------------------
# The build cache can transiently equal the image size again. On a 100 GB
# /home quota that is worth knowing before, not during.
if command -v quota >/dev/null 2>&1; then
  say "Current quota usage:"
  quota -s 2>/dev/null | sed 's/^/    /' || true
fi

say "Building (expect 15-40 minutes; most of it is pulling base layers)"
set +e
$ENGINE build --fakeroot "$RFD_IMAGE" "$DEF"
BUILD_RC=$?
set -e

if [ "$BUILD_RC" -ne 0 ]; then
  cat >&2 <<'EOF'

Build FAILED.

Documented fallback chain (infrastructure-design.md section 8):

  1. Sylabs remote build (needs a free Sylabs Cloud account):
       singularity remote login
       singularity build --remote $RFD_IMAGE containers/rfdiffusion.def

  2. Build locally with Docker/Podman, then convert and transfer:
       docker build -t rfdgui -f containers/Dockerfile .
       # or: podman build ...
       singularity build rfdiffusion.sif docker-daemon://rfdgui:latest
       rsync -avP rfdiffusion.sif grex:$RFD_IMAGE

If the failure is in the JAX step specifically, see the fallback ladder in
containers/rfdiffusion.def (%post) -- that is a known risk with a planned
answer, not an unknown.
EOF
  exit "$BUILD_RC"
fi

say "Build complete"
ls -lh "$RFD_IMAGE"

say "Running the image's built-in %test section"
$ENGINE test "$RFD_IMAGE" || \
  printf '\nWARNING: %%test reported problems -- run scripts/verify-image.sh on a GPU node for detail.\n'

cat <<EOF

Next:
  1. Stage model weights:   bash scripts/stage-weights.sh
  2. Verify on a GPU node:  salloc --partition=gpu --gpus=1 --cpus-per-task=6 \\
                              --mem-per-cpu=6000M --time=0-00:30:00
                            bash scripts/verify-image.sh
EOF
