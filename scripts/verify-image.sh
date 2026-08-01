#!/bin/bash
# Verify the rfdiffusion-gui container on a Grex GPU node.
#
# Run this INSIDE a GPU allocation:
#   salloc --partition=gpu --gpus=1 --cpus-per-task=6 --mem-per-cpu=6000M --time=0-00:30:00
#   bash scripts/verify-image.sh
#
# The checks are ordered so the two that could invalidate the whole approach
# run first (see infrastructure-design.md section 9):
#   check 3 -- the sokrypton fork is what is on PYTHONPATH (proves FR-16/FR-17
#              are achievable at all)
#   check 4 -- JAX imports and sees the GPU (the known CUDA-11 risk, with a
#              documented fallback ladder)

set -uo pipefail

cd "$(dirname "$0")/.."
ROOT=$(pwd)
[ -f "${ROOT}/.env" ] && . "${ROOT}/.env"

RFD_IMAGE=${RFD_IMAGE:-$HOME/rfd-images/rfdiffusion.sif}
RFD_WEIGHTS=${RFD_WEIGHTS:-$HOME/rfd-weights}

PASS=0; FAIL=0
ok()   { printf '  [ OK ]   %s\n' "$*"; PASS=$((PASS+1)); }
bad()  { printf '  [ FAIL ] %s\n' "$*"; FAIL=$((FAIL+1)); }
sect() { printf '\n=== %s\n' "$*"; }

[ -f "$RFD_IMAGE" ] || { printf 'ERROR: image not found: %s\n' "$RFD_IMAGE" >&2; exit 1; }

if [ -z "${SLURM_JOB_ID:-}" ]; then
  printf 'WARNING: not inside a Slurm allocation -- GPU checks will fail.\n'
  printf '         salloc --partition=gpu --gpus=1 --cpus-per-task=6 --mem-per-cpu=6000M --time=0-00:30:00\n\n'
fi

module load singularity 2>/dev/null || module load apptainer 2>/dev/null || true
ENGINE=$(command -v singularity || command -v apptainer)
[ -n "$ENGINE" ] || { printf 'ERROR: no singularity/apptainer on PATH\n' >&2; exit 1; }

SCRATCH="${TMPDIR:-/tmp}/rfd-verify-$$"
mkdir -p "$SCRATCH"
trap 'rm -rf "$SCRATCH"' EXIT
RUN="$ENGINE exec --nv --bind ${RFD_WEIGHTS}:/opt/weights --bind ${SCRATCH}:/scratch ${RFD_IMAGE}"

# The image's python is the base image's uv venv, not a system interpreter.
VPY=/app/RFdiffusion/.venv/bin/python

printf 'Verifying %s\n' "$RFD_IMAGE"
printf 'Engine:   %s\n' "$($ENGINE --version)"
printf 'Node:     %s\n' "$(hostname)"

# -------------------------------------------------------- 1. GPU visibility
sect "1. GPU visible inside the container"
OUT=$($RUN nvidia-smi --query-gpu=name,memory.total,compute_cap --format=csv 2>&1)
printf '%s\n' "$OUT" | sed 's/^/    /'
if printf '%s' "$OUT" | grep -qiE 'v100|a30|l40'; then
  ok "GPU visible via --nv"
else
  bad "no supported GPU reported -- check the allocation and --nv"
fi

# ------------------------------------------------------------- 2. torch/CUDA
sect "2. torch sees CUDA and the device is supported"
OUT=$($RUN $VPY -c "
import torch
print('torch', torch.__version__)
print('cuda_available', torch.cuda.is_available())
if torch.cuda.is_available():
    print('device', torch.cuda.get_device_name(0))
    print('capability', '.'.join(map(str, torch.cuda.get_device_capability(0))))
    print('arch_list', torch.cuda.get_arch_list())
" 2>&1)
printf '%s\n' "$OUT" | sed 's/^/    /'
if printf '%s' "$OUT" | grep -q 'cuda_available True'; then
  ok "torch reports CUDA available"
  CAP=$(printf '%s' "$OUT" | awk '/^capability/{print $2}')
  case "$CAP" in
    8.9) bad "device is sm_89 (L40s) -- NOT supported by this CUDA 11.6 image. Use --partition=gpu/agpu, or build the Phase 2 image." ;;
    "")  : ;;
    *)   ok "compute capability $CAP is covered by CUDA 11.6" ;;
  esac
else
  bad "torch cannot see CUDA"
fi

# --------------------------------------------------------- 3. THE FORK CHECK
sect "3. sokrypton fork is on PYTHONPATH (gates FR-16 / FR-17)"
N=$($RUN grep -c 'dump_pdb' /opt/RFdiffusion/config/inference/base.yaml 2>/dev/null | tr -d '[:space:]')
if [ "${N:-0}" -ge 2 ]; then
  ok "dump_pdb keys present (found $N) -- live progress is achievable"
  $RUN cat /opt/RFdiffusion.sha 2>/dev/null | sed 's/^/    fork sha: /'
else
  bad "dump_pdb keys MISSING -- this is the RosettaCommons build, not the fork.
           FR-16 (step progress) and FR-17 (live preview) cannot work. Rebuild the image."
fi

# ------------------------------------------------------------ 4. THE JAX RISK
sect "4. JAX imports and sees the GPU (known CUDA-11 risk)"
OUT=$($RUN $VPY -c "
import jax
print('jax', jax.__version__)
print('devices', jax.devices())
" 2>&1)
printf '%s\n' "$OUT" | sed 's/^/    /'
if printf '%s' "$OUT" | grep -q '^jax '; then
  if printf '%s' "$OUT" | grep -qi 'cuda\|gpu'; then
    ok "JAX imports and reports a GPU device"
  else
    bad "JAX imports but reports no GPU (CPU fallback would be very slow).
           See the fallback ladder in containers/rfdiffusion.def %post."
  fi
else
  bad "JAX failed to import -- this is the anticipated CUDA-11 risk.
           Fallback ladder (infrastructure-design.md section 3):
             1. jaxlib==0.4.7+cuda11.cudnn82
             2. two images (Q3=B): colabdesign.sif on a CUDA 12 base"
fi

# ----------------------------------------------------------- 5. dgl and e3nn
sect "5. dgl / e3nn import"
OUT=$($RUN $VPY -c "import dgl, e3nn; print('dgl', dgl.__version__, 'e3nn', e3nn.__version__)" 2>&1)
printf '%s\n' "$OUT" | sed 's/^/    /'
printf '%s' "$OUT" | grep -q '^dgl ' && ok "dgl and e3nn import" || bad "dgl/e3nn import failed"

# ---------------------------------------------------- 6. run_inference --help
sect "6. RFdiffusion entry point runs"
if $RUN $VPY /opt/RFdiffusion/run_inference.py --help >/dev/null 2>&1; then
  ok "run_inference.py --help succeeded"
else
  # Hydra returns non-zero for --help in some versions; fall back to an import.
  if $RUN $VPY -c "import sys; sys.path.insert(0,'/opt/RFdiffusion'); import inference.utils" 2>/dev/null; then
    ok "inference.utils imports (Hydra --help exit code is not meaningful here)"
  else
    bad "cannot run or import RFdiffusion from the fork"
  fi
fi

# --------------------------------------------------------------- 7. weights
sect "7. Model assets visible"
# Checkpoints ship inside the image (symlinked into the fork), not staged.
for f in Base_ckpt.pt Complex_base_ckpt.pt Complex_beta_ckpt.pt; do
  if $RUN test -s "/opt/RFdiffusion/models/$f"; then ok "in image: $f"; else bad "missing from image: $f -- rebuild"; fi
done
if $RUN test -d /opt/schedules-seed; then ok "in image: schedules seed"; else bad "missing from image: /opt/schedules-seed -- rebuild"; fi
if $RUN test -x /opt/weights/bin/ananas; then ok "present: ananas (symmetry=auto available)"; else printf '  [ WARN ] ananas missing -- symmetry="auto" will be unavailable\n'; fi
if $RUN test -d /opt/weights/alphafold; then ok "present: alphafold params"; else bad "missing: alphafold params"; fi

# ---------------------------------------------------------------- summary
sect "Summary"
printf '  PASS %d   FAIL %d\n\n' "$PASS" "$FAIL"
if [ "$FAIL" -gt 0 ]; then
  printf '  Verification FAILED. Checks 3 and 4 are the ones that change the plan --\n'
  printf '  report those specifically if they failed.\n'
  exit 1
fi
printf '  Image verified. U1 is done; milestone M1 is next (a real design via hand-written sbatch).\n'
