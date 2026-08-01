# AI-DLC State Tracking

## Project Information
- **Project Name**: rfdiffusion-gui
- **Project Type**: Brownfield
- **Start Date**: 2026-07-30T22:57:31Z
- **Current Phase**: **CONSTRUCTION** (INCEPTION complete and fully approved)
- **Current Stage**: U1 Code Generation complete → next is U2a Core Domain

## ⚠️ Upstream Bit-Rot: `files.ipd.uw.edu/krypton/` is GONE (404, verified 2026-08-01)
Two assets the original notebook downloads no longer exist. `/pub/RFdiffusion/` still works.

| Asset | Impact | Resolution |
|---|---|---|
| `schedules.zip` | none | Diffuser computes and caches schedules on demand into `/scratch/schedules` |
| `ananas` | **`symmetry="auto"` unavailable** | Staging is best-effort and non-fatal; `RFD_ANANAS_URL` or manual placement re-enables it |

**Requirement impact — `symmetry="auto"` is conditionally available:**
- **U4**: the symmetry selector must detect whether `ananas` is present and, if not, disable the
  `auto` option with an explanatory note. `none` / `cyclic` / `dihedral` are unaffected.
- **U2b**: `SymmetryDetector` (C-12) must fail with a clear, actionable message when `auto` is
  requested without the binary — never a bare exception or a silent fallback to no symmetry.
- **Note**: the original notebook is now broken in these same two respects, so the Colab fallback
  has partially bit-rotted too.

## ⚠️ Constraint Carried Into U2b (from U1 build findings)
- **Runner must seed diffusion schedules before invoking `run_inference.py`.** The image ships a seed
  at `/opt/schedules-seed`; `/opt/RFdiffusion/schedules` is a symlink to `/scratch/schedules`
  (bound from `$TMPDIR`). The runner must `mkdir -p /scratch/schedules` and copy the seed in — the
  fork does `os.mkdir()` on that path at import, which raises `FileExistsError` on a dangling symlink,
  and it *writes* there for uncached `T` values, which a read-only SIF cannot satisfy.
- **The container's Python is `/app/RFdiffusion/.venv/bin/python`** (a uv venv), not `python3.9` on
  PATH in the usual sense. Anything invoking the interpreter explicitly must use that path.

## ⚠️ Constraints Carried Into U2a
- **`rfd-core` MUST target Python 3.9** (container base image). No `StrEnum` → `class X(str, Enum)`;
  no runtime PEP 604 unions → `Optional[...]` + `from __future__ import annotations`; no `match`.
- **`rfd-web` uses a uv-managed Python ≥3.11** — the login node's system `python3` is **3.6.8**.
- Partition selector must offer the CUDA-11.6-compatible set (`gpu`, `agpu`, `stamps-b`, `livi-b`,
  `mcordgpu-b`) and mark **`lgpu` incompatible** with the Phase 1 image (U3).
- Walltime limits are **per-partition** (`lgpu` = 3 d, others 7–21 d) — read from `sinfo`, never a
  constant (U3, FR-6a).

## U1 Infrastructure Decisions (Q1=D, Q2=A, Q3=A, Q4=A)
- **Phase 1**: one image `FROM rosettacommons/rfdiffusion` (CUDA 11.6 / torch 1.12.1+cu116 /
  dgl 1.0.2+cu116 / e3nn 0.3.3 / Python 3.9), targeting **`gpu` (V100) only**, with the
  **sokrypton fork** cloned in for `dump_pdb` and ColabDesign/JAX overlaid. Built on Grex `--fakeroot`.
- **Phase 2 deferred**: CUDA 12.x variant for `lgpu`. `RFD_IMAGE` is configurable, so swapping is a
  config change, not a code change.
- ⚠️ **RISK + PRE-PLANNED FALLBACK**: ColabDesign may need newer JAX than CUDA 11.6 allows (JAX cuda11
  wheels are off-PyPI, on the `jax-releases` index, and old). If verification step 6 fails, fall back
  to **two images** — torch and JAX run as sequential subprocesses, so differing CUDA versions in
  separate containers is not a conflict. No re-decision needed.
- ⚠️ **HARD CONSTRAINT ON U2a**: base image is **Python 3.9**, so **`rfd-core` must target 3.9** —
  no `StrEnum` (use `class X(str, Enum)`), no runtime PEP 604 unions (use `Optional[...]` plus
  `from __future__ import annotations`), no `match`. `rfd-web` is unconstrained.
- **e3nn 0.3.3, not 0.5.5** — the notebook used 0.5.5 only because Colab's newer torch required it;
  on torch 1.12 the inherited pin is the correct one.

## U1 Research Findings (2026-07-31)
1. **Official `rosettacommons/rfdiffusion` container exists but is unusable as-is.**
   `inference.dump_pdb` / `dump_pdb_path` exist **only in the sokrypton fork** — they are the entire
   mechanism behind FR-16 and FR-17. The official image cannot provide live progress.
   Its *pinned dependency set* is still valuable as a base.
2. **Two viable stacks, far apart**: official = CUDA 11.6 / torch 1.12.1+cu116 / dgl 1.0.2+cu116 /
   e3nn 0.3.3, **fully pinned and proven**; notebook = CUDA 12.4 / torch 2.4 / e3nn 0.5.5,
   **almost entirely unpinned**.
3. ⚠️ **The proven stack cannot run on `lgpu`.** `gpu` = V100 (sm_70), `lgpu` = L40s (**sm_89**).
   CUDA 11.6 predates Ada Lovelace (sm_89 needs ≥11.8), so torch 1.12.1+cu116 is **V100-only**.
   Supporting `lgpu` means resolving the CUDA 12.x stack ourselves — R-1/R-2 in full.

## Units (5, amended from 4 by Units Generation Q1=A)
| Unit | Package / dir | Depends on | Testable without cluster |
|---|---|---|---|
| **U1** Runtime and Container | `containers/`, `scripts/`, `docs/` | — | no |
| **U2a** Core Domain | `rfd-core` | — | **fully** |
| **U2b** Runner | `rfd-runner` | U1, U2a | partially |
| **U3** Slurm and Persistence | `rfd-web/{slurm,persistence,services}` | U2a, U1 (template) | with fake Slurm |
| **U4** Web Application | `rfd-web/{routes,templates,static}` | U2a, U3 | yes |

- **Milestone M1** "working CLI pipeline" after U1+U2a+U2b, verified by hand-written `sbatch`
- **Phase A parallelism**: U1 and U2a both start immediately — the largest schedule lever
- **U2a is deliberately OFF the critical path** — the point of the split

## Application Design Decisions
| Ref | Decision |
|---|---|
| DD-1 | `uv` **workspace, three packages**: `rfd-core` (pure), `rfd-runner` (GPU), `rfd-web` (login node). `rfd-web` → `rfd-core` only, resolver-enforced, keeping PyTorch out of the web env |
| DD-2 | Runner source **bind-mounted** into the container; image holds dependencies only (fast iteration) |
| DD-3 | Live frame published **every N steps, default 5, configurable** |
| DD-4 | **Separate `progress.json`** (volatile) from `run.json` (durable), both written atomically |
| DD-5 | Original notebook moved to **`reference/diffusion.py`**, unmodified (rollback path preserved) |
| DD-6 | **`current_frame.pdb` bridge** — resolves the FR-17 / G-11 conflict discovered during design: `$TMPDIR` is node-local to the compute node and invisible to the login-node web app, so per-step churn stays on scratch (G-11) while only the latest frame is atomically published to persistent storage |

## Execution Plan Summary
- **Units**: U1 Runtime and Container · U2 Core Domain and Runner · U3 Slurm Integration and
  Persistence · U4 Web Application
- **Critical path**: U1 → U2 → U3 → U4, with U1's *validation* deliberately overlapped onto U2's
  development window (U1 is highest-risk but independent; U2 is pure Python needing no cluster)
- **Stages to execute**: Application Design, Units Generation, Infrastructure Design (U1 only),
  Functional Design (U2 and U3 only), Code Generation (all 4 units), Build and Test
- **Stages to skip**: User Stories; NFR Requirements (all units); NFR Design (all units);
  Functional Design (U1, U4); Infrastructure Design (U2, U3, U4)
- **Risk level**: HIGH (R-1/R-2, the Apptainer GPU dependency stack)
- **Rollback**: EASY — `diffusion.py` is never modified and remains a working Colab fallback

## Confirmed Architectural Decisions
- **Runtime model**: **Submit-and-track** (user decision, 2026-07-30). The web app is launched
  independently of any run, submits Slurm batch jobs, tracks them, and survives both the browser
  closing and the 6-hour OpenOnDemand interactive cap.
- **Implications**: web app is GPU-free and PyTorch-free; run state must be persisted outside
  process memory; the app is a Slurm client (sbatch/squeue/sacct), not a compute process;
  two distinct environments are implied (light web app env + heavy RFdiffusion runtime env).

## Settled Requirements Decisions (Requirements Analysis)
| Ref | Decision |
|---|---|
| Q1 | **FastAPI + HTMX**, server-rendered, no Node toolchain; 3Dmol.js vendored as a single script |
| Q2a | Web app on a **Grex login node**, bound to `127.0.0.1`, reached via SSH tunnel with `ControlMaster` (Duo answered once interactively; tunnel reuses the master socket) |
| Q3 | **`uv`** for the web app project; **Apptainer** image for the RFdiffusion/JAX GPU runtime |
| Q4 | **Full pipeline, one click** — backbone generation + ProteinMPNN/AlphaFold validation |
| Q5 | **Full notebook-parity live progress** per job (step counter + live structure preview) |
| Q6 | **Single Slurm job running one program** (user's proposal, adopted). `contigs`/`copies` stay in-memory variables. Persistence = SQLite index on `/home` + `run.json` per run directory as the job→web-app status/progress/provenance channel. Runner takes `--stage {all,backbone,validate}` for retry. |
| Q7 | **Single user, no auth**; SSH login is the authentication |
| Q8 | **`/home`** for now, downside explicitly accepted; all paths configurable via env vars |
| Q9/10/11 | **B / B / B** — all extensions opted out; no blocking compliance gates |

## Binding Constraint: Grex Documentation Adherence
User constraint (2026-07-31): *"My only constraint is making sure https://um-grex.github.io/docs/
are very strongly adhered to."* Captured as requirements **G-1 through G-20** in requirements.md
section 5A. Execution model confirmed as ordinary **`sbatch` batch jobs** per
running-jobs/batch-jobs; the web app is a thin wrapper generating a conventional `#SBATCH` script,
introducing no alternative execution mechanism.

Key documented idioms now binding:
- `$TMPDIR` for per-job scratch (replaces the notebook's `/dev/shm`); `export SLURM_TMPDIR=$TMPDIR`
- Never emit `--qos=` (documented as "Not to be used on Grex!")
- Always explicit `--time`, `--mem-per-cpu`, `--gpus=`, `--partition=`
- GPU defaults from Grex's own template: `--gpus=1 --cpus-per-task=6 --mem-per-cpu=6000M`
- Container image pulled/built ahead of time, never at job start; `--nv` for GPU
- Partitions discovered at runtime — Grex's own pages disagree on GPU partition names

## Verified Grex Constraints
- Default walltime **3 hours** — `--time` must always be requested explicitly
- Max walltime **7 days on `gpu`** partition (21 days on CPU partitions) — ample for a single-job full pipeline
- General GPU capacity is small: **2 nodes in `gpu` (4x V100 32GB), 2 nodes in `lgpu` (2x L40s 48GB)** — this is why a chained second job was rejected: it would re-queue for a new allocation
- GPU-partition jobs are **rejected unless they request GPUs** (`--gpus=`)
- Grex MFA docs explicitly recommend `ControlMaster`/`ControlPersist` to cache Duo sessions

## Intent Analysis (Requirements Analysis Step 2)
- **Request Clarity**: Clear in intent, incomplete in detail
- **Request Type**: Migration (Colab notebook to standalone web app) + Upgrade (ad-hoc pip to uv)
- **Scope**: System-wide — effectively a rewrite preserving one core algorithm
- **Complexity**: Complex
- **Requirements Depth Selected**: **Comprehensive**

## Workspace State
- **Existing Code**: Yes
- **Programming Languages**: Python (single file: `diffusion.py`, Colab-exported notebook)
- **Build System**: None detected (no pyproject.toml, requirements.txt, package.json, setup.py)
- **Project Structure**: Single-script / notebook export (not a packaged application)
- **Reverse Engineering Needed**: Yes
- **Workspace Root**: /home/pieberrykinnie/rfdiffusion-gui

## User Objective
Port the Colab RFdiffusion notebook (`diffusion.py`) into:
1. A project managed by the **uv** package manager
2. A **lightweight web UI application**
3. Appropriate for deployment on the **Grex HPC cluster** (University of Manitoba)

## Target Environment Summary (Grex HPC)
- **Scheduler**: Slurm
- **GPU partitions**: `gpu` (2 nodes x 4x V100 32GB), `lgpu` (2 nodes x 2x L40s 48GB)
- **CPU partitions**: skylake, largemem, genoa, genlm, test
- **Web access**: OpenOnDemand (ood.hpc.umanitoba.ca), max 6h interactive walltime, MFA + VPN required
- **Python policy**: NO system-wide conda (Anaconda licensing); virtualenv + pip explicitly preferred
- **Containers**: Apptainer / Singularity-CE available, `--nv` for GPU passthrough
- **Modules**: CCEnv (Alliance stack) + SBEnv
- **Storage**: /home 100 GB per user; /project 5 TB per group (Lustre)

## Code Location Rules
- **Application Code**: Workspace root (NEVER in aidlc-docs/)
- **Documentation**: aidlc-docs/ only
- **Structure patterns**: See code-generation.md Critical Rules

## Extension Configuration
| Extension | Enabled | Decided At |
|---|---|---|
| security/baseline | **No** | Requirements Analysis (2026-07-30, user answered 9a=B) |
| resiliency/baseline | **No** | Requirements Analysis (2026-07-30, user answered 10a=B) |
| testing/property-based | **No** | Requirements Analysis (2026-07-30, user answered 11a=B) |

**Deferred rule loading**: all three extensions opted OUT, so their full rules files were NOT loaded
(`security-baseline.md`, `resiliency-baseline.md`, `property-based-testing.md`). No extension rules
are enforced as blocking constraints at any stage. Substantive protections remain in scope as
ordinary requirements — see NFR-11 through NFR-14 and FR-21 in requirements.md.

**User priority**: speed — *"I need this working ASAP"* (2026-07-30). This informs depth selection at
Workflow Planning and favours skipping optional stages.

## Stage Progress

## Reverse Engineering Status
- [x] Reverse Engineering - Artifacts generated on 2026-07-30T22:57:31Z (awaiting user approval)
- **Artifacts Location**: aidlc-docs/inception/reverse-engineering/
- **Artifacts**: business-overview.md, architecture.md, code-structure.md, api-documentation.md,
  component-inventory.md, interaction-diagrams.md, technology-stack.md, dependencies.md,
  code-quality-assessment.md, reverse-engineering-timestamp.md

## Key Reverse Engineering Findings (carried into Requirements Analysis)
- `diffusion.py` is a 6-cell Colab notebook export; cells 1, 2, 4 are commented out and are NOT
  executable Python as shipped. They hold the provisioning logic and every helper function.
- 7 business transactions identified (BT-1 provision, BT-2 generate backbone, BT-3 monitor progress,
  BT-4 review backbone, BT-5 design+validate sequence, BT-6 review best, BT-7 export).
- Core reusable asset: `run_diffusion()` (~120 lines) plus the contig mode-inference block.
  Everything else is provisioning, Colab glue, or notebook-bound presentation.
- Hard blockers for the port: `google.colab.files` (upload/download), `apt-get install aria2` (root),
  `dist-packages` symlink, cross-cell global state (`path`, `contigs`, `copies`, `num_designs`).
- Zero tests, zero linting, zero type hints, no dependency manifest or lockfile.
- Shared-cluster risks not present on Colab: shell injection via unsanitised parameters (TD-7),
  fixed `/dev/shm/{n}.pdb` paths colliding between concurrent users (TD-13).
- ~8 GB of model weights re-downloaded every Colab session; on Grex these become one-time staged
  assets that must live on `/project`, not `/home` (100 GB quota).

### INCEPTION PHASE
- [x] Workspace Detection - COMPLETED 2026-07-30T22:57:31Z
- [x] Reverse Engineering - COMPLETED and APPROVED 2026-07-30T23:10:00Z
- [x] Requirements Analysis - COMPLETED 2026-07-30T23:55:00Z (awaiting approval)
  - Artifacts: requirements.md, requirement-verification-questions.md,
    requirements-clarification-questions.md, requirements-clarification-questions-2.md
  - 24 functional requirements, 18 non-functional requirements, 12 constraints, 7 risks
- [x] Requirements Analysis - **APPROVED** 2026-07-31T00:25:00Z
- [x] User Stories - **SKIPPED** (offered at the Requirements approval gate; not requested)
- [x] Workflow Planning - COMPLETED 2026-07-31T00:25:00Z (awaiting approval)
  - Artifact: aidlc-docs/inception/plans/execution-plan.md
- [x] Application Design - **APPROVED** 2026-07-31T01:00:00Z
  - Artifacts: components.md, component-methods.md, services.md, component-dependency.md,
    application-design.md — 29 components, 4 services, 3 packages
  - Approval was conditional on notebook parameter parity; parity verified parameter-by-parameter,
    `visual` restored as `live_preview` (DD-7), condition met
- [x] Units Generation - COMPLETED 2026-07-31T01:10:00Z (awaiting approval)
  - Artifacts: unit-of-work.md, unit-of-work-dependency.md, unit-of-work-story-map.md
  - Plan: unit-of-work-plan.md (all checkboxes [x])

### CONSTRUCTION PHASE (per-unit loop over U1, U2a, U2b, U3, U4)
- [x] U1 Runtime and Container: Infrastructure Design **DONE** → Code Generation **DONE** 2026-07-31
      (Functional Design SKIP, NFR Requirements SKIP, NFR Design SKIP)
      - Artifacts: `containers/rfdiffusion.def`, `scripts/{preflight-grex,build-image,stage-weights,verify-image}.sh`,
        `env.example`, `docs/setup.md`, `reference/`, `.gitignore`
      - **Preflight verified on `yak`**: 16 PASS / 0 WARN / 0 FAIL
      - **Awaiting user execution on Grex**: build image → stage weights → verify on a GPU node
- [ ] U2a Core Domain: Functional Design **EXECUTE** → Code Generation **EXECUTE**
      (NFR Requirements SKIP, NFR Design SKIP, Infrastructure Design SKIP)
- [ ] U2b Runner: Functional Design **EXECUTE** → Code Generation **EXECUTE**
      (NFR Requirements SKIP, NFR Design SKIP, Infrastructure Design SKIP)
- [ ] **Milestone M1** — working CLI pipeline, verified by hand-written `sbatch` on a Grex GPU node
- [ ] U3 Slurm Integration and Persistence: Functional Design **EXECUTE** → Code Generation **EXECUTE**
      (NFR Requirements SKIP, NFR Design SKIP, Infrastructure Design SKIP)
- [ ] U4 Web Application: Code Generation **EXECUTE**
      (Functional Design SKIP, NFR Requirements SKIP, NFR Design SKIP, Infrastructure Design SKIP)
- [ ] Build and Test - **EXECUTE**

## Current Status
- **Lifecycle Phase**: INCEPTION (final stage)
- **Current Stage**: Units Generation Complete
- **Next Stage**: CONSTRUCTION PHASE — U1 Infrastructure Design
- **Status**: Awaiting units approval

### OPERATIONS PHASE
- [ ] Operations - PLACEHOLDER
