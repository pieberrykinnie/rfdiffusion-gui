# U1 Runtime and Container — Infrastructure Design

**Unit**: U1 Runtime and Container
**Date**: 2026-07-31
**Decisions**: Q1 = D · Q2 = A · Q3 = A · Q4 = A
**Preflight**: verified on `yak` 2026-07-31 — 16 PASS, 0 WARN, 0 FAIL

---

## 0. Preflight Findings (verified on the real cluster)

`scripts/preflight-grex.sh` was run on a Grex login node. All checks passed, and four results
**change or strengthen this design**. Verified facts supersede the documentation-derived assumptions
recorded earlier.

### 0.1 ✅ Phase 1 is **not V100-only** — it covers 5 of 6 GPU partition families

The real partition table includes **A30 partitions the documentation never mentioned**:

| Partition | GPU | Compute cap. | GPUs | Walltime | CUDA 11.6? |
|---|---|---|---|---|---|
| `gpu` | V100 ×4 / 2 nodes | sm_70 | 8 | 7 d | ✅ |
| `stamps` / `stamps-b` | V100 ×4 / 3 nodes | sm_70 | 12 | 21 d / 7 d | ✅ |
| `livi` / `livi-b` | V100 ×16 / 1 node | sm_70 | 16 | 21 d / 7 d | ✅ |
| `agpu` | **A30** ×2 / 2 nodes | **sm_80** | 4 | 7 d | ✅ |
| `mcordgpu` / `mcordgpu-b` | **A30** ×4 / 2 nodes | **sm_80** | 8 | 21 d / 7 d | ✅ |
| `lgpu` | L40s ×2 / 2 nodes | sm_89 | 4 | **3 d** | ❌ |

**A30 is Ampere (sm_80), which CUDA 11.6 fully supports** — sm_80 arrived in CUDA 11.0.
`torch 1.12.1+cu116` ships an arch list covering sm_37 … sm_86.

So the Phase 1 image runs on **`gpu`, `stamps-b`, `livi-b`, `agpu`, and `mcordgpu-b`** —
**36 V100s + 12 A30s**. Only `lgpu` (L40s, sm_89) is excluded.

This substantially strengthens Q1 = D and **reduces the value of Phase 2** to "access L40s
specifically", rather than "access most of the cluster's GPUs". `-b` partitions are preemptible and
open to non-owners with a 1-hour minimum runtime guarantee, so a `def-` account reaches them.

**Design change**: `RFD_DEFAULT_PARTITION` stays `gpu`, but the partition selector must offer the
full CUDA-11.6-compatible set and **mark `lgpu` as incompatible with the Phase 1 image**. Recorded as
a U3 requirement.

### 0.2 ⚠️ `lgpu` walltime is **3 days**, not 7

Contradicts the batch-jobs page, which lists 7 days for GPU partitions generally. Walltime validation
must be **per-partition**, read from `sinfo`, not a single constant. Reinforces FR-6a.

### 0.3 ⚠️ Login-node `python3` is **3.6.8**

Far too old for FastAPI. **`uv` 0.12.0 is present**, so `rfd-web` must use a **uv-managed standalone
Python**, never the system interpreter. Concretely: `requires-python = ">=3.11"` in `rfd-web`, and
setup docs use `uv sync` / `uv run` (which download a suitable Python automatically) rather than
`python3 -m venv`.

This does **not** relax the Python 3.9 constraint on `rfd-core` — that comes from the *container*
(§4), and both constraints hold simultaneously:

| Package | Runs where | Python |
|---|---|---|
| `rfd-core` | container **and** login node | **3.9-compatible source** |
| `rfd-runner` | container | 3.9 |
| `rfd-web` | login node, uv-managed | ≥3.11 |

### 0.4 ✅ Everything else confirmed

- **Account**: `def-cardona` (single, so `--account` can default; no RAC ⇒ 400 CPU-cores/group cap
  and preemptible partitions available)
- **Container runtime**: `singularity-ce 4.4.1`, modules 4.2.2 / 4.3.6 / 4.4.1
- **`--fakeroot`**: user namespaces enabled (`max_user_namespaces=1500`) — Q4 = A is viable
- **Quota**: **100 GB soft / 105 GB hard**, 54 MB used. The ~15–25 GB baseline fits comfortably.
  (Note: `df` reports 4.2 TB free on the shared filesystem — the **quota**, not `df`, is binding.)
- **Egress**: `files.ipd.uw.edu`, `storage.googleapis.com`, `registry-1.docker.io`, `files.rcsb.org`,
  `alphafold.ebi.ac.uk`, `pypi.org` all reachable from the login node — so
  `singularity build` can pull `docker://rosettacommons/rfdiffusion` **directly on Grex**, and the
  staging script can fetch weights without an intermediate hop.

---

## 1. Strategy

**Phase 1 (now)**: one Apptainer image built **`FROM rosettacommons/rfdiffusion`**, targeting the
**`gpu` (V100) partition**, with the sokrypton fork's source and ColabDesign/JAX overlaid. Built on
Grex with `--fakeroot`.

**Phase 2 (deferred)**: a CUDA 12.x variant adding `lgpu` (L40s) support, built only once the
application is proven. Deferred deliberately — it is R-1/R-2 in full and nothing else depends on it.

### Why this is the low-risk path

The official Dockerfile is a **complete, working, fully-pinned solve** of the torch ↔ CUDA ↔ DGL ↔
e3nn ↔ SE3Transformer problem. Inheriting it means the hardest part of U1 is already done by someone
else. What we add on top is narrower and better understood.

### Why the official image alone is insufficient

`inference.dump_pdb` and `inference.dump_pdb_path` exist **only in the sokrypton fork**
(`config/inference/base.yaml` lines 22–23). They are the entire mechanism behind per-step structure
dumps, so **FR-16 and FR-17 depend on the fork**. The base image supplies the *environment*; the fork
supplies the *code*.

The layouts differ and this matters for how we overlay:

| | RosettaCommons (base image) | sokrypton fork (what we run) |
|---|---|---|
| Layout | installable package: `setup.py`, `rfdiffusion/`, `scripts/run_inference.py` | flat: `run_inference.py`, `inference/`, `util.py` at root |
| Install | `pip install --no-deps` | **none** — used via `sys.path` |
| Overlay method | — | clone to `/opt/RFdiffusion` and put on `PYTHONPATH` |

No name collision: the base installs a package called `rfdiffusion`; the fork's modules are
`inference`, `util`, `chemical`, etc. They coexist.

---

## 2. Pinned Dependency Set

### Inherited from `rosettacommons/rfdiffusion` (unchanged)

| Component | Pin | Source |
|---|---|---|
| Base OS | Ubuntu 20.04 | `nvcr.io/nvidia/cuda:11.6.2-cudnn8-runtime-ubuntu20.04` |
| CUDA / cuDNN | **11.6.2 / 8** | base image |
| Python | **3.9** | apt |
| torch | **`1.12.1+cu116`** | `download.pytorch.org/whl/cu116` |
| DGL | **`1.0.2+cu116`** | `data.dgl.ai/wheels/cu116/repo.html` |
| e3nn | **`0.3.3`** | PyPI |
| hydra-core | **`1.3.2`** | PyPI |
| pyrsistent | `0.19.3` · decorator `5.1.0` · pynvml `11.0.0` · wandb `0.12.0` | PyPI |
| dllogger | git (NVIDIA) | GitHub |
| SE3Transformer | from `env/SE3Transformer` | base image |
| `DGLBACKEND` | `pytorch` | base image env |

**Note on e3nn**: the notebook used `0.5.5`, but only because Colab's newer torch required it. On the
torch 1.12 base, **`0.3.3` is the correct and proven pin** — this is a case where inheriting the old
stack gives us the *right* answer, not merely an older one.

### Added by our overlay

| Component | Pin | Notes |
|---|---|---|
| `sokrypton/RFdiffusion` | **explicit commit SHA** | recorded at build; the notebook left this floating |
| `sokrypton/ColabDesign` | **explicit commit SHA** | same |
| `jax` + `jaxlib` | **cuda11 build, pinned** | from `storage.googleapis.com/jax-releases/jax_cuda_releases.html` — **not PyPI** (verified: PyPI carries no cuda11 jaxlib wheels) |
| `opt_einsum_fx` | pinned | required by e3nn paths |
| `ananas` | binary from `files.ipd.uw.edu` | staged, not in image |

---

## 3. ⚠️ Known Risk and Pre-Planned Fallback

**Risk (new, specific to Q2=A + Q3=A)**: ColabDesign is actively developed and may require a newer
JAX than is available for CUDA 11.6 / Python 3.9. JAX cuda11 wheels exist only on the `jax-releases`
index and only in older versions.

**This is the one place where the "inherit the proven stack" strategy could bite** — the proven stack
is proven for *RFdiffusion*, not for ColabDesign.

**Detection**: the build fails, or `designability_test.py` fails at import. Either way it surfaces at
build time or at M1, not in production.

**Pre-planned fallback — no re-decision needed if it triggers**: fall back to **Q3 = B, two images**:

| Image | Base | Purpose |
|---|---|---|
| `rfdiffusion.sif` | `rosettacommons/rfdiffusion` (CUDA 11.6) | backbone generation |
| `colabdesign.sif` | CUDA 12.x + modern JAX | ProteinMPNN + AlphaFold validation |

This is clean because the two frameworks run as **sequential subprocesses, never concurrently** —
different CUDA versions in different containers is not a conflict. The job script invokes each in
turn; `PipelineOrchestrator` already separates the stages, so only the invocation changes.

**Degradation path (last resort)**: JAX on CPU. Correct but slow; documented, not recommended.

---

## 4. ⚠️ Constraint Propagated to U2a — Python 3.9

**The base image is Python 3.9.** `rfd-runner` runs on it, and `rfd-runner` imports `rfd-core`.
Therefore:

> **`rfd-core` must target Python 3.9.**

This is a **hard constraint on U2a**, which is being built in parallel, and it contradicts the
indicative signatures written during Application Design. Concretely:

| Do not use | Use instead | Reason |
|---|---|---|
| `StrEnum` | `class X(str, Enum)` | `StrEnum` is 3.11+ |
| `int \| None` at runtime | `Optional[int]` + `from __future__ import annotations` | PEP 604 runtime unions are 3.10+ |
| `match` statements | `if`/`elif` | 3.10+ |
| `tomllib` | `tomli` | 3.11+ |

`rfd-web` is free to target a newer Python — it runs in its own `uv` venv on the login node and never
enters the container. Only `rfd-core` is bound by the lowest common denominator.

**Caught now specifically because U2a starts in parallel with U1** and would otherwise have been
written against 3.11 syntax and failed at M1.

---

## 5. Apptainer Definition (specification)

`containers/rfdiffusion.def`:

```
Bootstrap: docker
From: rosettacommons/rfdiffusion

%labels
    Maintainer  rfdiffusion-gui
    Base        rosettacommons/rfdiffusion (CUDA 11.6.2, torch 1.12.1)
    Fork        sokrypton/RFdiffusion @ <SHA>
    ColabDesign sokrypton/ColabDesign @ <SHA>
    Target      Grex gpu partition (V100, sm_70)

%post
    set -eu
    apt-get -q update
    DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y \
        git wget unzip
    rm -rf /var/lib/apt/lists/*

    # sokrypton fork -- required for inference.dump_pdb (FR-16, FR-17)
    git clone https://github.com/sokrypton/RFdiffusion.git /opt/RFdiffusion
    git -C /opt/RFdiffusion checkout <SHA>

    # JAX for CUDA 11 -- NOT on PyPI, must use the jax-releases index
    pip install --no-cache-dir "jax[cuda11_cudnn86]==<PIN>" \
        -f https://storage.googleapis.com/jax-releases/jax_cuda_releases.html

    pip install --no-cache-dir opt_einsum_fx==<PIN>
    pip install --no-cache-dir \
        "git+https://github.com/sokrypton/ColabDesign.git@<SHA>"

%environment
    export DGLBACKEND=pytorch
    export PYTHONPATH=/opt/RFdiffusion:/opt/rfdgui/packages/rfd-core/src:/opt/rfdgui/packages/rfd-runner/src:${PYTHONPATH:-}
    export RFD_MODELS=/opt/weights/rfdiffusion
    export RFD_AF_PARAMS=/opt/weights/alphafold
    export ANANAS_BIN=/opt/weights/bin/ananas

%runscript
    exec python3.9 -m rfd_runner "$@"
```

**Deliberately *not* in the image**: model weights (staged separately, ~8 GB), `rfd-core`/`rfd-runner`
source (bind-mounted per DD-2), and the `ananas` binary (staged with weights).

**Why source is bind-mounted**: a Python change must not require rebuilding a multi-GB image. Under
an ASAP constraint that is the difference between a minute and an hour, repeatedly.

---

## 6. Weight Staging

`scripts/stage-weights.sh` — run **once**, on a login node, before any job.

| Asset | Size | Destination |
|---|---|---|
| `Base_ckpt.pt` | ~1.3 GB | `$RFD_WEIGHTS/rfdiffusion/` |
| `Complex_base_ckpt.pt` | ~1.3 GB | `$RFD_WEIGHTS/rfdiffusion/` |
| `Complex_beta_ckpt.pt` | ~1.3 GB | `$RFD_WEIGHTS/rfdiffusion/` |
| `schedules.zip` (extracted) | small | `$RFD_WEIGHTS/rfdiffusion/schedules/` |
| `alphafold_params_2022-12-06.tar` | ~4 GB | `$RFD_WEIGHTS/alphafold/` |
| `ananas` | small | `$RFD_WEIGHTS/bin/` |

**Behaviours**:
- **`curl`/`wget`, never `aria2c`** — `aria2` requires `apt-get` and there is no root on Grex (C-5).
- **Idempotent** — skips assets already present and checksum-valid, so an interrupted staging resumes.
- **Checksums recorded and verified**, so a truncated download fails at staging rather than mid-job.
  The notebook's `.aria2`-marker polling had no integrity check at all.
- **Multimer AlphaFold params optional** (`--no-multimer`), since `use_multimer` defaults off and this
  is real money against a 100 GB quota.
- **`ananas` `chmod +x` and executability verified** at staging; `symmetry="auto"` is the only feature
  depending on it and must degrade gracefully.

---

## 7. Filesystem Layout

Defaults on `/home` (Q8), every path overridable (NFR-6):

| Env var | Default | Contents |
|---|---|---|
| `RFD_PROJECT_ROOT` | `$HOME/rfdiffusion-gui` | source; bind-mounted to `/opt/rfdgui` |
| `RFD_WEIGHTS` | `$HOME/rfd-weights` | ~8 GB of model assets → `/opt/weights` |
| `RFD_IMAGE` | `$HOME/rfd-images/rfdiffusion.sif` | the SIF |
| `RFD_OUTPUT_ROOT` | `$HOME/rfd-runs` | per-run directories → `/opt/outputs` |
| `RFD_DB` | `$HOME/.local/share/rfdgui/runs.sqlite` | SQLite index — **`/home`, never Lustre** |
| `APPTAINER_CACHEDIR` | `$HOME/.cache/apptainer` | **set explicitly** (G-18) |

### Quota budget (100 GB `/home`)

| Item | Size |
|---|---|
| Model weights | ~8 GB (~4 GB without multimer) |
| SIF image | ~6–10 GB |
| Build cache (transient) | up to ~10 GB |
| Per run | tens–hundreds of MB |

**~15–25 GB baseline.** The build cache is the one that bites unexpectedly, which is why
`APPTAINER_CACHEDIR` is set explicitly and the staging script prints a quota summary on completion.

---

## 8. Build Procedure (Q4 = A — Grex `--fakeroot`)

```bash
module load singularity
export APPTAINER_CACHEDIR=$HOME/.cache/apptainer
mkdir -p "$APPTAINER_CACHEDIR" "$(dirname "$RFD_IMAGE")"
singularity build --fakeroot "$RFD_IMAGE" containers/rfdiffusion.def
```

**Build on a compute node, not a login node** — a multi-GB image build is exactly the "heavy compute"
login nodes are not for (C-11). An interactive `salloc` on a CPU partition is sufficient; no GPU is
needed to *build*.

**If `--fakeroot` fails** (documented as occasionally limited for complex recipes), fall back in this
order: (1) Sylabs remote build `--remote`; (2) local Docker/Podman in WSL2 then convert and transfer.
Recorded so a build failure is a known branch, not a blocker.

---

## 9. Verification (U1 definition of done)

Run on a `gpu`-partition allocation:

1. `apptainer exec --nv $RFD_IMAGE nvidia-smi` — GPU visible in container
2. `apptainer exec --nv $RFD_IMAGE python3.9 -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"` — **must report a V100**
3. `apptainer exec --nv $RFD_IMAGE python3.9 -c "import dgl, e3nn; print(dgl.__version__, e3nn.__version__)"`
4. `apptainer exec --nv $RFD_IMAGE python3.9 /opt/RFdiffusion/run_inference.py --help`
5. **`grep -c dump_pdb /opt/RFdiffusion/config/inference/base.yaml` returns 2** — confirms the fork,
   not the base package. *This is the check that proves FR-16/FR-17 are achievable.*
6. `apptainer exec --nv $RFD_IMAGE python3.9 -c "import jax; print(jax.devices())"` — **the risk
   check from §3**; if this fails, trigger the two-image fallback
7. A trivial unconditional design (`contigs=50`, `iterations=10`) completes and writes per-step PDBs
   to the dump path

Steps 5 and 6 are the ones worth running first — they are the two findings that could invalidate the
whole approach, and both are cheap.

---

## 10. Phase 2 — CUDA 12.x (deferred, Q1 = D)

**Trigger (revised after preflight)**: a real need for **`lgpu` specifically** — designs exceeding
32 GB of VRAM. Preflight showed the Phase 1 image already reaches 36 V100s and 12 A30s across five
partition families, so "queue contention" is no longer a plausible trigger. Phase 2's value has
narrowed to L40s access alone.

**Approach**: a second definition from a `pytorch/pytorch:2.4.x-cuda12.4-cudnn9` base, replicating
the same overlay. A single CUDA 12.4 torch wheel covers **sm_70 through sm_90**, so the Phase 2 image
would supersede Phase 1 rather than complement it — this is exactly why the notebook runs on any
Colab GPU.

**Deferred because**: DGL's cu124 wheels are the flaky element (R-2), nothing in U2a/U2b/U3/U4
depends on which image is used, and `RFD_IMAGE` is already configurable — swapping images is a config
change, not a code change.
