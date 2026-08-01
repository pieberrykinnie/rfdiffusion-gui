#!/bin/bash
# Preflight sanity checks for rfdiffusion-gui on Grex.
#
# Run this on a Grex LOGIN NODE before building the container or staging weights.
# It verifies every assumption the U1 infrastructure design rests on, and prints
# a summary at the end. Nothing is installed, downloaded, or modified.
#
#   bash scripts/preflight-grex.sh
#
# Optionally also submit a tiny GPU probe job (checks the GPU model and $TMPDIR
# from inside a real allocation):
#
#   bash scripts/preflight-grex.sh --gpu-probe

set -u

PASS=0; WARN=0; FAIL=0
pass() { printf '  [ OK ]   %s\n' "$*"; PASS=$((PASS+1)); }
warn() { printf '  [ WARN ] %s\n' "$*"; WARN=$((WARN+1)); }
fail() { printf '  [ FAIL ] %s\n' "$*"; FAIL=$((FAIL+1)); }
section() { printf '\n=== %s\n' "$*"; }

GPU_PROBE=0
[ "${1:-}" = "--gpu-probe" ] && GPU_PROBE=1

printf 'rfdiffusion-gui preflight -- %s on %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(hostname)"

# ---------------------------------------------------------------- 1. Environment
section "1. Environment"
if command -v sinfo >/dev/null 2>&1; then
  pass "Slurm client tools present ($(sinfo --version 2>/dev/null))"
else
  fail "sinfo not found -- are you on a Grex login node?"
fi
printf '  info     user=%s  home=%s\n' "${USER:-?}" "${HOME:-?}"
printf '  info     login-node python3: %s\n' "$(python3 -V 2>&1 || echo 'not found')"

# ------------------------------------------------------------------ 2. Partitions
# ASSUMPTION UNDER TEST: gpu partition exists with V100s; whether lgpu exists.
# Grex's own docs disagree (partitions page says gpu/lgpu; batch-jobs page says
# gpu/stamps-b/livi-b/agro-b), which is why FR-6a discovers these at runtime.
section "2. GPU partitions and generations"
if command -v sinfo >/dev/null 2>&1; then
  printf '  %-14s %-10s %-22s %s\n' PARTITION TIMELIMIT GRES NODES
  sinfo -h -o '%P|%l|%G|%D' 2>/dev/null | while IFS='|' read -r p t g n; do
    case "$g" in
      *gpu*) printf '  %-14s %-10s %-22s %s\n' "$p" "$t" "$g" "$n" ;;
    esac
  done
  if sinfo -h -p gpu -o '%P' 2>/dev/null | grep -q .; then
    pass "'gpu' partition exists (Phase 1 target)"
  else
    fail "'gpu' partition NOT found -- Phase 1 targets it; tell Claude"
  fi
  if sinfo -h -p lgpu -o '%P' 2>/dev/null | grep -q .; then
    pass "'lgpu' partition exists (Phase 2 target, deferred)"
  else
    warn "'lgpu' not found -- fine for Phase 1; affects the deferred Phase 2 plan"
  fi
  printf '\n  GPU models visible to the scheduler:\n'
  sinfo -h -o '%P %G %N' 2>/dev/null | grep -i gpu | sed 's/^/    /' || true
  if command -v partition-list >/dev/null 2>&1; then
    printf '\n  partition-list (Grex custom):\n'; partition-list 2>&1 | sed 's/^/    /'
  fi
fi

# -------------------------------------------------------------------- 3. Accounts
# ASSUMPTION UNDER TEST: which --account values are valid (G-6 / FR-6).
section "3. Slurm accounting groups"
if command -v sacctmgr >/dev/null 2>&1; then
  ACCTS=$(sacctmgr -nP show assoc user="$USER" format=Account 2>/dev/null | sort -u | tr '\n' ' ')
  if [ -n "${ACCTS// /}" ]; then
    pass "accounts: $ACCTS"
    printf '  note     if more than one, the web app must pass --account explicitly\n'
  else
    warn "no accounts returned -- check with 'sacctmgr show assoc user=\$USER'"
  fi
else
  warn "sacctmgr not available"
fi

# ------------------------------------------------------------------ 4. Containers
# ASSUMPTION UNDER TEST: G-15 (module load singularity) and fakeroot build (Q4=A).
section "4. Container runtime"
if module spider singularity 2>&1 | grep -qi 'singularity'; then
  pass "singularity module found"
  module spider singularity 2>&1 | grep -iE '^\s*(singularity|Versions|\s+singularity/)' | head -8 | sed 's/^/    /'
else
  warn "'module spider singularity' found nothing -- try 'module spider apptainer' (CCEnv)"
fi
if module load singularity >/dev/null 2>&1 || module load apptainer >/dev/null 2>&1; then
  if command -v singularity >/dev/null 2>&1; then
    pass "singularity on PATH: $(singularity --version 2>&1)"
  elif command -v apptainer >/dev/null 2>&1; then
    pass "apptainer on PATH: $(apptainer --version 2>&1)"
  else
    fail "module loaded but no singularity/apptainer binary on PATH"
  fi
else
  warn "could not module load singularity or apptainer"
fi
if [ -f /proc/sys/user/max_user_namespaces ]; then
  NS=$(cat /proc/sys/user/max_user_namespaces 2>/dev/null || echo 0)
  if [ "${NS:-0}" -gt 0 ] 2>/dev/null; then
    pass "user namespaces enabled (max=$NS) -- --fakeroot builds plausible"
  else
    warn "user namespaces appear disabled -- --fakeroot may fail; fallback is Sylabs remote or local Docker"
  fi
fi

# --fakeroot remaps your UID to root inside a user namespace. On root_squashed
# network storage the server maps that back to `nobody`, which cannot traverse
# a 0700 home directory or read your files -- the build then dies with
# "permission denied" on the definition file. build-image.sh works around this
# by staging to node-local $TMPDIR; this check explains why that matters.
REPO=$(cd "$(dirname "$0")/.." && pwd)
REPO_FS=$(df -PTh "$REPO" 2>/dev/null | awk 'NR==2{print $2}')
HOME_MODE=$(stat -c '%a' "$HOME" 2>/dev/null || echo '?')
printf '  info     repo path: %s\n' "$REPO"
printf '  info     repo filesystem: %s   $HOME mode: %s\n' "${REPO_FS:-unknown}" "$HOME_MODE"
case "${REPO_FS:-}" in
  nfs*|lustre*|beegfs*|gpfs*|cifs*)
    if [ "$HOME_MODE" = "700" ] || [ "$HOME_MODE" = "750" ]; then
      warn "repo is on '$REPO_FS' and \$HOME is mode $HOME_MODE -- a direct --fakeroot build here
           WILL fail with 'permission denied' (root_squash). build-image.sh stages to \$TMPDIR
           automatically, so this is handled; do not build by hand from this path."
    else
      pass "repo on '$REPO_FS'; build-image.sh stages to \$TMPDIR regardless (root_squash safe)"
    fi
    ;;
  *) pass "repo filesystem '${REPO_FS:-unknown}' -- build staging to \$TMPDIR still applied" ;;
esac

# -------------------------------------------------------------------- 5. Storage
# ASSUMPTION UNDER TEST: ~15-25 GB baseline fits in the 100 GB /home quota (Q8).
section "5. Storage and quota"
printf '  df on \$HOME:\n'; df -h "$HOME" 2>/dev/null | sed 's/^/    /'
for q in "quota -s" "lfs quota -h $HOME" "check-quota" "diskusage_report"; do
  C=${q%% *}
  if command -v "$C" >/dev/null 2>&1; then
    printf '  %s:\n' "$q"; $q 2>&1 | head -12 | sed 's/^/    /'; break
  fi
done
# NOTE: df shows the shared filesystem, which is NOT the binding limit -- the per-user
# quota is. Parse the quota first and fall back to df only if quota is unavailable.
HEADROOM_GB=""
if command -v quota >/dev/null 2>&1; then
  # quota output rows look like:  <filesystem>  <used>  <soft>  <hard>  ...
  # with -s the sizes carry K/M/G/T suffixes; without it they are plain kilobytes.
  HEADROOM_GB=$(quota -s 2>/dev/null | awk '
    function gb(v,   n,s) {
      n = v; s = v
      gsub(/[^0-9.]/, "", n)
      if (s ~ /K$/)      return n / 1048576
      else if (s ~ /M$/) return n / 1024
      else if (s ~ /G$/) return n
      else if (s ~ /T$/) return n * 1024
      else               return n / 1048576   # bare number = kilobytes
    }
    $2 ~ /^[0-9.]+[KMGT]?\*?$/ && $3 ~ /^[0-9.]+[KMGT]?$/ {
      used = gb($2); soft = gb($3)
      if (soft > 0) { printf "%d", soft - used; exit }
    }')
fi
if [ -z "${HEADROOM_GB:-}" ]; then
  AVAIL_KB=$(df -Pk "$HOME" 2>/dev/null | awk 'NR==2{print $4}')
  [ -n "${AVAIL_KB:-}" ] && HEADROOM_GB=$((AVAIL_KB/1024/1024))
  [ -n "${HEADROOM_GB:-}" ] && printf '  note     no quota command; using df (may overstate your real limit)\n'
fi
if [ -n "${HEADROOM_GB:-}" ]; then
  if [ "$HEADROOM_GB" -ge 30 ] 2>/dev/null; then
    pass "~${HEADROOM_GB} GB quota headroom (need ~15-25 GB: weights + image + build cache)"
  elif [ "$HEADROOM_GB" -ge 15 ] 2>/dev/null; then
    warn "~${HEADROOM_GB} GB quota headroom -- tight. Consider --no-multimer, or RFD_OUTPUT_ROOT on /project"
  else
    fail "~${HEADROOM_GB} GB quota headroom -- not enough; move weights/outputs to /project"
  fi
fi
if [ -d /project ]; then
  pass "/project exists (fallback for weights and outputs)"
  ls -d /project/*"$USER"* 2>/dev/null | head -3 | sed 's/^/    /'
fi

# ------------------------------------------------------------------- 6. Egress
# ASSUMPTION UNDER TEST: weights and container layers are reachable from a login node.
section "6. Network egress from login node"
for url in \
  "https://files.ipd.uw.edu/" \
  "https://storage.googleapis.com/" \
  "https://registry-1.docker.io/v2/" \
  "https://files.rcsb.org/" \
  "https://alphafold.ebi.ac.uk/" \
  "https://pypi.org/simple/" ; do
  if curl -sS -o /dev/null -m 15 --retry 1 -w '%{http_code}' "$url" 2>/dev/null | grep -qE '^(2|3|4)'; then
    pass "reachable: $url"
  else
    fail "NOT reachable: $url -- weights or image layers cannot be fetched here"
  fi
done

# ---------------------------------------------------------------------- 7. uv
section "7. uv package manager"
if command -v uv >/dev/null 2>&1; then
  pass "uv present: $(uv --version 2>&1)"
else
  warn "uv not installed -- install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
fi

# ------------------------------------------------------------------ 8. GPU probe
section "8. GPU probe job (optional)"
if [ "$GPU_PROBE" -eq 1 ]; then
  PROBE=$(mktemp "${TMPDIR:-/tmp}/rfd-probe-XXXXXX.sh")
  cat > "$PROBE" <<'EOF'
#!/bin/bash
#SBATCH --job-name=rfd-preflight
#SBATCH --partition=gpu
#SBATCH --gpus=1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem-per-cpu=2000M
#SBATCH --time=0-00:05:00
cd ${SLURM_SUBMIT_DIR}
echo "Starting run at: `date`"
export SLURM_TMPDIR=$TMPDIR
echo "--- hostname:  `hostname`"
echo "--- TMPDIR:    ${TMPDIR:-UNSET}"
if [ -n "${TMPDIR:-}" ] && [ -d "$TMPDIR" ]; then
  echo "--- TMPDIR is a directory; free space:"
  df -h "$TMPDIR" | tail -1
  echo "test" > "$TMPDIR/probe.txt" && echo "--- TMPDIR is writable: YES"
else
  echo "--- TMPDIR MISSING -- this breaks the G-11 scratch design; tell Claude"
fi
echo "--- GPU:"
nvidia-smi --query-gpu=name,memory.total,compute_cap --format=csv
rc=$?
echo "Job finished with exit code $rc at: `date`"
exit $rc
EOF
  echo "  submitting 5-minute probe to the gpu partition..."
  sbatch "$PROBE" 2>&1 | sed 's/^/    /'
  echo "    watch with:  squeue -u $USER"
  echo "    output lands in slurm-<jobid>.out in $(pwd)"
else
  echo "  skipped -- rerun with --gpu-probe to submit a 5-minute job that checks"
  echo "  the GPU model, compute capability, and that \$TMPDIR exists and is writable."
fi

# --------------------------------------------------------------------- Summary
section "Summary"
printf '  PASS %d   WARN %d   FAIL %d\n\n' "$PASS" "$WARN" "$FAIL"
if [ "$FAIL" -gt 0 ]; then
  echo "  One or more checks FAILED. Report the output before building the image."
  exit 1
fi
echo "  Preflight clear. Next: scripts/build-image.sh (inside an salloc CPU job),"
echo "  then scripts/stage-weights.sh."
