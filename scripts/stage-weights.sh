#!/bin/bash
# Stage AlphaFold parameters (required) and the AnAnaS binary (optional).
#
#   bash scripts/stage-weights.sh [--no-multimer] [--force]
#
# Run ONCE on a login node before the first job. Roughly 4 GB (a few MB with
# --no-multimer). Safe to interrupt and rerun -- downloads resume and completed
# assets are skipped.
#
# NOT staged here:
#   * RFdiffusion checkpoints -- the published rosettacommons/rfdiffusion image
#     bakes in all nine, including the three this project uses. The image
#     symlinks them to /opt/RFdiffusion/models. (~4 GB saved.)
#   * Diffusion schedules -- computed on demand by the Diffuser and cached in
#     writable scratch. The notebook's schedules.zip URL is dead (404).
#
# Uses curl, never aria2c: aria2 needs apt-get and there is no root on Grex.

set -euo pipefail

cd "$(dirname "$0")/.."
ROOT=$(pwd)
[ -f "${ROOT}/.env" ] && . "${ROOT}/.env"

RFD_WEIGHTS=${RFD_WEIGHTS:-$HOME/rfd-weights}
MULTIMER=1
ANANAS_OK=0
FORCE=0
for a in "$@"; do
  case "$a" in
    --no-multimer) MULTIMER=0 ;;
    --force)       FORCE=1 ;;
    *) printf 'unknown option: %s\n' "$a" >&2; exit 2 ;;
  esac
done

AFDIR="${RFD_WEIGHTS}/alphafold"
BINDIR="${RFD_WEIGHTS}/bin"
MANIFEST="${RFD_WEIGHTS}/manifest.txt"

mkdir -p "$AFDIR" "$BINDIR"

say()  { printf '\n>>> %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }
die()  { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

# Resumable download. curl -C - continues a partial file; --fail turns an HTTP
# error into a non-zero exit instead of a saved error page.
# Returns non-zero on failure; the caller decides whether that is fatal.
fetch() {
  url=$1; dest=$2
  if [ -s "$dest" ] && [ "$FORCE" -eq 0 ] && grep -qxF "$(basename "$dest")" "$MANIFEST" 2>/dev/null; then
    info "skip (already staged): $(basename "$dest")"
    return 0
  fi
  info "fetching $(basename "$dest")"
  set +e
  curl -L --fail --retry 5 --retry-delay 5 -C - -o "$dest" "$url"
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    rm -f "$dest"          # do not leave a truncated or error-page file behind
    return "$rc"
  fi
}

fetch_or_die() { fetch "$1" "$2" || die "download failed: $1"; }

# Structural validation. We deliberately do NOT ship hardcoded checksums --
# fabricating hashes we have not verified would be worse than useless. Instead
# each format is asked to validate itself, which reliably catches the failure
# that actually happens here: a truncated download.
record() { basename "$1" >> "$MANIFEST"; sort -u -o "$MANIFEST" "$MANIFEST"; }

# ----------------------------------------------------- checkpoints / schedules
say "RFdiffusion checkpoints and schedules"
info "skipped -- both are baked into the container image"
info "  checkpoints: /opt/RFdiffusion/models (symlink to /app/RFdiffusion/models)"
info "  schedules:   generated on demand into writable scratch"

# --------------------------------------------------------------------- ananas
# OPTIONAL. AnAnaS powers symmetry="auto" only; every other symmetry mode
# (none / cyclic / dihedral with an explicit order) works without it.
#
# The URL the notebook used -- files.ipd.uw.edu/krypton/ananas -- now returns
# 404; the whole /krypton/ directory has been removed upstream (verified
# 2026-08-01, same cause as the dead schedules.zip). So this download is
# best-effort and NEVER fatal.
#
# To supply it yourself: set RFD_ANANAS_URL, or drop the binary at
# $RFD_WEIGHTS/bin/ananas and chmod +x it. Source:
#   https://team.inria.fr/nano-d/software/ananas/
ANANAS_URL=${RFD_ANANAS_URL:-https://files.ipd.uw.edu/krypton/ananas}
say "AnAnaS symmetry detector (optional)"
if [ ! -x "$BINDIR/ananas" ] || [ "$FORCE" -eq 1 ]; then
  if ! fetch "$ANANAS_URL" "$BINDIR/ananas"; then
    printf '    NOT AVAILABLE: %s\n' "$ANANAS_URL"
    printf '    This is expected -- the upstream /krypton/ directory was removed.\n'
    printf '\n'
    printf '    Consequence: symmetry="auto" will be UNAVAILABLE.\n'
    printf '    Everything else is unaffected: symmetry none / cyclic / dihedral all\n'
    printf '    work, you just have to state the symmetry group and order explicitly\n'
    printf '    rather than having it detected from the template.\n'
    printf '\n'
    printf '    To enable auto-detection later, obtain the binary from\n'
    printf '      https://team.inria.fr/nano-d/software/ananas/\n'
    printf '    and either place it at %s (chmod +x)\n' "$BINDIR/ananas"
    printf '    or rerun with RFD_ANANAS_URL=<url>.\n'
    ANANAS_OK=0
  else
    chmod +x "$BINDIR/ananas"
    # Verify it actually runs here -- glibc compatibility is not guaranteed for
    # a precompiled binary. AnAnaS exits non-zero when given no real input, so
    # we only care that it executed at all; 126/127 mean it could not.
    set +e
    "$BINDIR/ananas" --help >/dev/null 2>&1
    rc=$?
    set -e
    if [ "$rc" -lt 126 ]; then
      info "ok: ananas executed (exit $rc) -- symmetry=\"auto\" available"
      ANANAS_OK=1
    else
      printf '    WARNING: ananas could not execute here (exit %s).\n' "$rc"
      printf '             symmetry="auto" unavailable; all other modes unaffected.\n'
      ANANAS_OK=0
    fi
    record "$BINDIR/ananas"
  fi
else
  info "skip (already staged): ananas"
  ANANAS_OK=1
fi

# ------------------------------------------------------------------ AlphaFold
say "AlphaFold parameters -> $AFDIR"
if [ ! -f "$AFDIR/params_model_1_ptm.npz" ] || [ "$FORCE" -eq 1 ]; then
  TAR="$AFDIR/alphafold_params_2022-12-06.tar"
  fetch_or_die "https://storage.googleapis.com/alphafold/alphafold_params_2022-12-06.tar" "$TAR"
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

Staged at: $RFD_WEIGHTS
  alphafold/     parameters$([ "$MULTIMER" -eq 0 ] && echo ' (monomer only)')
  bin/ananas     $([ "${ANANAS_OK:-0}" -eq 1 ] && echo 'symmetry detector (symmetry="auto" available)' || echo 'NOT AVAILABLE -- symmetry="auto" disabled, all other modes fine')

RFdiffusion checkpoints and diffusion schedules are in the container image;
nothing to stage for those.

Set RFD_WEIGHTS=$RFD_WEIGHTS in your .env if you used a non-default location.
Next: verify on a GPU node with scripts/verify-image.sh
EOF
