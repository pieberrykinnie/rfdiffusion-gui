# Units of Work

**Five units**, following the Q1 = A split of the originally-approved U2.

**Terminology**: this is a **modular monolith**, not microservices. There is one deployable web
application plus one in-job program. "Unit of work" here means a unit of *development*, and units map
to workspace packages and directories rather than to independently deployable services.

---

## U1 — Runtime and Container

**Purpose**: Make RFdiffusion, ProteinMPNN and AlphaFold executable on a Grex GPU node, reproducibly.

**Why it exists as a unit**: it is the project's highest risk (R-1, R-2) and its only hard external
dependency. It is also completely independent of application code, which is what allows it to be
built first and validated *while other units proceed*.

**Responsibilities**
- Apptainer definition pinning the full GPU stack: torch + CUDA, DGL (from the CUDA wheel index),
  e3nn `0.5.5`, opt_einsum_fx, SE3Transformer, JAX, plus RFdiffusion and ColabDesign **at explicit
  commit SHAs** — the notebook pinned almost none of this
- The `ananas` binary
- Weight-staging procedure for the 3 RFdiffusion checkpoints, `schedules.zip`, and AlphaFold params
- Filesystem layout and `APPTAINER_CACHEDIR` handling
- The canonical `#SBATCH` job-script template satisfying G-1 … G-18
- Setup documentation: image build, weight staging, `uv sync`, SSH `ControlMaster` tunnel, launch

**Deliverables**: `containers/rfdiffusion.def` · `scripts/stage-weights.sh` ·
`scripts/build-image.sh` · job-script template · `docs/setup.md`

**Not a Python package.** Contributes no importable code.

**Definition of done**: `apptainer exec --nv <image> python RFdiffusion/run_inference.py --help`
succeeds on a Grex GPU node, and a trivial unconditional design completes.

**Stages**: Infrastructure Design → Code Generation

---

## U2a — Core Domain (`rfd-core`)

**Purpose**: The pure, dependency-free heart of the system — everything that can be reasoned about
and tested without a GPU, a cluster, or ColabDesign.

**Why it exists as a unit** (Q1 = A): it is the most testable code in the project and the most
valuable to get right, and it has **zero dependency on U1**. Separating it means it can be completed
and property-tested on day one, in parallel with the container build, instead of waiting behind the
riskiest dependency.

**Responsibilities**
- `ContigSpec` — syntactic contig parsing (C-1)
- `DesignModeInferrer` — `free` / `fixed` / `partial` (C-2) — the highest-value logic carried over
- `SymmetryResolver` (C-3), `IterationPlanner` (C-4)
- `InferenceArgvBuilder` (C-5) — argument lists, never shell strings
- Models: `DesignRequest` (C-6), `RunRecord` (C-7), `ProgressState` (C-8) — the file-format contracts
  shared between runner and web app
- `AtomicJsonStore` (C-9), `PathLayout` (C-10)
- The `uv` **workspace root**: `pyproject.toml`, `uv.lock`

**Deliverables**: `packages/rfd-core/` · workspace root config · unit and property test suite

**Constraint**: must remain importable with **no ColabDesign, no RFdiffusion, no PyTorch**. This is
what makes NFR-2 enforceable and FR-4's pre-submission mode preview possible.

**Definition of done**: full test suite passes on any machine with no cluster access; property tests
cover mode inference and argv assembly; all four notebook protocols produce correct Hydra overrides.

**Stages**: Functional Design → Code Generation

---

## U2b — Runner (`rfd-runner`)

**Purpose**: Execute the complete scientific pipeline inside the container, in one process.

**Responsibilities**
- `TemplateResolver` (C-11) — RCSB / AlphaFold DB / local / pre-uploaded, **no Colab upload path**
- `SymmetryDetector` (C-12) — AnAnaS invocation and asymmetric-unit extraction
- `ContigNormaliser` (C-13) — the only contig component importing ColabDesign
- `InferenceExecutor` (C-14) — `run_inference.py` via argument list, `$TMPDIR` dumps, `TER`
  completeness check, exit-code and stderr capture
- `FramePublisher` (C-15) — **the DD-6 bridge**; publishes `current_frame.pdb` every N steps, or not
  at all when `live_preview` is off
- `ProgressReporter` (C-16), `PdbPostProcessor` (C-17), `ValidationExecutor` (C-18),
  `ResultPackager` (C-19)
- `PipelineOrchestrator` (C-20) — `--stage {all,backbone,validate}`; holds `normalised_contigs` and
  `copies` **in memory** across stages (AD-5); guarantees a terminal `RunRecord` on every exit path

**Deliverables**: `packages/rfd-runner/`

**Definition of done**: `--stage all` completes a real design end to end inside the container on a
Grex GPU node, producing backbone PDBs, trajectories, validation outputs, and a terminal `run.json`.

**Stages**: Functional Design → Code Generation

---

## 🏁 Milestone M1 — Working CLI Pipeline (Q2 = A)

**After U1 + U2a + U2b, before any web code.**

Verified by writing a job script by hand and submitting it with plain `sbatch` on Grex. At this point
you have a usable command-line tool with no web interface.

**Why this milestone exists**: it isolates the failure modes that are hardest to diagnose later. If
the GPU stack, the container, the Grex job script, or the scientific pipeline is wrong, it surfaces
here with four components in play rather than through a web form with eight. It also means that if
the web work stalls for any reason, you still have something that works.

**Exit criteria**
1. Container runs `run_inference.py` on a Grex GPU node
2. A real design completes via `sbatch` with a hand-written script
3. The job script passes review against `https://um-grex.github.io/docs/` (G-1 … G-18)
4. `run.json`, `progress.json`, and `current_frame.pdb` are all written as specified
5. `rfd-core`'s test suite passes independently

---

## U3 — Slurm Integration and Persistence

**Purpose**: Turn the CLI pipeline into something submittable and trackable from a program.

**Responsibilities**
- `SlurmAdapter` (C-21) — `sbatch`/`squeue`/`sacct`/`scancel`/`sinfo` behind a `Protocol` so it can
  be faked in tests (NFR-18)
- `PartitionDiscovery` (C-22) — runtime discovery; **never** a hard-coded partition list (FR-6a)
- `JobScriptGenerator` (C-23) — programmatic emission of U1's template, retained in the run directory
  so every run is hand-resubmittable (G-2)
- `RunRepository` (C-24) — SQLite index on `/home`
- `RunDirectoryReader` (C-25) — reads the `rfd-core` contracts plus outputs and log tail
- `S-2 RunQueryService` — **state reconciliation across SQLite, `run.json`, `progress.json`, and live
  Slurm**, including the rule that a terminal Slurm state with a non-finalised `run.json` is reported
  as failure, never success

**Deliverables**: `packages/rfd-web/src/rfd_web/slurm/` · `persistence/` · `services/`

**Definition of done**: a run can be submitted, tracked to completion, and cancelled
programmatically; the full suite passes against a fake Slurm with no cluster access.

**Stages**: Functional Design → Code Generation

---

## U4 — Web Application

**Purpose**: The visible deliverable.

**Responsibilities**
- `RequestValidator` (C-26) — rejects bad input **before** a job is queued (FR-5, G-9)
- `TemplateUploadHandler` (C-27)
- `Routes` (C-28) — 15 endpoints; submission form, run list, run detail, HTMX status polling,
  structure/frame/trajectory endpoints, downloads, cancel, clone, contig help
- `ViewerAssets` (C-29) — **vendored** 3Dmol.js, rainbow / chain / pLDDT colouring, trajectory
  animation, best-design overlay
- `S-1 SubmissionService`, `S-3 ResultService`
- Jinja2 templates and HTMX wiring; localhost-only binding

**Deliverables**: `packages/rfd-web/src/rfd_web/routes/` · `templates/` · `static/` · `services/`

**Definition of done**: one click submits a job; live progress and structures render in-browser;
results download; restarting the app loses nothing.

**Stages**: Code Generation only

---

## Code Organization Strategy

`uv` workspace, three packages, five units. Units map to directories, not to deployables:

```
rfdiffusion-gui/
├── pyproject.toml              # U2a — workspace root
├── uv.lock                     # U2a — committed
├── packages/
│   ├── rfd-core/               # U2a
│   ├── rfd-runner/             # U2b
│   └── rfd-web/
│       └── src/rfd_web/
│           ├── slurm/          # U3
│           ├── persistence/    # U3
│           ├── services/       # U3 (S-2), U4 (S-1, S-3)
│           ├── routes/         # U4
│           ├── templates/      # U4
│           └── static/         # U4
├── containers/                 # U1
├── scripts/                    # U1
├── docs/                       # U1
├── reference/diffusion.py      # DD-5 — unmodified original
└── aidlc-docs/
```

**Deployment model**: two runtime artifacts —
1. the web app, run by the user on a Grex login node in a `uv`-managed venv (no GPU, no PyTorch);
2. the runner, executed by Slurm inside the Apptainer image with its source **bind-mounted** (DD-2).

**Why U3 and U4 share a package**: both are login-node code with identical dependencies. Splitting
them into separate distributions would add packaging overhead with no boundary benefit — the boundary
that matters (`rfd-web` must never depend on `rfd-runner`) is already enforced between packages.

---

## Summary

| Unit | Package / dir | Depends on | Testable without cluster | Stages |
|---|---|---|---|---|
| **U1** Runtime and Container | `containers/`, `scripts/`, `docs/` | — | ✗ | Infra Design → Code Gen |
| **U2a** Core Domain | `rfd-core` | — | **✓ fully** | Functional Design → Code Gen |
| **U2b** Runner | `rfd-runner` | U1, U2a | partially | Functional Design → Code Gen |
| **U3** Slurm and Persistence | `rfd-web/{slurm,persistence,services}` | U2a | **✓ with fake Slurm** | Functional Design → Code Gen |
| **U4** Web Application | `rfd-web/{routes,templates,static}` | U2a, U3 | ✓ | Code Gen |

Then **Build and Test** across all units.
