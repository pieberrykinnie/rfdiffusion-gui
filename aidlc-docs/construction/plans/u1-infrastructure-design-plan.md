# U1 Runtime and Container — Infrastructure Design Plan

**Unit**: U1 Runtime and Container
**Stage**: CONSTRUCTION — Infrastructure Design
**Date**: 2026-07-31

---

## Research Findings (completed before writing this plan)

Three findings that change the shape of U1. Two are good news; one is a constraint nobody would want
to discover after building an image.

### Finding 1 — An official RFdiffusion container exists, and it will not work unmodified

`rosettacommons/rfdiffusion` is published on Docker Hub with a Dockerfile in the repo, pullable
directly with `apptainer pull … docker://rosettacommons/rfdiffusion`.

**But the notebook uses the `sokrypton/RFdiffusion` fork, not RosettaCommons — and the difference is
load-bearing.** Comparing `config/inference/base.yaml` in both:

| Key | sokrypton fork | RosettaCommons |
|---|---|---|
| `inference.dump_pdb` | **present** (line 22) | **absent** |
| `inference.dump_pdb_path` | **present** (line 23) | **absent** |

Those two keys are what make per-step structure dumps possible. **FR-16 (live step progress) and
FR-17 (live 3D preview) depend entirely on them.** The official image cannot deliver the live-progress
feature at all.

The layouts also differ: RosettaCommons is an installable package (`setup.py`, `rfdiffusion/`,
`scripts/run_inference.py`); the sokrypton fork is flat (`run_inference.py` and `inference/` at the
root, no `setup.py`, used via `sys.path`). So the official image's *installed package* is not a
drop-in for the fork.

**What is still worth taking**: the official Dockerfile is a **proven, fully-pinned dependency set** —
which is exactly what R-1 and R-2 are about. We can inherit that resolved environment and overlay the
fork's source, since both are the same model code.

### Finding 2 — Two viable pinned stacks exist, and they are far apart

| | **Official RosettaCommons stack** | **Notebook (sokrypton) stack** |
|---|---|---|
| CUDA | 11.6.2 + cuDNN 8 | 12.4 (implied by the DGL wheel index) |
| Python | 3.9 | Colab default (3.10/3.11) |
| torch | `1.12.1+cu116` | 2.4 |
| DGL | `1.0.2+cu116` | unpinned, `torch-2.4/cu124` index |
| e3nn | `0.3.3` | `0.5.5` |
| hydra-core | `1.3.2` | unpinned |
| Status | **fully pinned, known-good** | **almost entirely unpinned** |

### Finding 3 — ⚠️ The proven stack cannot run on Grex's L40s nodes

This is the constraint that drives Question 1.

Grex's two general GPU partitions have different GPU generations:

| Partition | GPU | Compute capability | Capacity |
|---|---|---|---|
| `gpu` | V100 32 GB | **sm_70** (Volta) | 2 nodes × 4 = **8 GPUs** |
| `lgpu` | L40s 48 GB | **sm_89** (Ada Lovelace) | 2 nodes × 2 = **4 GPUs** |

**CUDA 11.6 predates Ada Lovelace.** sm_89 support arrives in CUDA 11.8. So `torch==1.12.1+cu116` —
the proven stack — **will not run on `lgpu` at all**. It is V100-only.

Targeting both partitions requires building the newer CUDA 12.x stack, which is precisely the
unpinned territory that makes R-1/R-2 the project's top risks.

---

## Plan Steps

### Part 1 — Design decisions
- [x] Research existing RFdiffusion container options
- [x] Compare sokrypton fork against RosettaCommons for feature compatibility
- [x] Identify the GPU-generation constraint across Grex partitions
- [x] User answers the 4 questions below — **Q1 = D, Q2 = A, Q3 = A, Q4 = A** (2026-07-31)
- [x] Analyze answers for ambiguity; raise follow-ups if needed — all unambiguous and mutually
      consistent. Q1=D phase 1 is option A (V100 / CUDA 11.6), which is exactly what Q2=A assumes.
      No follow-ups needed. Two consequences flagged rather than re-asked: the JAX-on-CUDA-11 risk
      (pre-planned two-image fallback) and the Python 3.9 constraint propagated to U2a.

### Part 2 — Artifact generation
- [x] `infrastructure-design.md` — image strategy, pinned dependency set, build procedure,
      weight staging, filesystem layout, `APPTAINER_CACHEDIR` handling
- [x] `deployment-architecture.md` — node topology, `#SBATCH` template, bind-mount map,
      environment variables, the login-node/compute-node boundary
- [x] Validate against G-1 … G-20 — conformance table in deployment-architecture.md §3

---

## Questions

### Question 1 ⚠️ — Which GPU partitions must be supported?

The single most consequential decision in U1. It determines whether you get the proven dependency
stack or have to resolve a new one.

A) **`gpu` (V100) only — build on the proven CUDA 11.6 stack.** Inherit RosettaCommons' fully-pinned dependency set exactly as published, overlay the sokrypton fork's source. **Largest possible reduction in R-1/R-2** — the hardest problem in the project becomes "reuse someone else's solved build." You also get the larger GPU pool (8 V100s vs 4 L40s). Cost: `lgpu` is unavailable, and 32 GB caps the size of designs you can run. *(Recommended for getting working ASAP — this is the option that most directly serves your stated priority.)*

B) **Both `gpu` and `lgpu` — build the CUDA 12.x stack.** Access to all 12 GPUs and to 48 GB cards for larger complexes. Cost: you are resolving torch 2.4 + DGL cu124 + e3nn 0.5.5 + JAX yourself, from a starting point where the notebook pinned almost nothing. This is R-1 and R-2 in full.

C) **`lgpu` only — CUDA 12.x, newer hardware.** Fewer GPUs but more memory each and much faster cards. Same dependency risk as (B) with less queue capacity.

D) **Start with (A), add (B) later as a second image.** Get a working V100 pipeline first, then build a CUDA 12.x variant once the application is proven. Two images to maintain, but the risk is sequenced rather than taken up front.

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

### Question 2 — Image base strategy

Assumes whichever CUDA generation you chose above.

A) **Build `FROM rosettacommons/rfdiffusion`**, then overlay: the sokrypton fork source (for `dump_pdb`), ColabDesign, JAX, and AlphaFold support. Inherits a known-good torch/DGL/SE3Transformer environment; smallest amount of dependency resolution done by us. *(Recommended if Q1 = A — it is the whole point of choosing the proven stack.)*

B) **Build from `nvcr.io/nvidia/cuda:<ver>-cudnn-runtime-ubuntu…`**, replicating the official Dockerfile's steps but substituting the fork and adding ColabDesign/JAX. Full control, explicit pins in one readable file, no inherited surprises — at the cost of doing the resolution ourselves.

C) **Build from a `pytorch/pytorch` base image** with torch+CUDA already matched, then add DGL, e3nn, SE3Transformer, the fork, and ColabDesign. A middle path that removes the hardest single pin (torch↔CUDA) without inheriting an entire application image.

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

### Question 3 — One image or two?

The pipeline needs **two different ML frameworks**: PyTorch (RFdiffusion backbone generation) and
JAX (ProteinMPNN + AlphaFold validation, via ColabDesign). They run as **sequential subprocesses**,
never concurrently.

A) **One image containing both.** A single artifact, one bind-mount, one thing to build and stage. Risk: torch and JAX must coexist on one CUDA/cuDNN version, and their pins can fight. *(Recommended — they run sequentially, so the usual JAX/PyTorch GPU-memory contention does not arise, and one artifact is materially simpler to build, stage, and reason about.)*

B) **Two images** — `rfdiffusion.sif` and `colabdesign.sif` — with the job script invoking each in turn. Decouples the two dependency resolutions entirely, so a JAX problem cannot block backbone generation. Costs a second build, a second staging step, roughly double the disk against your `/home` quota, and a more complex job script.

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

### Question 4 — Where will the image be built?

Grex documents three routes, and your local environment offers a fourth.

A) **On Grex with `--fakeroot`** (Singularity-CE from SBEnv or Apptainer from CCEnv). No external accounts, builds where it will run. Fakeroot builds occasionally hit limitations with complex recipes. *(Recommended to try first — it is the documented path and keeps everything on one machine.)*

B) **Locally in WSL2 with Docker/Podman**, then convert to SIF and transfer. You control the build environment completely and iterate fast, but you must move a multi-GB image to Grex over the network.

C) **Remote build via Sylabs Cloud** (`--remote`). Requires a free Sylabs account; Grex documents this as supported.

D) **Pull a prebuilt image and overlay at runtime** — pull `rosettacommons/rfdiffusion` directly, bind-mount the fork source and a `uv`-managed venv for the extras. No image build at all. Fastest possible start; less self-contained and more moving parts at run time.

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

## Notes — decisions I will make without asking

- **AlphaFold parameters**: the notebook downloads the full ~4 GB tarball (monomer + multimer). Since
  `use_multimer` defaults off, staging will extract everything but the staging script will make the
  multimer set optional, with a documented flag — meaningful against a 100 GB `/home` quota.
- **`APPTAINER_CACHEDIR`**: set explicitly in both build and job scripts (G-18). Left at its default
  it grows silently in `/home`, which is the failure mode that bites people at exactly the wrong time.
- **Weight integrity**: staging script records checksums so a truncated download is detected at
  staging rather than mid-job.
- **`ananas` binary**: staged alongside the weights and verified executable at staging time, since
  `symmetry="auto"` is the only feature depending on it and it should degrade gracefully.

---

## Anything else?

[Answer]:
