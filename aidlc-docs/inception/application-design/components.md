# Components

**Depth**: Lean — component boundaries, responsibilities and interfaces. Detailed business logic is
deferred to Functional Design (U2, U3).

---

## Packaging Structure (Q1 = A)

A single `uv` **workspace** with three member packages:

| Package | Environment | Heavy dependencies | Runs on |
|---|---|---|---|
| **`rfd-core`** | both | **none** — pure Python + `pydantic` | everywhere |
| **`rfd-runner`** | container | torch, CUDA, DGL, e3nn, JAX, RFdiffusion, ColabDesign | GPU compute node |
| **`rfd-web`** | login node | `fastapi`, `uvicorn`, `jinja2` | login node |

`rfd-web` depends on `rfd-core` **only**. This makes NFR-2 ("no PyTorch in the web app environment")
a property the resolver enforces, not a convention someone has to remember.

### Unit → Package mapping

Units are units of *work*; packages are units of *deployment*. They do not map one-to-one:

| Unit | Package(s) |
|---|---|
| U1 Runtime and Container | `containers/` definition files + `scripts/` (no Python package) |
| U2 Core Domain and Runner | `rfd-core` + `rfd-runner` |
| U3 Slurm Integration and Persistence | `rfd-web` (`slurm/`, `persistence/` modules) + models in `rfd-core` |
| U4 Web Application | `rfd-web` (`routes/`, `templates/`, `static/`) |

U3 lives in `rfd-web` because it is login-node code needing no GPU. The *file-format contract*
(`run.json`, `progress.json`) lives in `rfd-core` because the runner writes it and the web app reads
it — neither may own it alone.

---

## `rfd-core` — Shared Domain (pure)

The constraint that shapes this package: **everything here must be importable without ColabDesign,
RFdiffusion, or PyTorch**, because the web app imports it. Anything requiring those libraries belongs
in `rfd-runner`.

### C-1 `ContigSpec`
- **Purpose**: Parse and represent a contig string.
- **Responsibilities**: Split on `,` `:` whitespace then `/`; classify each segment as *fixed*
  (leading alphabetic, e.g. `A163-181`) or *free* (numeric, e.g. `100` or a range `70-100`);
  expose segments, referenced chains, and validity.
- **Interface**: constructed from a raw string; exposes `segments`, `fixed_chains`, `has_free`,
  `has_fixed`, `is_empty`.
- **Note**: Purely syntactic — no PDB access. This is what makes FR-4's pre-submission preview
  possible in the web app.

### C-2 `DesignModeInferrer`
- **Purpose**: Derive the RFdiffusion protocol from a `ContigSpec`.
- **Responsibilities**: Apply the notebook's rule (FR-12): no free segment ⇒ `partial`; free + fixed ⇒
  `fixed`; free only ⇒ `free`.
- **Interface**: `ContigSpec → DesignMode`.
- **Note**: The single highest-value pure function in the project and the primary property-test
  target (NFR-17).

### C-3 `SymmetryResolver`
- **Purpose**: Resolve symmetry settings into an RFdiffusion symmetry group and copy count.
- **Responsibilities**: `cyclic(n) → ("c{n}", n)`; `dihedral(n) → ("d{n}", 2n)`; `none` → `(None, 1)`;
  `auto` → deferred (resolved by the runner via AnAnaS, since it needs the template).
- **Interface**: `(symmetry, order) → SymmetryPlan`.

### C-4 `IterationPlanner`
- **Purpose**: Compute the diffusion step count and which Hydra key carries it.
- **Responsibilities**: For `partial` mode with `partial_T="auto"` ⇒ `int(80 * iterations / 200)`,
  else `int(partial_T)`, emitted as `diffuser.partial_T`; otherwise `iterations` as `diffuser.T`.
  Validates that `partial_T` is numeric (fixing TD-11).
- **Interface**: `(mode, iterations, partial_T) → IterationPlan`.

### C-5 `InferenceArgvBuilder`
- **Purpose**: Assemble the RFdiffusion invocation as an **argument list**.
- **Responsibilities**: Build the ordered `list[str]` of Hydra overrides from an already-normalised
  contig list plus mode, symmetry plan, iteration plan, hotspots, beta-model flag, scratch dump path,
  and output prefix. Never produces a shell string (NFR-11, eliminating TD-7).
- **Interface**: `(request, normalised_contigs, plans, paths) → list[str]`.
- **Note**: Takes contigs **already normalised**. Normalisation needs ColabDesign and therefore lives
  in the runner — this split is what keeps the builder pure and unit-testable.

### C-6 `DesignRequest` (model)
- **Purpose**: The validated design parameters (FR-1, FR-2).
- **Responsibilities**: Carry all RFdiffusion and ProteinMPNN/AlphaFold parameters with types and
  range validation (FR-5) — replacing the notebook's total absence of validation (TD-12).

### C-7 `RunRecord` (model) — `run.json` contract
- **Purpose**: The durable per-run record.
- **Responsibilities**: Identity, submitted `DesignRequest`, inferred mode, **normalised contigs**,
  **copies**, Slurm job id, per-stage state, timestamps, output paths, error detail. Defines the
  serialisation format both the runner (writer) and the web app (reader) obey.

### C-8 `ProgressState` (model) — `progress.json` contract (Q4 = A)
- **Purpose**: The volatile progress snapshot, kept separate from `RunRecord`.
- **Responsibilities**: Current stage, design index, current step, total steps, latest published
  frame path, timestamp. Deliberately separate so a partial or stale progress write can never damage
  the durable record.

### C-9 `AtomicJsonStore`
- **Purpose**: Crash-safe small-file JSON I/O.
- **Responsibilities**: Write via temp file + `os.replace`; read tolerating a concurrent write.
  Used for both `run.json` and `progress.json`, and by the frame publisher.

### C-10 `PathLayout`
- **Purpose**: Resolve all configurable filesystem locations (NFR-6, G-18).
- **Responsibilities**: Read env vars for weights root, image path, cache dir, output root, database
  path; default to `/home`; derive per-run directory structure.

---

## `rfd-runner` — In-Job Pipeline (GPU, inside container)

Bind-mounted into the container at runtime (Q2 = A) — the image supplies dependencies, not this code.

### C-11 `TemplateResolver`
- **Purpose**: Obtain a template structure (FR-3), replacing the notebook's `get_pdb`.
- **Responsibilities**: Local path pass-through; 4-character code ⇒ RCSB `.pdb1`; otherwise ⇒
  AlphaFold DB; pre-uploaded file from the run directory. **No `google.colab.files` branch** — upload
  is handled by the web app before submission (TD-2 removed).

### C-12 `SymmetryDetector`
- **Purpose**: Detect symmetry and reduce to the asymmetric unit (`run_ananas` equivalent).
- **Responsibilities**: Invoke the `ananas` binary via argument list, parse JSON, apply `sym_it` per
  group type, rebuild ATOM records. Distinguishes "no symmetry detected" from "detector failed"
  (NFR-12, fixing TD-8).

### C-13 `ContigNormaliser`
- **Purpose**: Produce normalised contigs — the ColabDesign-dependent step.
- **Responsibilities**: `parse_pdb` the template, then `fix_contigs` or `fix_partial_contigs` by mode;
  replicate by symmetry copy count. **The only component that must import ColabDesign for contig work.**

### C-14 `InferenceExecutor`
- **Purpose**: Run `run_inference.py` and observe it.
- **Responsibilities**: Launch via `subprocess` with an argument list (no shell); dump per-step PDBs
  to `$TMPDIR` (G-11); detect step completion by trailing `TER`; capture stderr and check the exit
  code (NFR-13); surface failure distinctly from completion.

### C-15 `FramePublisher`
- **Purpose**: Bridge node-local scratch to the login node — **the fix for the FR-17 / G-11 conflict**.
- **Responsibilities**: Every N steps (default 5, configurable — Q3 = B), copy the current
  `$TMPDIR` frame to `<run_dir>/current_frame.pdb` atomically via `AtomicJsonStore`'s replace
  semantics. Bulk trajectory data never crosses to shared storage mid-run.

### C-16 `ProgressReporter`
- **Purpose**: Publish `progress.json`.
- **Responsibilities**: Update step counts every step (cheap), frame path every N steps; write
  atomically.

### C-17 `PdbPostProcessor`
- **Purpose**: Apply `fix_pdb` to outputs and trajectories (FR-12).
- **Responsibilities**: Rewrite each final and trajectory PDB so numbering matches requested contigs.

### C-18 `ValidationExecutor`
- **Purpose**: Run ProteinMPNN + AlphaFold designability (BT-5).
- **Responsibilities**: Build the `designability_test.py` argument list from in-memory normalised
  contigs and copies — **no file handoff needed**, they are ordinary variables in the same process
  (AD-5); execute; check exit code.

### C-19 `ResultPackager`
- **Purpose**: Stage outputs out of `$TMPDIR` and archive (G-13, FR-31).
- **Responsibilities**: Ensure all durable artifacts are on persistent storage before job end; build
  the result zip.

### C-20 `PipelineOrchestrator`
- **Purpose**: The runner entry point — the in-process equivalent of the notebook's cell sequence.
- **Responsibilities**: Honour `--stage {all,backbone,validate}` (FR-11); drive C-11 → C-19 in order;
  keep `normalised_contigs` and `copies` in memory across stages; write `RunRecord` at start and
  completion; guarantee a terminal state is recorded even on failure.

---

## `rfd-web` — Login-Node Application

### C-21 `SlurmAdapter`
- **Purpose**: The only component that talks to Slurm (NFR-18).
- **Responsibilities**: `sbatch`, `squeue`, `sacct`, `scancel`, `sinfo` via argument lists; parse
  output; map to domain states. Isolated behind an interface so it can be faked in tests.

### C-22 `PartitionDiscovery`
- **Purpose**: Enumerate partitions at runtime (FR-6a).
- **Responsibilities**: Query `sinfo`/`partition-list` and identify GPU-capable partitions. Never
  hard-codes names — Grex's own documentation is inconsistent about them (C-4d).

### C-23 `JobScriptGenerator`
- **Purpose**: Emit the `#SBATCH` script (G-1 … G-12).
- **Responsibilities**: Render a script following Grex's documented template shape: `#!/bin/bash`,
  directive block with explicit `--time`, `--mem-per-cpu`, `--gpus`, `--partition`, `--cpus-per-task`;
  **never `--qos=`** (G-3); `cd ${SLURM_SUBMIT_DIR}`; `export SLURM_TMPDIR=$TMPDIR`;
  `module load singularity`; `apptainer exec --nv --bind …`; start/finish echo lines with exit code.
  Writes the script into the run directory so it is inspectable and hand-resubmittable (G-2).

### C-24 `RunRepository`
- **Purpose**: SQLite index of runs (AD-6).
- **Responsibilities**: Insert on submission; update terminal state; list and query for the run-list
  UI. Database lives on `/home`, never Lustre.

### C-25 `RunDirectoryReader`
- **Purpose**: Read the runner's output contract.
- **Responsibilities**: Load `run.json` and `progress.json` via `rfd-core` models; locate output PDBs,
  trajectories, `best.pdb`, `current_frame.pdb`; tail the job log for FR-19.

### C-26 `RequestValidator`
- **Purpose**: Reject bad input **before** a job is queued (FR-5, G-9).
- **Responsibilities**: Validate `DesignRequest`; parse contigs and report the inferred mode back to
  the user (FR-4); check ranges and template identifier plausibility. Keeps GPU allocations from
  being consumed by input that was never going to work.

### C-27 `TemplateUploadHandler`
- **Purpose**: Accept a browser-uploaded structure (FR-3).
- **Responsibilities**: Persist the upload into the run directory; enforce size/extension limits.

### C-28 `Routes`
- **Purpose**: HTTP surface (FastAPI).
- **Responsibilities**: Submission form and POST; run list; run detail with HTMX status polling;
  frame/structure endpoints; download endpoints; cancel; in-app contig help (FR-34).

### C-29 `ViewerAssets`
- **Purpose**: Client-side 3D rendering (FR-21).
- **Responsibilities**: Vendored 3Dmol.js and templates implementing rainbow / by-chain / by-pLDDT
  colouring, trajectory animation, and the best-design overlay. **No external CDN fetch** — the
  notebook's dependency on `3dmol.org` at render time is removed.

---

## Component Count

| Package | Components |
|---|---|
| `rfd-core` | 10 (C-1 … C-10) |
| `rfd-runner` | 10 (C-11 … C-20) |
| `rfd-web` | 9 (C-21 … C-29) |
| **Total** | **29** |
