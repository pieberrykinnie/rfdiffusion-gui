# U1 Runtime and Container — Code Generation Plan

**Unit**: U1 Runtime and Container
**Stage**: CONSTRUCTION — Code Generation
**Date**: 2026-07-31
**Workspace root**: `/home/pieberrykinnie/rfdiffusion-gui`

> This plan is the **single source of truth** for U1 code generation.

---

## Unit Context

**Requirements owned** (from `unit-of-work-story-map.md`): FR-10, FR-35, NFR-4, NFR-5,
G-15, G-16, G-17, G-18, G-19, G-20; contributes to FR-13, G-1, G-11, G-12.

**Dependencies**: none. U1 is the root of the dependency graph.

**Consumed by**: U2b (executes inside the image), U3 (fills in the job-script template).

**Interfaces produced**:
- Container image at `$RFD_IMAGE` with `PYTHONPATH` pre-wired for bind-mounted source
- Bind-mount contract: `/opt/rfdgui`, `/opt/weights`, `/opt/outputs`, `/scratch`
- Weight layout under `$RFD_WEIGHTS`
- `#SBATCH` template (spec in `deployment-architecture.md` §3; U3 renders it programmatically)

**No Python package.** U1 produces container definitions, shell scripts, and documentation.

---

## Verified Pins (research completed before generation)

| Item | Pin | How verified |
|---|---|---|
| Base image | `rosettacommons/rfdiffusion` | Docker Hub; Dockerfile read |
| CUDA / cuDNN / Python | 11.6.2 / 8 / 3.9 | base Dockerfile |
| torch / DGL / e3nn / hydra | `1.12.1+cu116` / `1.0.2+cu116` / `0.3.3` / `1.3.2` | base Dockerfile |
| `sokrypton/RFdiffusion` | **`597d37f2a686e23941440fddf6daa4cb778e7bc7`** | GitHub API, 2025-10-23 |
| `sokrypton/ColabDesign` | **`e31a56fe1d9b4de25c8697f3a28b75892941cc72`** | GitHub API, 2025-10-23 |
| jaxlib (CUDA 11) | **`0.4.25+cuda11.cudnn86`** — newest cuda11 build with cp39 wheels | enumerated `jax_cuda_releases.html` |
| cuDNN supply | `nvidia-cudnn-cu11==8.6.0.163` | PyPI |

**Why `nvidia-cudnn-cu11` is pinned in**: jaxlib `cuda11.cudnn86` needs cuDNN ≥ 8.6, but the base
image ships the cuDNN 8.4-era runtime. Installing cuDNN as a pip package makes JAX independent of
whatever the base image carries — this removes the most likely cause of the §3 risk rather than
waiting to hit it.

**Fallback ladder if JAX still fails** (verified to exist, no re-decision needed):
1. `jaxlib==0.4.7+cuda11.cudnn82` — matches the base image's cuDNN directly; much older, so
   ColabDesign may not support it
2. Two images (Q3 = B) — `colabdesign.sif` on a CUDA 12 base

---

## Steps

### Step 1: Repository structure setup
- [x] Create `containers/`, `scripts/`, `docs/`, `reference/`
- [x] Move `diffusion.py` → `reference/diffusion.py` via `git mv`, **unmodified** (DD-5)
- [x] Add `reference/README.md` explaining provenance and its role as rollback fallback
- [x] Add `.gitignore` for images, weights, run outputs, caches, venvs

### Step 2: Apptainer definition
- [x] `containers/rfdiffusion.def` — `FROM rosettacommons/rfdiffusion`, overlay sokrypton fork at
      pinned SHA, ColabDesign at pinned SHA, JAX + cuDNN pins, `%environment` with `DGLBACKEND`,
      `PYTHONPATH`, and weight paths (NFR-4, G-17)

### Step 3: Image build script
- [x] `scripts/build-image.sh` — `module load singularity`, explicit `APPTAINER_CACHEDIR` (G-18),
      `--fakeroot` build, refuse to run on a login node, documented fallback chain (G-16)

### Step 4: Weight staging script
- [x] `scripts/stage-weights.sh` — `curl` not `aria2c` (C-5), idempotent and resumable,
      structural integrity validation, `--no-multimer` option, manifest recording (NFR-5)

### Step 5: Image verification script
- [x] `scripts/verify-image.sh` — the 7-check list from `infrastructure-design.md` §9 as an
      executable script, ordered so the two approach-invalidating checks run first

### Step 6: Environment template
- [x] `env.example` — every configurable path with `/home` defaults (NFR-6)

### Step 7: Setup documentation
- [x] `docs/setup.md` — end-to-end: preflight, uv, image build, weight staging, verification,
      SSH `ControlMaster` tunnel, launch (FR-35, G-19, G-20)

### Step 8: Code summary
- [x] `aidlc-docs/construction/u1-runtime-container/code/u1-code-summary.md`

---

## Out of Scope for U1

- The `#SBATCH` generator (U3 renders the template programmatically)
- Any Python package (U2a, U2b, U3, U4)
- Actually building the image or staging weights — those are **user-executed**, and they are exactly
  the long-running steps the execution plan overlaps with U2a
