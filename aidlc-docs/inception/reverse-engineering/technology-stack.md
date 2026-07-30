# Technology Stack

## Programming Languages

| Language | Version | Usage |
|---|---|---|
| Python | 3.x (Colab default, implied 3.10/3.11) | Entire codebase |
| Shell (bash via `os.system`) | — | Provisioning, process launch, downloads, archiving |
| JavaScript (3Dmol.js) | loaded from `3dmol.org/build/3Dmol.js` | Browser-side 3D structure rendering, injected by py3Dmol |

## Frameworks and Libraries

| Library | Version | Purpose |
|---|---|---|
| **PyTorch** | unpinned — inherited from Colab image; DGL wheel choice implies **2.4 + CUDA 12.4** | Neural network execution |
| **DGL** | unpinned, installed `--no-dependencies` from `data.dgl.ai/wheels/torch-2.4/cu124` | Graph neural networks; backend set to pytorch via `DGLBACKEND` |
| **e3nn** | `0.5.5` (**the only pinned dependency**) | E(3)-equivariant neural network primitives |
| **opt_einsum_fx** | unpinned | Einsum optimisation for e3nn |
| **SE3Transformer** | vendored in `RFdiffusion/env/SE3Transformer` | SE(3)-equivariant attention |
| **RFdiffusion** | unpinned git clone (sokrypton fork) | The diffusion model |
| **ColabDesign** | unpinned git install (sokrypton) | Contig/PDB utilities, plotting, ProteinMPNN + AlphaFold designability harness |
| **hydra-core / omegaconf** | unpinned | RFdiffusion's configuration system (drives the CLI override syntax) |
| **JAX** | transitively via ColabDesign | AlphaFold and ProteinMPNN execution |
| **NumPy** | unpinned | Coordinate math in `run_ananas` |
| **matplotlib** | unpinned | Pseudo-3D renders and trajectory GIFs |
| **py3Dmol** | unpinned, **never explicitly installed** — assumed present in Colab | Interactive 3D visualization |
| **ipywidgets** | unpinned | Progress bar, output areas, design dropdown |
| **IPython** | Colab-provided | `display`, `HTML` |
| **google.colab** | Colab-only | `files.upload()`, `files.download()` |
| **dllogger** | git install (NVIDIA) | Logging dependency of SE3Transformer |
| **icecream, jedi, pyrsistent, pynvml, decorator** | unpinned | Transitive/utility requirements pulled in by Cell 1 |

## Infrastructure

| Component | Purpose |
|---|---|
| **Google Colab runtime** | Ephemeral Ubuntu VM with a single NVIDIA GPU, root access, and unrestricted internet |
| **`/dev/shm` (tmpfs)** | IPC channel for streaming per-timestep structure dumps |
| **`aria2c`** | 16-connection parallel downloader for the ~8 GB of model weights (installed via `apt-get`, i.e. **requires root**) |
| **`wget` / `gunzip` / `zip`** | Template fetching and result archiving |
| **`nohup`** | Detaching the inference process so the notebook can poll it |

## Build Tools

**None.** No build system, no packaging, no lockfile, no dependency manifest. Installation is imperative shell invoked at runtime from within application code.

## Testing Tools

**None.** No pytest, unittest, hypothesis, tox, nox, or CI configuration. No test files exist.

## Target Stack Gaps (Colab → Grex HPC)

Recorded here because these gaps define the porting work:

| Colab assumption | Grex reality | Implication |
|---|---|---|
| `apt-get install` (root) | No root | `aria2c` unavailable; use `curl`/`wget`, or module-provided tools |
| Runtime `pip install` into system site-packages | Per-user environments; **no system conda** (Anaconda licensing) | Aligns with the requested `uv` migration; needs a lockfile |
| Symlink into `/usr/local/lib/python3.*/dist-packages` | Not writable, not that layout | Must vendor or properly install ColabDesign |
| PyTorch/CUDA pre-installed | Provided via CCEnv modules (`cuda/12.2`, `cudnn`) or must be pinned in the lockfile | Torch/CUDA becomes an explicit, version-critical dependency |
| Unrestricted internet from compute node | Alliance wheel mirror available; general egress may be constrained | Weights must be pre-staged, not downloaded at job start |
| `google.colab.files` upload/download | Does not exist | Replace with HTTP file upload/download |
| `ipywidgets` progress bar | No notebook kernel in a web app | Replace with server-side job state + browser polling/SSE |
| Ephemeral VM, re-download every session | Persistent `/home` (100 GB) and `/project` (5 TB Lustre) | One-time ~8 GB weight staging; must live in `/project` |
| Long-running foreground process | Slurm batch/interactive jobs; **6 h cap on OpenOnDemand sessions** | Long designs need batch submission, not an interactive session |
| One GPU, always available | `gpu` partition (V100 32 GB) / `lgpu` (L40s 48 GB); queued | Job may wait; UI must handle PENDING state |
| Single concurrent run per machine | Shared multi-user cluster | `/dev/shm/{n}.pdb` fixed paths would collide — must be namespaced per run |
