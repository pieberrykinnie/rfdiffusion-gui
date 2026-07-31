#!/bin/bash
# Stage RFdiffusion + AlphaFold model weights and the AnAnaS binary.
#
#   bash scripts/stage-weights.sh [--no-multimer] [--force]
#
# Run ONCE on a login node before the first job. Roughly 8 GB (about 4 GB with
# --no-multimer). Safe to interrupt and rerun -- downloads resume and completed
# assets are skipped.
#
# Uses curl, never aria2c: aria2 needs apt-get and there is no root on Grex.

set -euo pipefail

cd "$(dirname "$0")/.."
ROOT=$(pwd)
[ -f "${ROOT}/.env" ] && . "${ROOT}/.env"

RFD_WEIGHTS=${RFD_WEIGHTS:-$HOME/rfd-weights}
MULTIMER=1
FORCE=0
for a in "$@"; do
  case "$a" in
    --no-multimer) MULTIMER=0 ;;
    --force)       FORCE=1 ;;
    *) printf 'unknown option: %s\n' "$a" >&2; exit 2 ;;
  esac
done

MODELS="${RFD_WEIGHTS}/rfdiffusion"
AFDIR="${RFD_WEIGHTS}/alphafold"
BINDIR="${RFD_WEIGHTS}/bin"
MANIFEST="${RFD_WEIGHTS}/manifest.txt"

mkdir -p "$MODELS" "$AFDIR" "$BINDIR"

say()  { printf '\n>>> %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }
die()  { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

# Resumable download. curl -C - continues a partial file; --fail turns an HTTP
# error into a non-zero exit instead of a saved error page.
fetch() {
  url=$1; dest=$2
  if [ -s "$dest" ] && [ "$FORCE" -eq 0 ] && grep -qxF "$(basename "$dest")" "$MANIFEST" 2>/dev/null; then
    info "skip (already staged): $(basename "$dest")"
    return 0
  fi
  info "fetching $(basename "$dest")"
  curl -L --fail --retry 5 --retry-delay 5 -C - -o "$dest" "$url" \
    || die "download failed: $url"
}

# Structural validation. We deliberately do NOT ship hardcoded checksums --
# fabricating hashes we have not verified would be worse than useless. Instead
# each format is asked to validate itself, which reliably catches the failure
# that actually happens here: a truncated download.
record() { basename "$1" >> "$MANIFEST"; sort -u -o "$MANIFEST" "$MANIFEST"; }

check_torch_ckpt() {
  f=$1
  [ -s "$f" ] || die "empty: $f"
  # torch checkpoints are ZIP archives (PK magic) in modern formats.
  head -c 2 "$f" | grep -q 'PK' || die "not a valid torch checkpoint (truncated?): $f"
  sz=$(stat -c%s "$f" 2>/dev/null || stat -f%z "$f")
  [ "$sz" -gt 100000000 ] || die "suspiciously small ($sz bytes), likely truncated: $f"
  info "ok: $(basename "$f") ($((sz/1024/1024)) MB)"
  record "$f"
}

# ---------------------------------------------------------------- RFdiffusion
say "RFdiffusion checkpoints -> $MODELS"
IPD=http://files.ipd.uw.edu/pub/RFdiffusion
fetch "$IPD/6f5902ac237024bdd0c176cb93063dc4/Base_ckpt.pt"         "$MODELS/Base_ckpt.pt"
check_torch_ckpt "$MODELS/Base_ckpt.pt"
fetch "$IPD/e29311f6f1bf1af907f9ef9f44b8328b/Complex_base_ckpt.pt" "$MODELS/Complex_base_ckpt.pt"
check_torch_ckpt "$MODELS/Complex_base_ckpt.pt"
fetch "$IPD/f572d396fae9206628714fb2ce00f72e/Complex_beta_ckpt.pt" "$MODELS/Complex_beta_ckpt.pt"
check_torch_ckpt "$MODELS/Complex_beta_ckpt.pt"

# ------------------------------------------------------------------ schedules
say "Diffusion schedules"
if [ ! -d "$MODELS/schedules" ] || [ "$FORCE" -eq 1 ]; then
  fetch "https://files.ipd.uw.edu/krypton/schedules.zip" "$MODELS/schedules.zip"
  unzip -tq "$MODELS/schedules.zip" || die "schedules.zip is corrupt (truncated?)"
  rm -rf "$MODELS/schedules"
  mkdir -p "$MODELS/schedules"
  unzip -oq "$MODELS/schedules.zip" -d "$MODELS/schedules"
  rm -f "$MODELS/schedules.zip"
  info "ok: schedules extracted"
else
  info "skip (already staged): schedules"
fi

# --------------------------------------------------------------------- ananas
say "AnAnaS symmetry detector"
if [ ! -x "$BINDIR/ananas" ] || [ "$FORCE" -eq 1 ]; then
  fetch "https://files.ipd.uw.edu/krypton/ananas" "$BINDIR/ananas"
  chmod +x "$BINDIR/ananas"
  # Verify it actually runs here (glibc compatibility is not guaranteed for a
  # precompiled binary). symmetry="auto" is the only feature that needs it, so
  # a failure must degrade gracefully rather than surprise a user mid-run.
  # AnAnaS exits non-zero when invoked with no real input, so we only care that
  # it executed at all -- exit code 126/127 means it could not.
  set +e
  "$BINDIR/ananas" --help >/dev/null 2>&1
  rc=$?
  set -e
  if [ "$rc" -lt 126 ]; then
    info "ok: ananas executed (exit $rc)"
  else
    printf '    WARNING: ananas could not execute here (exit %s).\n' "$rc"
    printf '             symmetry="auto" will be unavailable; all other modes are unaffected.\n'
  fi
  record "$BINDIR/ananas"
else
  info "skip (already staged): ananas"
fi

# ------------------------------------------------------------------ AlphaFold
say "AlphaFold parameters -> $AFDIR"
if [ ! -f "$AFDIR/params_model_1_ptm.npz" ] || [ "$FORCE" -eq 1 ]; then
  TAR="$AFDIR/alphafold_params_2022-12-06.tar"
  fetch "https://storage.googleapis.com/alphafold/alphafold_params_2022-12-06.tar" "$TAR"
  tar -tf "$TAR" >/dev/null || die "AlphaFold params tar is corrupt (truncated?)"
  if [ "$MULTIMER" -eq 1 ]; then
    info "extracting all parameters (monomer + multimer)"
    tar -xf "$TAR" -C "$AFDIR"
  else
    info "extracting monomer parameters only (--no-multimer)"
    # use_multimer defaults off; skipping these saves several GB of quota.
    tar -xf "$TAR" -C "$AFDIR" --wildcards --exclude='*multimer*'
  fi
  rm -f "$TAR"
  info "ok: AlphaFold parameters extracted"
  record "$AFDIR/params_model_1_ptm.npz"
else
  info "skip (already staged): AlphaFold parameters"
fi

# -------------------------------------------------------------------- summary
say "Staging complete"
du -sh "$RFD_WEIGHTS" 2>/dev/null | sed 's/^/    total: /'
if command -v quota >/dev/null 2>&1; then
  printf '\n    Quota after staging:\n'
  quota -s 2>/dev/null | sed 's/^/      /' || true
fi

cat <<EOF

Weights staged at: $RFD_WEIGHTS
  rfdiffusion/   3 checkpoints + schedules/
  alphafold/     parameters$([ "$MULTIMER" -eq 0 ] && echo ' (monomer only)')
  bin/ananas     symmetry detector

Set RFD_WEIGHTS=$RFD_WEIGHTS in your .env if you used a non-default location.
Next: verify on a GPU node with scripts/verify-image.sh
EOF
