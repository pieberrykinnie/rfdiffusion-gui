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

**⚠️ MATERIALIZED 2026-08-06 — Tier 1 fallback now active.** The risk described above turned out to
be slightly different in shape from what was anticipated: it was not ColabDesign requiring a newer
JAX, but **JAX itself requiring a newer CUDA than this base image ships**. `jaxlib==0.4.25` failed on
a real GPU with `Found CUDA version 11060, but JAX was built against version 11080, which is newer`.
Root-caused to `jax 0.4.8` (2023-03-29 `CHANGELOG.md`: "CUDA 11.4 support has been dropped... only
support CUDA 11.8 and CUDA 12") — every cuda11 jaxlib from 0.4.8 onward needs CUDA ≥ 11.8; this base
is 11.6.2. `jaxlib 0.4.7` is the newest build that predates the bump, paired with `chex==0.1.82`
(the newest chex release still accepting `jax>=0.4.6` rather than the `>=0.4.16` that `0.1.86`
requires). Full derivation in §8.1g. **Tier 2 (two images, Q3=B) remains the fallback if 0.4.7 turns
out to have some other incompatibility with ColabDesign at the pinned commit** — not yet needed.

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
salloc --partition=skylake --cpus-per-task=4 --mem=16000M --time=0-02:00:00
bash scripts/build-image.sh
```

**Build on a compute node, not a login node** — a multi-GB image build is exactly the "heavy compute"
login nodes are not for (C-11). `build-image.sh` refuses to run on `yak`/`bison`. No GPU is needed to
*build*.

### 8.1 ⚠️ `--fakeroot` cannot build from network storage (observed 2026-07-31)

**Symptom**: the first build attempt failed immediately with

```
FATAL: unable to open file .../containers/rfdiffusion.def: permission denied
```

— before executing a single build step, on a file the user can read normally.

**Root cause**: `--fakeroot` runs the build inside a **user namespace that remaps the invoking UID to
root**. On network storage with **`root_squash`** (both Grex `/home` over NFS and `/project` over
Lustre), the server maps that root identity back to `nobody`. `nobody` cannot traverse a `0700` home
directory, and is not the file's owner — so the very first `open()` of the definition fails.

This is not specific to complex recipes, and it is not intermittent: **any** `--fakeroot` build whose
inputs live under root_squashed network storage fails this way. The original design assumed the repo
would sit in `$HOME`; in practice it was cloned into `/project` space
(`~/projects/def-cardona/<user>/…`), which made the collision unavoidable.

**Fix (implemented in `build-image.sh`)**: stage the build onto **node-local `$TMPDIR`**, build there,
then copy the finished SIF to `$RFD_IMAGE`. Specifically:

- definition copied to `$TMPDIR/rfd-build-$$/`
- `APPTAINER_CACHEDIR` pointed at the same node-local directory
- SIF built locally, then copied out **before the job ends** (`$TMPDIR` is removed at job exit)
- `trap cleanup EXIT` removes the staging directory

**This is the correct approach independently of the permission problem.** A container build writes
tens of thousands of small files, which is precisely the metadata-heavy pattern Grex's documentation
says to keep off the shared parallel filesystem (G-11, G-14). Node-local scratch is 100–200 GB;
the build needs ~25 GB, and the script checks this before starting.

**Secondary benefit**: the transient build cache — which can grow to the size of the image again —
no longer counts against the 100 GB `/home` quota.

**Preflight now detects the precondition**: `preflight-grex.sh` reports the repo's filesystem type
and `$HOME`'s mode, and warns when a hand-run `--fakeroot` build from that path would fail.

### 8.1b ⚠️ `apt-get` cannot run inside a `--fakeroot` `%post` (observed 2026-07-31)

**Symptom**: after the staging fix, the build pulled all base layers successfully and entered
`%post`, then failed on the very first command:

```
Err:1 http://archive.ubuntu.com/ubuntu focal InRelease
  Couldn't create temporary file /tmp/apt.conf.E9vUL4 for passing config to apt-key
E: The repository '...' is not signed.
FATAL: While performing build: while running engine: exit status 100
```

**Root cause**: Singularity bind-mounts the host's `/tmp` (and `/var/tmp`) into the build container.
`apt` **drops privileges to its sandbox user `_apt` (uid 100)** before fetching, as a security
measure. Under the `--fakeroot` UID mapping that identity is unmapped on the host, so `_apt` cannot
create files in the bind-mounted `/tmp`. `apt-key` then cannot pass its config, GPG verification
fails, and every repository is rejected as unsigned.

This is a general property of `apt` + `--fakeroot` + bind-mounted `/tmp` — not specific to this image.

**Fix**: **remove `apt-get` from `%post` entirely.** It was never needed:

| Package we were installing | Actually required? |
|---|---|
| `git` | **already in the base image** (RosettaCommons Dockerfile installs it) |
| `ca-certificates` | already present — the base image pip-installs from `git+https://` |
| `wget`, `unzip` | **never used inside the container** — `stage-weights.sh` runs those on the host |

`%post` now uses only `git`, `pip`, `grep` and `mkdir`. Removing apt eliminates the failure mode
rather than working around it, and makes the build faster and more deterministic.

**Hardening applied alongside**:
- `%post` sets `TMPDIR=/opt/buildtmp`, a directory **inside the image**, so no build step depends on
  host `/tmp` permissions (pip in particular unpacks wheels via `TMPDIR`). Removed at the end of
  `%post` so it does not bloat the image.
- `pip` is invoked as `python3.9 -m pip` so the interpreter is unambiguous.
- A `command -v git` guard fails the build with a clear message if the base image ever stops
  shipping git.

**General lesson recorded**: inside a `--fakeroot` `%post`, avoid any tool that drops privileges to a
service account. `apt` is the common one; `gpg` agents and some package managers behave similarly.
Prefer tools that run as the (fake) root user throughout.

### 8.1c ⚠️ The published base image is **uv-based**, not built from its own repo Dockerfile

**Symptom**: third build. Every earlier step succeeded — layers pulled, fork cloned at the pinned SHA,
`dump_pdb` assertions passed — then:

```
+ python3.9 -m pip install --no-cache-dir nvidia-cudnn-cu11==8.6.0.163
/app/RFdiffusion/.venv/bin/python3.9: No module named pip
```

**Root cause**: **`rosettacommons/rfdiffusion` on Docker Hub is not built from the pip-based
Dockerfile in that repository.** Reading the actual image config from the registry shows a completely
different build:

```
COPY /uv /uvx /bin/
RUN ... uv venv --python 3.9 && uv pip install dgl==1.0.2+cu116 torch==1.12.1+cu116 \
        e3nn==0.3.3 ... && uv pip install /app/RFdiffusion/env/SE3Transformer \
        && uv pip install -e /app/RFdiffusion --no-deps
ENV PATH=/app/RFdiffusion/.venv/bin:/usr/local/nvidia/bin:...
ENTRYPOINT ["/app/RFdiffusion/.venv/bin/python", "/app/RFdiffusion/scripts/run_inference.py"]
```

So `python3.9` resolves to the **uv venv** at `/app/RFdiffusion/.venv`, and that venv has **no `pip`
module** — uv does not install one by default. This was a **documentation-vs-reality gap**: reading
the repo's Dockerfile was reasonable, but only the registry image config is authoritative about what
was actually published.

**Fixes applied**:
- All installs go through `uv pip install --python /app/RFdiffusion/.venv/bin/python --no-cache …`,
  targeting the venv explicitly. Guards assert `uv` and the venv interpreter exist.
- `%runscript` and `%test` use `/app/RFdiffusion/.venv/bin/python`, not `python3.9`.
- **`LD_LIBRARY_PATH` corrected.** It pointed at `/usr/local/lib/python3.9/dist-packages/nvidia/cudnn/lib`,
  which does not exist here. The real path is
  `/app/RFdiffusion/.venv/lib/python3.9/site-packages/nvidia/cudnn/lib`. Left uncorrected, the
  pip-supplied cuDNN 8.6 would have been invisible and JAX would have silently fallen back to the
  base image's 8.4 — producing exactly the failure the cuDNN pin was meant to prevent.

### 8.1d ✅ Good news: model checkpoints and the CUDA/cuDNN versions are confirmed in-image

The same registry inspection produced two findings that **simplify** the design.

**1. All nine RFdiffusion checkpoints are baked into the image**, downloaded at build time into
`/app/RFdiffusion/models/` — including all three this project uses (`Base_ckpt.pt`,
`Complex_base_ckpt.pt`, `Complex_beta_ckpt.pt`). That is what the 5.6 GiB layer contains.

The fork resolves checkpoints as `{SCRIPT_DIR}/../models/*.pt` (confirmed in `inference/model_runners.py`
lines 80–91), i.e. `/opt/RFdiffusion/models`. A **symlink** to `/app/RFdiffusion/models` is therefore
sufficient.

**Consequence**: `stage-weights.sh` **no longer downloads RFdiffusion checkpoints at all — roughly
4 GB less to stage**, and one less thing that can be truncated. Staging is now AlphaFold parameters
plus the `ananas` binary.

**2. `NV_CUDNN_VERSION=8.4.0.27` confirmed** — the assumption behind pinning `nvidia-cudnn-cu11==8.6.0.163`
was correct. jaxlib `cuda11.cudnn86` needs ≥ 8.6, and the base genuinely ships 8.4.

**3. Diffusion schedules need writable storage.** `model_runners.py` line 31 does
`os.mkdir(f'{SCRIPT_DIR}/../schedules')` at import when absent, and `Diffuser(cache_dir=…)` **writes**
there for uncached `T` values. A SIF is read-only at run time, so:
- ~~the image ships a pre-computed seed at `/opt/schedules-seed`~~ — **superseded by §8.1e**: the
  upstream `schedules.zip` is 404, pre-seeding was only ever an optimisation, and **no seed exists
  in the shipped image**. The `Diffuser` computes and caches any missing schedule on CPU.
- `/opt/RFdiffusion/schedules` is a **symlink to `/scratch/schedules`** (bound from `$TMPDIR`)
- **U2b requirement**: the runner must `mkdir -p /scratch/schedules` before invoking
  `run_inference.py` (no seed to copy — see above). `os.mkdir` on a dangling symlink raises
  `FileExistsError`, so this cannot be left to the fork.
- ⚠️ **Confirmed live 2026-08-06.** `verify-image.sh` omitted this `mkdir` and every fork import
  failed with exactly this error. The requirement is load-bearing, not defensive — U1's own
  verification script was its first consumer and its first violator.

### 8.1e ⚠️ The CUDA jaxlib pin was silently clobbered — and the dead schedules URL

Fourth build. Everything through ColabDesign succeeded, but the log contained this:

```
+ uv pip install ... py3Dmol joblib chex optax dm-haiku immutabledict
 - jax==0.4.25
 + jax==0.4.30
 - jaxlib==0.4.25+cuda11.cudnn86
 + jaxlib==0.4.30
```

**This is the most dangerous failure so far, because it was not a failure.** The extras install pulled
a newer `jax`, and uv correspondingly replaced `jaxlib 0.4.25+cuda11.cudnn86` with the **generic
`jaxlib 0.4.30`** — a **CPU-only wheel**. Had the build completed, it would have produced an image
that looks correct and in which **JAX silently has no GPU**. AlphaFold validation would have run on
CPU at a small fraction of the expected speed, with no error anywhere.

The `--no-deps` on ColabDesign was the right instinct applied to the wrong package: the threat came
from the *extras* install that existed precisely to compensate for that `--no-deps`.

**Fixes**:
1. **One resolution pass.** `jax`, `jaxlib`, and every jax-dependent extra are installed in a single
   `uv pip install` with the pins present, so an incompatibility surfaces as a **loud conflict**
   rather than a silent downgrade. Extras pinned to versions verified via PyPI `requires-dist` to
   accept jax 0.4.25 on Python 3.9 (`chex==0.1.86` needs `jax>=0.4.16`; `optax==0.2.2` declares no
   jax bound; `dm-haiku==0.0.12` constrains jax only under its optional `[jax]` extra).
2. **A build-time guard that fails the build** if `importlib.metadata.version("jaxlib")` does not
   contain `cuda`. A CUDA wheel reports `0.4.25+cuda11.cudnn86`; the CPU wheel reports a bare
   `0.4.30`. This is the check that would have caught the clobbering, and it now runs on every build.
3. **`verify-image.sh` check 4 asserts the same thing at run time**, so a bad image cannot pass
   verification either.

**Generalisable lesson**: when a package is pinned to a *local version* (`+cuda11.cudnn86`), any
later resolution that touches its dependents can silently swap it for the upstream build of the same
version series. Pin such packages in the **same** resolution as everything that constrains them, and
assert the local version afterwards.

**Also fixed in this round — dead URL**: `https://files.ipd.uw.edu/krypton/schedules.zip` now returns
**404** (verified 2026-08-01), which is what `wget` exit 8 reported. Pre-seeding diffusion schedules
was only ever an optimisation — the `Diffuser` computes and caches any missing schedule. The seed is
removed; `/opt/RFdiffusion/schedules` remains a symlink to writable `/scratch/schedules`, and the
cost is a one-time CPU schedule generation per distinct `T`.

### 8.1f ⚠️ Two fork dependencies missing from the base image (observed 2026-08-06, live verification)

`verify-image.sh` check 6, on a real built and staged image on Grex, failed with
`ModuleNotFoundError: No module named 'icecream'` (`diff_util.py:6`, imported via
`inference/utils.py:8`) — the first defect this design missed that only a real execution could catch.

**Root cause**: `reference/diffusion.py`'s commented-out cell 2 ran
`pip install jedi omegaconf hydra-core icecream pyrsistent pynvml decorator` under Colab — a
convenience cell for everything the fork might need, on a base image with no pins. `rfdiffusion.def`
inherits the **RosettaCommons** base's install list, built for RosettaCommons's own codebase, which
imports none of these six packages.

**Resolved by reading the fork's actual imports at the pinned commit, not by installing the whole
Colab cell defensively**:

| Package | Needed? | Why |
|---|---|---|
| `icecream` | **Yes** | Imported unconditionally by the entry point (`run_inference.py`), `diff_util.py`, `contigs.py`, `potentials/manager.py`, `RoseTTAFoldModel.py`, `Embeddings.py` |
| `pyrsistent` | **Yes** | `inference/symmetry.py`: `from pyrsistent import v` — the symmetry feature this project exposes depends on it directly |
| `jedi` | No | Zero references in the fork; Colab tab-completion only |
| `pynvml`, `decorator` | No | Listed in `env/SE3Transformer/requirements.txt`, but that file is decorative — `setup.py` declares no `install_requires`. Both are imported only by `se3_transformer.runtime.{training,inference}` (NVIDIA's own training/benchmark harness); RFdiffusion imports only `se3_transformer.model`, never `.runtime` |

Both required packages sit on **one eager import chain** — `run_inference.py` → `inference.utils` →
`inference.model_runners` → `inference.symmetry` → `pyrsistent` — so `verify-image.sh` check 6
exercises both with no script change; fixing `icecream` alone would only have deferred discovering
`pyrsistent` to a fourth build/stage/verify cycle.

**Fixed**: `rfdiffusion.def` now runs `uv pip install "icecream" "pyrsistent"` into the fork's venv
immediately after the `dump_pdb` build-time assertion.

**Confirmed 2026-08-06**: rebuilt and re-verified on the same CPU node — check 6 now passes in full,
no further hidden import gap. Combined with §9's status, **U1's entire CPU-verifiable surface is
now clean**; only the GPU-gated checks (1, 2, and the JAX device test) remain.

**Generalisable lesson, consistent with §8.1e**: pinning what the *base* image installs says nothing
about what the *overlaid* fork needs. The Colab cell this project deliberately never executes (cell 2
is commented out, per the original reverse-engineering findings) is nonetheless the only complete
record of the fork's real third-party dependencies — it should have been cross-checked against the
fork's actual imports during Step 2 of code generation, not discovered via a runtime traceback.

### 8.1g ⚠️ The §3 risk materialized: JAX built against a newer CUDA than this base ships (observed 2026-08-06, first real GPU allocation)

U1's CPU-verifiable surface was fully clean (§9 status, PASS 9/FAIL 3, three rounds). The first real
GPU allocation then exercised the one check three rounds of CPU verification structurally cannot
reach — and it failed exactly where §3 said it might, though not in the shape originally described:

```
CUDA backend failed to initialize: Found CUDA version 11060, but JAX was built against
version 11080, which is newer. The copy of CUDA that is installed must be at least as new
as the version against which JAX was built.
```

**Not a ColabDesign-needs-newer-JAX problem** (the shape §3 anticipated) — the reverse: **JAX itself
needs a newer CUDA than this base provides.** CUDA's minor-version forward-compatibility model runs
one direction only: a newer *runtime* can execute code built against an *older* CUDA within the same
major version, never the other way around. `jaxlib 0.4.25+cuda11.cudnn86` was built against CUDA
11.8; this base image's runtime is CUDA 11.6.2. Older runtime, newer build — the direction that
cannot work.

**Root-caused from JAX's own `CHANGELOG.md`**, fetched directly rather than inferred from wheel
filenames (the `+cuda11.cudnn86` tag says nothing about the exact CUDA minor version a wheel was
compiled against — that information exists only in the changelog):

> ## jax 0.4.8 (March 29, 2023)
> * Deprecations
>   * CUDA 11.4 support has been dropped. JAX GPU wheels only support CUDA 11.8 and CUDA 12.

Every cuda11-tagged jaxlib release from **0.4.8 onward** — which includes 0.4.25, the version this
project had pinned — is built against CUDA 11.8. **`jaxlib 0.4.7` is the newest cuda11 release that
predates this bump**, confirmed by enumerating the complete cp39 cuda11 wheel index at
`jax_cuda_releases.html`: there is no cuda11 build between 0.4.7 and 0.4.8 that this project's
CUDA-11.6 base could satisfy — 0.4.7 is not an arbitrary older pin, it is the actual ceiling.

**Downgrading jax alone would have failed the very next resolution.** `chex==0.1.86` (pinned
alongside jax 0.4.25) declares `jax>=0.4.16`, which `jax==0.4.7` violates — `uv pip install` would
have reported this as a loud conflict (correctly, per the "one resolution pass" design in §8.1e)
rather than silently succeeding, but it would still have cost a fourth build/verify cycle to
discover. Checked chex's PyPI release history for exactly where the floor moved: `0.1.82`
(2023-07-20) still requires only `jax>=0.4.6`; the bump to `jax>=0.4.16` landed in `0.1.83`
(2023-09-20). `optax==0.2.2` (`jax>=0.1.55`) and `dm-haiku==0.0.12` (jax constraint lives entirely
under an `[jax]` extra this install never requests) needed no change — confirmed by reading each
package's actual `requires_dist`, not by assuming the whole extras set would need re-pinning.

**Fixed**: `containers/rfdiffusion.def`'s single resolution pass now installs `jax==0.4.7`,
`jaxlib==0.4.7+cuda11.cudnn86`, `chex==0.1.82`, `optax==0.2.2`, `dm-haiku==0.0.12`. The pip-supplied
`nvidia-cudnn-cu11==8.6.0.163` is **unchanged** — that addresses a different problem (cuDNN version)
orthogonal to this one (CUDA version), and switching it would have been an unnecessary second
variable in the same fix. The build-time CUDA-build guard (§8.1e) is unaffected in mechanism but its
comment now states explicitly what it does **not** catch: it asserts jaxlib *is* a CUDA build, not
that the CUDA build is *new enough* for the runtime — that distinction is exactly what this defect
was, and only a real GPU execution (verify-image.sh checks 1/2/4) can catch it.

**Not yet rebuilt or re-verified on GPU** — pending the user's next `build-image.sh` →
`verify-image.sh` cycle on a GPU allocation. If `jaxlib 0.4.7` surfaces some other incompatibility
with ColabDesign at the pinned commit, Tier 2 (§3 — two images, Q3=B) is the next and last fallback;
the CUDA-11-only ceiling established here is unconditional, so there is no Tier 1.5 to try first.

**Generalisable lesson, continuing §8.1e/§8.1f's pattern**: a package's local-version wheel tag
(`+cuda11.cudnn86`) encodes only what its *authors chose to publish in the filename* — here, cuDNN
compatibility — not everything the wheel actually requires. The CUDA minor-version floor was silent
in every artifact that matters at install time (PyPI metadata, the wheel filename, `pip`/`uv`'s own
conflict resolution) and surfaced only in prose, in a changelog, and only as a runtime failure on
real hardware. Pin verification against a wheel index tells you a wheel *exists*; it does not tell
you it will *run* on your specific driver/runtime combination.

### 8.2 Remaining fallbacks

If a staged `--fakeroot` build still fails: (1) Sylabs remote build `--remote`; (2) local
Docker/Podman then convert and transfer. Recorded so a build failure is a known branch, not a blocker.

---

## 9. Verification (U1 definition of done)

Implemented as `scripts/verify-image.sh`. **Amended 2026-08-06 after first execution** — see
`u1-code-summary.md` §Verification Results.

**Only steps 1, 2 and the device half of 6 require a GPU.** Steps 3, 4, 5, 7 and the jaxlib-version
half of 6 are filesystem and import tests that run on any CPU node. Given that the `gpu` partition
was quoting a five-day queue, this split is worth using deliberately: **step 5 — the check that
proves FR-16/FR-17 are achievable — needs no GPU at all**, and passed on a `skylake` node.

Run steps 3–5, 7 on any CPU allocation; run 1, 2, 6 on a short GPU allocation:

1. `apptainer exec --nv $RFD_IMAGE nvidia-smi` — GPU visible in container *(GPU)*
2. `apptainer exec --nv $RFD_IMAGE python3.9 -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"` — **must report a V100 or an A30** (sm_70/sm_80; preflight found the A30 partitions the docs omit — **not** an L40s, which is sm_89) *(GPU)*
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

**Status 2026-08-06, CPU rounds (1–3)**: step 5 **PASSED** (fork at pinned sha `597d37f2…`,
`dump_pdb` ×2) — FR-16 and FR-17 are achievable. `icecream`/`pyrsistent` found missing and fixed
(§8.1f); after the rebuild, U1's **entire CPU-verifiable surface passed clean**: PASS 9 / FAIL 3,
the 3 FAILs being exactly checks 1, 2, and the device half of 4 — all genuinely GPU-gated, as
designed.

**Status 2026-08-06, first GPU round**: the device test **correctly failed** — not a script defect
this time, but the real §3 risk finally materializing (§8.1g): `jaxlib 0.4.25` requires CUDA ≥ 11.8,
this base ships 11.6.2. Fixed by re-pinning to `jaxlib 0.4.7` (the newest cuda11 build predating
that requirement) plus `chex 0.1.82` (the version bump this forced). **Not yet re-verified on GPU**
— this is now the only remaining U1 verification step.

**Three preconditions this section did not originally state, all discovered by running it**:
`/scratch/schedules` must exist before *anything* imports the fork (§8.1d); any check asserting a
GPU must assert against the device list specifically, not the whole output, since a version string
containing `cuda` will otherwise satisfy it (§8.1f's check-4 fix); and a wheel's `+cudaXX.cudnnYY`
tag encodes only cuDNN compatibility, never the CUDA minor-version floor it was actually compiled
against (§8.1g) — that requires reading the package's changelog, not its filename.

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
