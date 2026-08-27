# Milestone M1 — Working CLI Pipeline Verification

> **STATUS: ✅ PASSED 2026-08-27** — job 7556085, node `g325`, real Tesla V100-SXM2-32GB,
> elapsed 00:01:27. All 5 exit criteria met: `backbone_state` and `validate_state` both
> `completed`, `error: null`, `sacct` `COMPLETED` / `0:0`, and the full output set
> (`m1smoke_0.pdb`, `traj/`, `m1smoke/best.pdb`, `m1smoke/best_design.pdb`,
> `m1smoke.result.zip`). Took eight executions and seven distinct root causes; see
> `aidlc-docs/aidlc-state.md` and `aidlc-docs/audit.md` for the chain. The instructions below
> remain valid for re-running the smoke test.

**What this is**: the first time U1 (container), U2a (`rfd-core`), and U2b (`rfd-runner`) run
together, on a real Grex GPU node, with no web app in the loop. Per
`aidlc-docs/inception/application-design/unit-of-work.md`, this milestone gates all further work
on U3/U4 — it exists specifically to catch problems in the GPU stack, the container, the Grex job
script, or the scientific pipeline with four components in play instead of eight.

This must be run by hand, from a Grex login node. It cannot be executed from this development
environment — no SSH/MFA session to Grex, no GPU, no Slurm.

## Prerequisites

Already satisfied as of 2026-08-07 (see `aidlc-docs/aidlc-state.md`):
- Image built: `$RFD_IMAGE` (default `~/rfd-images/rfdiffusion.sif`)
- Weights staged: `scripts/stage-weights.sh` has been run (`$RFD_WEIGHTS`, default `~/rfd-weights`)
- `.env` configured from `env.example` if any path differs from the defaults

If starting from a fresh Grex checkout, run `scripts/preflight-grex.sh` first.

## Steps

Run from the repo root on a **Grex login node** (`yak` or `bison`):

```bash
# 1. Create a run directory + run.json for a minimal smoke-test design
bash scripts/m1-prepare-run.sh
# -> prints RUN_DIR, e.g. ~/rfd-runs/m1-smoke-20260813T190000Z

# 2. Submit the hand-written job script
sbatch scripts/m1-submit.sh "<RUN_DIR from step 1>"

# 3. Watch it
squeue -u $USER
tail -f <RUN_DIR>/../rfd-m1-smoke-<jobid>.out   # job stdout, written to the submit dir
```

The smoke-test design is intentionally small: `contigs="80"` (an 80-residue de novo monomer,
`DesignMode.FREE` — no template PDB, no symmetry, no hotspot), 50 diffusion steps, 1 design,
`--stage all` (backbone generation **and** ProteinMPNN/AlphaFold validation). It should finish
in a few minutes on a V100 or A30; the job requests a 30-minute walltime.

## Exit criteria (unit-of-work.md)

| # | Criterion | How to check |
|---|---|---|
| 1 | Container runs `run_inference.py` on a Grex GPU node | Job stdout shows RFdiffusion's own step logging, not an import error |
| 2 | A real design completes via `sbatch` with a hand-written script | `sacct -j <jobid>` shows `COMPLETED`; exit code 0 |
| 3 | The job script passes review against the Grex docs (G-1…G-18) | See conformance table below |
| 4 | `run.json`, `progress.json`, and `current_frame.pdb` are all written as specified | Check `<RUN_DIR>` after submission (see below) |
| 5 | `rfd-core`'s test suite passes independently | Already true — 157 tests, 100% coverage, verified 2026-08-01 (`aidlc-docs/construction/u2a-core-domain/code/u2a-code-summary.md`) |

**Checking criterion 4**, once the job is running:
```bash
cat <RUN_DIR>/run.json          # backbone_state should move pending -> running -> completed
cat <RUN_DIR>/progress.json     # step counter advancing, updated_at recent
ls <RUN_DIR>/current_frame.pdb  # published every RFD_FRAME_EVERY_N steps (default 5)
```
On success, `<RUN_DIR>` should also contain `m1smoke_0.pdb` (backbone), `traj/` (trajectories),
`m1smoke/best.pdb` and `m1smoke/best_design.pdb` (validation outputs), and a result `.zip`.

## `scripts/m1-submit.sh` conformance against Grex documentation (G-1…G-18)

| Rule | Satisfied by |
|---|---|
| G-1 shape | shebang, `#SBATCH` block, `cd ${SLURM_SUBMIT_DIR}`, start/finish echo with `date` and exit code |
| G-2 retained and resubmittable | the script itself lives in the repo (`scripts/m1-submit.sh`), not a throwaway; re-runnable against a fresh `run_dir` |
| G-3 no `--qos=` | never emitted; comment records why |
| G-4 explicit time and memory | `--time=0-00:30:00`, `--mem-per-cpu=6000M` |
| G-5 GPUs requested | `--gpus=1` |
| G-6 explicit partition | `--partition=gpu` |
| G-7 one GPU default | matches Grex's own GPU guidance |
| G-8 6 CPUs / 6 GB per CPU | `--cpus-per-task=6`, `--mem-per-cpu=6000M` |
| G-11 `$TMPDIR` scratch | bound to `/scratch` inside the container |
| G-12 `SLURM_TMPDIR` | `export SLURM_TMPDIR=$TMPDIR` |
| G-13 stage out | `ResultPackager.stage_out` runs before the process exits; `$TMPDIR` is discarded by Slurm at job end |
| G-15 module | `module load singularity` (falls back to `apptainer`), then the engine binary is detected off `PATH` — Grex's module gives `singularity`, CCEnv gives `apptainer` |
| G-16 image pre-built | `$RFD_IMAGE` staged ahead of time by `scripts/build-image.sh`; never built or pulled at job start |
| G-17 `--nv` | present on `$ENGINE exec` |
| G-18 cache dir | both `APPTAINER_CACHEDIR` and `SINGULARITY_CACHEDIR` set explicitly |

## Known scope limits of this smoke test

This exercises the `DesignMode.FREE` path only. It deliberately does **not** exercise:
- Template resolution (`FIXED`/`PARTIAL` modes, `TemplateResolver`) — needs a real PDB input
- `SymmetryDetector` / AnAnaS (`symmetry=auto`) — `ananas` availability is a separate, already-known
  open item (see `aidlc-docs/aidlc-state.md`, "Upstream Bit-Rot")
- `--stage backbone` / `--stage validate` used independently (only `--stage all` is run here)

If M1 passes, these remain worth a manual spot-check before U4 exposes them through the web form,
but they are not blocking for the M1 gate itself, which unit-of-work.md scopes to proving the
container + GPU + Slurm + core pipeline work together at all.

## If it fails

Record the failure the same way every other real-hardware finding in this project has been
recorded (see `aidlc-docs/audit.md` for the pattern): paste the exact `sacct`/job-log output back,
root-cause from primary sources rather than guessing, fix, and re-run — don't patch symptoms.
