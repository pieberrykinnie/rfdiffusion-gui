#!/bin/bash
# Prepares one run directory + run.json for Milestone M1: a real, minimal
# RFdiffusion design run driven by hand (no rfd-web, no SlurmAdapter -- those
# are U3/U4). This is the first time U1 (container) + U2a (rfd-core contracts)
# + U2b (rfd-runner) run together end to end.
#
# Run on a Grex LOGIN NODE:
#
#   bash scripts/m1-prepare-run.sh
#
# Prints the created run_dir. Pass it to scripts/m1-submit.sh via sbatch.
#
# The design itself is a minimal de novo (FREE-mode) monomer smoke test --
# contigs="80" has no chain token and one free segment, so rfd_core.modes
# infers DesignMode.FREE and no template PDB is needed. Small enough to
# finish well inside the 30-minute walltime below while still exercising the
# full pipeline (backbone + ProteinMPNN/AlphaFold validation, --stage all).

set -euo pipefail

cd "$(dirname "$0")/.."
ROOT=$(pwd)
[ -f "${ROOT}/env.example" ] && [ -f "${ROOT}/.env" ] && . "${ROOT}/.env"

RFD_OUTPUT_ROOT=${RFD_OUTPUT_ROOT:-$HOME/rfd-runs}

RUN_ID="m1-smoke-$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="${RFD_OUTPUT_ROOT}/${RUN_ID}"
mkdir -p "$RUN_DIR"

CREATED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# Minimal RunRecord (rfd_core.models.RunRecord / DesignRequest). Only the
# fields with no default are included; everything else (symmetry=none,
# num_seqs=8, mem_per_cpu=6000M, ...) comes from the pydantic model's own
# defaults on load, matching packages/rfd-core/src/rfd_core/models.py.
cat > "${RUN_DIR}/run.json" <<JSON
{
  "schema_version": 1,
  "run_id": "${RUN_ID}",
  "name": "m1smoke",
  "run_dir": "${RUN_DIR}",
  "created_at": "${CREATED_AT}",
  "request": {
    "name": "m1smoke",
    "contigs": "80",
    "iterations": 50,
    "num_designs": 1,
    "symmetry": "none",
    "live_preview": true,
    "partition": "gpu",
    "walltime": "0-00:30:00",
    "gpus": 1,
    "cpus_per_task": 6,
    "mem_per_cpu": "6000M"
  }
}
JSON

echo "Prepared: ${RUN_DIR}/run.json"
echo
echo "Next:"
echo "  sbatch scripts/m1-submit.sh \"${RUN_DIR}\""
