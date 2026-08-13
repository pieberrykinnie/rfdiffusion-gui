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
| jaxlib (CUDA 11) | ~~`0.4.25+cuda11.cudnn86`~~ → **`0.4.7+cuda11.cudnn86`** (superseded 2026-08-06, see below) | enumerated `jax_cuda_releases.html` + JAX `CHANGELOG.md` |
| cuDNN supply | `nvidia-cudnn-cu11==8.6.0.163` | PyPI |

**Why `nvidia-cudnn-cu11` is pinned in**: jaxlib `cuda11.cudnn86` needs cuDNN ≥ 8.6, but the base
image ships the cuDNN 8.4-era runtime. Installing cuDNN as a pip package makes JAX independent of
whatever the base image carries — this removes the most likely cause of the §3 risk rather than
waiting to hit it. **Unaffected by the jaxlib downgrade below** — still cuDNN 8.6, still pip-supplied.

**§3 fallback tier 1 is now ACTIVE (2026-08-06)**, triggered by a real GPU allocation on Grex:
`jaxlib==0.4.25+cuda11.cudnn86` failed with `CUDA backend failed to initialize: Found CUDA version
11060, but JAX was built against version 11080, which is newer.` CUDA's forward-compat model requires
the installed runtime to be *at least as new* as the version jaxlib was built against, and this base
image's runtime is 11.6.2 — older than 11.8.

**Root-caused from JAX's own `CHANGELOG.md`, not guessed**: `jax 0.4.8` (2023-03-29) is the exact
release where "CUDA 11.4 support has been dropped. JAX GPU wheels only support CUDA 11.8 and CUDA
12." Every cuda11-tagged jaxlib from 0.4.8 onward — including 0.4.25 — is built against CUDA 11.8
regardless of its `cudnnXX` suffix. **`jaxlib 0.4.7` is the newest cuda11 build that predates this
bump**, confirmed against the full wheel index — this is the correct pin, not an arbitrary older one.

**Downgrading jax alone is not sufficient** — `chex==0.1.86` (pinned for jax 0.4.25) requires
`jax>=0.4.16`, which 0.4.7 violates. Checked chex's PyPI release history for exactly where that floor
was introduced: bumped to `jax>=0.4.16` in `chex 0.1.83` (2023-09-20); **`chex 0.1.82`**
(2023-07-20) is the newest release still requiring only `jax>=0.4.6`.

**First attempt at this fix was itself incomplete** — `optax==0.2.2` was initially left unchanged
after checking only its `jax` bound (`jax>=0.1.55`, fine). It also requires `chex>=0.1.86`
unconditionally, a direct conflict with `chex==0.1.82`, caught immediately by `uv`'s own resolver as
a loud build-time failure (`No solution found`) — exactly what the "one resolution pass" design
exists to do, and cheap: caught before staging, let alone before a GPU allocation. Re-checked and
fixed: **`optax==0.1.7`** (2023-07-26, contemporary with chex 0.1.82) requires only `chex>=0.1.5` and
`jax>=0.1.55`. Also checked `dm-haiku==0.0.12`'s **unconditional** `flax>=0.7.1` dependency this time
(not just its optional `[jax]` extra, which this install never requests) — `flax 0.7.1` requires only
`jax>=0.4.2`, so `dm-haiku==0.0.12` needs no version change.

**Verified pin set for jax 0.4.7**: `jax==0.4.7`, `jaxlib==0.4.7+cuda11.cudnn86`, `chex==0.1.82`,
`optax==0.1.7`, `dm-haiku==0.0.12` — applied in `containers/rfdiffusion.def`.

**Remaining fallback if this still fails**: two images (Q3 = B) — `colabdesign.sif` on a CUDA 12
base. The CUDA-11-only ceiling is now firmly established (0.4.7 is the newest option, full stop), so
this is the only tier left if 0.4.7 has some other incompatibility with ColabDesign at the pinned
commit.

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
- [x] **Corrected 2026-08-06** — `icecream` and `pyrsistent` added. Both are genuinely imported by
      the fork's inference path (base image never installs them) and were missing from the shipped
      image; see Step 9 in the code summary for the full defect and source-tree audit

### Step 3: Image build script
- [x] `scripts/build-image.sh` — `module load singularity`, explicit `APPTAINER_CACHEDIR` (G-18),
      `--fakeroot` build, refuse to run on a login node, documented fallback chain (G-16)

### Step 4: Weight staging script
- [x] `scripts/stage-weights.sh` — `curl` not `aria2c` (C-5), idempotent and resumable,
      structural integrity validation, `--no-multimer` option, manifest recording (NFR-5)

### Step 5: Image verification script
- [x] `scripts/verify-image.sh` — the 7-check list from `infrastructure-design.md` §9 as an
      executable script, ordered so the two approach-invalidating checks run first
- [x] **Corrected 2026-08-06** after its first real execution exposed two defects — see Step 9

### Step 6: Environment template
- [x] `env.example` — every configurable path with `/home` defaults (NFR-6)

### Step 7: Setup documentation
- [x] `docs/setup.md` — end-to-end: preflight, uv, image build, weight staging, verification,
      SSH `ControlMaster` tunnel, launch (FR-35, G-19, G-20)

### Step 8: Code summary
- [x] `aidlc-docs/construction/u1-runtime-container/code/u1-code-summary.md`

### Step 9: Verification-driven corrections to `verify-image.sh` (added 2026-08-06)

Added after the script's **first real execution** on Grex (`n339`, CPU node — see
`u1-code-summary.md` §Verification Results). Both defects were in the verification script, not in
the image. Neither is discoverable by `bash -n`, which is why they survived generation.

- [x] **Defect 1 — check 4 could not fail.** The GPU-device assertion grepped the *entire* captured
      output for `cuda\|gpu`, and the jaxlib version string is `0.4.25+cuda11.cudnn86`. The match
      landed on the version line, so the check reported `[ OK ] JAX imports and reports a GPU
      device` while `jax.devices()` returned `[CpuDevice(id=0)]`. It passed whenever the pin held —
      precisely when it needed to be able to fail. **Fixed**: scoped the grep to the `^devices`
      line. Verified against both real output shapes: `CpuDevice` → fail, `CudaDevice` → pass.
- [x] **Defect 2 — check 6 tripped a precondition the design had already written down.** The fork
      does `os.mkdir({SCRIPT_DIR}/../schedules)` **at import**, and that path is a symlink onto
      `/scratch`; `os.mkdir()` on a dangling symlink raises `FileExistsError`. The script created
      its scratch bind but never `schedules/` inside it, so every fork import failed. **Fixed**:
      `mkdir -p "$SCRATCH/schedules"`.
- [x] **Defect 2b — the failure was unreadable.** Check 6 discarded stderr on both branches
      (`2>/dev/null`), reporting only `cannot run or import RFdiffusion from the fork`. **Fixed**:
      capture and print stderr on failure.
- [x] `bash -n` clean; check-4 grep discrimination tested against both device outputs.

**Cross-unit consequence**: Defect 2 is the *first live confirmation* that U2b's documented
`mkdir -p /scratch/schedules` precondition is load-bearing rather than defensive. U1's own
verification script became the first consumer to violate it and failed exactly as predicted.

### Step 10: Image content defect — two missing pip packages (added 2026-08-06, second execution)

Re-running after Step 9's fixes surfaced a **third, genuine defect — this time in the image itself**,
via check 6's now-preserved stderr: `ModuleNotFoundError: No module named 'icecream'`.

- [x] Traced to source rather than patched blind. `reference/diffusion.py`'s commented-out cell 2
      installed `jedi omegaconf hydra-core icecream pyrsistent pynvml decorator` for Colab — a
      convenience cell covering everything the fork might need, onto a base with no pins of its own.
      `rfdiffusion.def` inherits the **RosettaCommons** image's install list, built for a codebase
      that imports none of these, so none shipped.
- [x] Downloaded the fork source at the pinned commit (`597d37f2…`) and read every import rather
      than adding the whole Colab cell defensively:
  - **`icecream` — required.** Imported unconditionally by `run_inference.py` (the entry point),
    `diff_util.py`, `contigs.py`, `potentials/manager.py`, `RoseTTAFoldModel.py`, `Embeddings.py`.
  - **`pyrsistent` — required.** `inference/symmetry.py` does `from pyrsistent import v` — this
    project's symmetry feature depends on it directly.
  - **`jedi` — not needed.** Zero references anywhere in the fork; Colab tab-completion only.
  - **`pynvml`, `decorator` — not needed for inference.** Real entries in
    `env/SE3Transformer/requirements.txt`, but that file is decorative: SE3Transformer's `setup.py`
    declares no `install_requires`. Both are imported only by
    `se3_transformer.runtime.{training,inference}` — NVIDIA's own training/benchmark harness.
    RFdiffusion imports only `se3_transformer.model` (`SE3_network.py`), never `.runtime`. Confirmed
    by grepping the full fork tree; adding them would be unused weight, not a fix.
- [x] Confirmed the *existing* check 6 already exercises both packages without modification: the
      import chain is `run_inference.py` → `inference.utils` → `inference.model_runners` →
      `inference.symmetry` → `pyrsistent`, all top-level imports, so fixing only `icecream` would
      have meant discovering `pyrsistent` missing on a **fourth** cluster round-trip. Caught here
      instead, at zero cluster cost.
- [x] `containers/rfdiffusion.def` — added `uv pip install --python "$VPY" --no-cache "icecream"
      "pyrsistent"` immediately after the fork's `dump_pdb` build-time assertion, with the full
      per-package audit recorded inline as a comment.

- [x] **Confirmed 2026-08-06, third execution**: rebuilt and re-verified on the same CPU node —
      **PASS 9 / FAIL 3**, check 6 fully passing, the 3 FAILs being exactly the predicted GPU-gated
      set (checks 1, 2, JAX device test). U1's CPU-verifiable surface is clean; only the GPU-gated
      checks remain.

### Step 11: §3 risk materialized on real GPU — jax/jaxlib/chex re-pinned (added 2026-08-06, first GPU execution)

The first GPU allocation reached exactly the risk `infrastructure-design.md` §3 named from the
start: `jaxlib==0.4.25+cuda11.cudnn86` failed with `CUDA backend failed to initialize: Found CUDA
version 11060, but JAX was built against version 11080, which is newer.`

- [x] Root-caused via JAX's own `CHANGELOG.md` rather than trial-and-error version bisection: `jax
      0.4.8` (2023-03-29) is the exact release that dropped CUDA 11.4 support and moved cuda11
      wheels to a CUDA 11.8 build baseline. Every cuda11 jaxlib from 0.4.8 onward — including
      0.4.25 — requires CUDA ≥ 11.8; this base image ships CUDA 11.6.2. **`jaxlib 0.4.7` is the
      newest cuda11 build that predates the bump** — confirmed against the full wheel index, not
      assumed from the pre-existing fallback-ladder text.
- [x] Checked whether downgrading jax alone is sufficient (it is not): queried PyPI's release
      history for `chex`, `optax`, `dm-haiku` — the exact extras pinned alongside jax 0.4.25 — for
      their declared jax lower bounds. `chex==0.1.86` requires `jax>=0.4.16`, which `jax==0.4.7`
      violates. `chex 0.1.82` (2023-07-20) is the newest chex release still requiring only
      `jax>=0.4.6`. `optax==0.2.2` and `dm-haiku==0.0.12` believed to need no change (see below —
      this was wrong for `optax`).
- [x] `containers/rfdiffusion.def` — the single resolution pass now installs `jax==0.4.7`,
      `jaxlib==0.4.7+cuda11.cudnn86`, `chex==0.1.82`, `optax==0.2.2`, `dm-haiku==0.0.12`. The
      pip-supplied cuDNN 8.6 is unchanged — that problem is orthogonal to the CUDA-version mismatch.
      `%labels` and the build-time guard's example text updated to match; the guard's comment now
      also notes explicitly what it does *not* catch (a CUDA build requiring a newer runtime than
      the base provides — only a real GPU run can catch that).
- [x] `bash -n` clean on the extracted `%post` block.

### Step 12: Build failure — the `optax` check was incomplete (added 2026-08-06, first build attempt with the re-pin)

Step 11's `optax==0.2.2 declares only jax>=0.1.55; no change needed` checked one dependency
direction only. The actual build failed immediately, at `uv`'s resolution step, before any staging:

```
x No solution found when resolving dependencies:
  `-> Because optax==0.2.2 depends on chex>=0.1.86 and you require chex==0.1.82, we can
      conclude that your requirements and optax==0.2.2 are incompatible.
```

- [x] `optax==0.2.2`'s **full** `requires_dist` (not just its `jax` line) declares `chex>=0.1.86`
      unconditionally — a direct conflict with the `chex==0.1.82` pin from Step 11. This is precisely
      the failure mode the "one resolution pass" design (§8.1e) exists to surface loudly, and it did
      — at build time, before staging, nowhere near a GPU allocation.
- [x] Checked optax's PyPI history for a version contemporary with `chex 0.1.82`: **`optax 0.1.7`**
      (2023-07-26) requires only `chex>=0.1.5` and `jax>=0.1.55` — both satisfied.
- [x] Learned from the miss and checked **all** transitive constraints this time, not just each
      package's direct `jax` line: `dm-haiku==0.0.12`'s *unconditional* `flax>=0.7.1` dependency
      (separate from its optional `[jax]` extra) was never checked in Step 11. `flax 0.7.1` requires
      only `jax>=0.4.2` — no conflict, `dm-haiku==0.0.12` genuinely needs no change. Also confirmed
      neither `chex 0.1.82` nor `optax 0.1.7` depends back on the other's replacement in a way that
      could reopen the conflict (`chex` has no `optax` reference at all; `optax`'s own dependents
      were re-checked against the final set).
- [x] `containers/rfdiffusion.def` — `optax==0.2.2` → `optax==0.1.7`. Comment rewritten to record
      the miss explicitly (why `jax`-only checking wasn't enough) rather than silently correcting it.

### Step 13: Rebuild and GPU re-verification — U1 fully verified (added 2026-08-07)

- [x] Rebuilt with the corrected pin set (`jax==0.4.7`, `jaxlib==0.4.7+cuda11.cudnn86`,
      `chex==0.1.82`, `optax==0.1.7`, `dm-haiku==0.0.12`) — resolution succeeded, no further
      transitive conflicts.
- [x] Re-verified on a real GPU allocation (`agpu` partition, NVIDIA A30, sm_80) —
      **PASS 13 / FAIL 0**. Every check passes, including the two that could have invalidated the
      approach: check 3 (sokrypton fork, `dump_pdb` present — FR-16/FR-17 achievable) and check 4
      (JAX imports and reports a real GPU device — `jax 0.4.7` / `jaxlib 0.4.7+cuda11.cudnn86` /
      `StreamExecutorGpuDevice`). The §3 risk is now closed: the CUDA-11 ceiling fix works.
- [x] Only non-`OK` line is the pre-known `ananas` `WARN` (symmetry="auto" unavailable — documented,
      non-fatal, from the upstream `files.ipd.uw.edu` 404, unrelated to this defect chain).

**U1 is fully verified. No further action needed on this unit.**

---

## Out of Scope for U1

- The `#SBATCH` generator (U3 renders the template programmatically)
- Any Python package (U2a, U2b, U3, U4)
- Actually building the image or staging weights — those are **user-executed**, and they are exactly
  the long-running steps the execution plan overlaps with U2a
