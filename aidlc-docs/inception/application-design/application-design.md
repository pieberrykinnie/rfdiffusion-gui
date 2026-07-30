# Application Design — Consolidated

**Stage**: INCEPTION — Application Design
**Depth**: Lean
**Date**: 2026-07-31

Consolidates [components.md](components.md), [component-methods.md](component-methods.md),
[services.md](services.md), and [component-dependency.md](component-dependency.md).

---

## 1. Design Decisions Taken This Stage

| Ref | Decision | Answer |
|---|---|---|
| **DD-1** | `uv` **workspace with three packages** — `rfd-core` (pure), `rfd-runner` (GPU), `rfd-web` (login node) | Q1 = A |
| **DD-2** | Runner source **bind-mounted** into the container; the image holds dependencies only | Q2 = A |
| **DD-3** | Live frame published **every N steps (default 5, configurable)** | Q3 = B |
| **DD-4** | Progress in a **separate atomically-written `progress.json`**, distinct from durable `run.json` | Q4 = A |
| **DD-5** | Original notebook moved to **`reference/diffusion.py`**, unmodified | Q5 = A |
| **DD-6** | **`current_frame.pdb` bridge** resolving the FR-17 / G-11 conflict | design finding, accepted |
| **DD-7** | **Full notebook parameter parity** — all 20 scientific parameters carried across, including `visual` restored as a `live_preview` toggle. Display-only parameters become viewer controls; `dpi` dropped as inapplicable to client-side rendering. See §5A. | user review |

### DD-6 in brief

FR-17 (live 3D preview) and G-11 (`$TMPDIR` for per-step dumps) could not both be satisfied as
written: `$TMPDIR` is node-local to the compute node, and the web app runs on a login node that
cannot see it. Resolution: per-step churn stays on node-local scratch as G-11 requires, and the
runner publishes **only the latest frame** to persistent storage as a single atomically-replaced
file. Both requirements are met; shared-filesystem traffic stays minimal.

---

## 2. Target Repository Layout

```
rfdiffusion-gui/
├── pyproject.toml              # uv workspace root
├── uv.lock                     # committed (NFR-1)
├── packages/
│   ├── rfd-core/               # pure: no torch, no colabdesign
│   │   └── src/rfd_core/
│   │       ├── contigs.py      # C-1, C-2
│   │       ├── symmetry.py     # C-3
│   │       ├── iterations.py   # C-4
│   │       ├── argv.py         # C-5
│   │       ├── models.py       # C-6, C-7, C-8
│   │       ├── storage.py      # C-9
│   │       └── paths.py        # C-10
│   ├── rfd-runner/             # GPU, inside container
│   │   └── src/rfd_runner/
│   │       ├── template.py     # C-11
│   │       ├── ananas.py       # C-12
│   │       ├── normalise.py    # C-13
│   │       ├── inference.py    # C-14
│   │       ├── publish.py      # C-15, C-16
│   │       ├── postprocess.py  # C-17
│   │       ├── validate.py     # C-18
│   │       ├── package.py      # C-19
│   │       └── __main__.py     # C-20
│   └── rfd-web/                # login node
│       └── src/rfd_web/
│           ├── slurm/          # C-21, C-22, C-23   (U3)
│           ├── persistence/    # C-24, C-25         (U3)
│           ├── services/       # S-1, S-2, S-3
│           ├── routes/         # C-28
│           ├── templates/      # Jinja2 + HTMX
│           └── static/         # vendored 3Dmol.js  (C-29)
├── containers/
│   └── rfdiffusion.def         # Apptainer definition (U1)
├── scripts/
│   ├── stage-weights.sh        # U1
│   └── build-image.sh          # U1
├── reference/
│   └── diffusion.py            # unmodified Colab original (DD-5)
└── aidlc-docs/
```

---

## 3. Component Summary

**29 components across three packages.** Full detail in [components.md](components.md).

### `rfd-core` (10) — pure domain and shared contracts
`ContigSpec` · `DesignModeInferrer` · `SymmetryResolver` · `IterationPlanner` ·
`InferenceArgvBuilder` · `DesignRequest` · `RunRecord` · `ProgressState` · `AtomicJsonStore` ·
`PathLayout`

*Constraint*: importable without ColabDesign, RFdiffusion, or PyTorch — this is what lets the web app
show the inferred design mode before submission (FR-4) while staying light (NFR-2).

### `rfd-runner` (10) — in-job pipeline
`TemplateResolver` · `SymmetryDetector` · `ContigNormaliser` · `InferenceExecutor` ·
`FramePublisher` · `ProgressReporter` · `PdbPostProcessor` · `ValidationExecutor` ·
`ResultPackager` · `PipelineOrchestrator`

### `rfd-web` (9) — login-node application
`SlurmAdapter` · `PartitionDiscovery` · `JobScriptGenerator` · `RunRepository` ·
`RunDirectoryReader` · `RequestValidator` · `TemplateUploadHandler` · `Routes` · `ViewerAssets`

---

## 4. Services

| Service | Package | Responsibility |
|---|---|---|
| **S-1 `SubmissionService`** | `rfd-web` | Validate → create run dir → generate script → `sbatch` → persist |
| **S-2 `RunQueryService`** | `rfd-web` | Reconcile SQLite + `run.json` + `progress.json` + Slurm into one truthful view |
| **S-3 `ResultService`** | `rfd-web` | Locate and stream artifacts, path-confined to the run directory |
| **S-4 `PipelineService`** | `rfd-runner` | Execute the whole pipeline in one process, contigs held in memory |

Services are **stateless** and never call each other. All state lives in the run directory and SQLite,
which is what lets the web app restart without losing a running job (FR-29).

The one piece of genuinely subtle logic is **S-2's reconciliation**: when Slurm reports a terminal
state but `run.json` was never finalised, the runner died before recording its outcome — that must be
reported as failure with the log tail, never as success. Concentrating this in one service is what
keeps the status display honest.

---

## 5. Key Boundaries

| Boundary | Why it matters |
|---|---|
| `rfd-web` **never** depends on `rfd-runner` | Keeps PyTorch out of the login-node environment (NFR-2), enforced by the workspace resolver rather than by discipline |
| Pure contig logic in `rfd-core`, ColabDesign-dependent normalisation in `rfd-runner` | Lets mode inference run in the browser-facing path and be property-tested with no cluster (NFR-17) |
| All Slurm access behind the `SlurmAdapter` `Protocol` | Makes the app testable without a cluster (NFR-18) |
| Runner and web communicate **only** through `rfd-core`-defined file formats | They are different processes on different nodes; neither may own the contract alone |
| Run directory has exactly one writer at a time | Web writes at submission; runner writes during execution. Windows never overlap, so no locking is needed |

---

## 5A. Notebook Parameter Parity

Verified parameter-by-parameter against `reference/diffusion.py`. **All 20 scientific parameters are
carried across.**

### Cell 2 — RFdiffusion (13 of 13)

| Notebook `#@param` | Web form field | Note |
|---|---|---|
| `name` | `name` | |
| `contigs` | `contigs` | plus live inferred-mode preview (FR-4), which the notebook lacked |
| `pdb` | `pdb` | plus browser upload, replacing `files.upload()` |
| `iterations` | `iterations` | same choices (25/50/100/150/200) |
| `hotspot` | `hotspot` | |
| `num_designs` | `num_designs` | same choices (1/2/4/8/16/32) |
| `visual` | `live_preview` | **restored**; boolean toggle. The notebook's three values were `none` / `image` / `interactive`, but `image` vs `interactive` chose the *renderer* — here rendering is always client-side 3Dmol, so only the on/off distinction carries meaning |
| `symmetry` | `symmetry` | same choices |
| `order` | `order` | 1–12 |
| `chains` | `chains` | |
| `add_potential` | `add_potential` | |
| `partial_T` | `partial_T` | same choices, now validated (fixes TD-11) |
| `use_beta_model` | `use_beta_model` | |

### Cell 4 — ProteinMPNN / AlphaFold (7 of 7)

| Notebook `#@param` | Web form field |
|---|---|
| `num_seqs` | `num_seqs` |
| `mpnn_sampling_temp` | `mpnn_sampling_temp` |
| `rm_aa` | `rm_aa` |
| `use_solubleMPNN` | `use_soluble_mpnn` |
| `initial_guess` | `initial_guess` |
| `num_recycles` | `num_recycles` |
| `use_multimer` | `use_multimer` |

### Cell 3 — display parameters → viewer controls, not submission inputs

| Notebook `#@param` | Disposition |
|---|---|
| `animate` | **Viewer control** on the results page (FR-23). In the notebook this was a cell parameter re-run after the fact; it never influenced the design, so it does not belong in the design request. |
| `color` | **Viewer control** (FR-22) — rainbow / chain / pLDDT. |
| `dpi` | **Dropped.** It existed solely to size matplotlib-rendered GIF animations. With client-side 3Dmol rendering there is no server-side raster step for it to control. |

### Added — Slurm submission (no notebook equivalent)

`partition`, `account`, `walltime`, `gpus`, `cpus_per_task`, `mem_per_cpu` — required by Grex
(G-4, G-5, G-6) and defaulted per Grex's documented GPU guidance (FR-6).

---

## 6. Requirements Traceability

| Requirement area | Realised by |
|---|---|
| FR-1, FR-2 submission form | C-6, C-28 |
| FR-3 template input | C-11, C-27 |
| FR-4 mode preview | C-1, C-2, C-26 — pure, no cluster |
| FR-5 validation | C-26, S-1 (rejects before any resource is consumed) |
| FR-6, FR-6a Slurm params, partition discovery | C-22, C-23 |
| FR-8 one click | S-1 → S-4 |
| FR-9, FR-12 single job, preserved logic | C-20, S-4 |
| FR-11 `--stage` retry | C-20 |
| FR-13 `$TMPDIR` scratch | C-14, C-15 |
| FR-14 cancel | C-21, C-28 |
| FR-15–FR-20 progress and status | C-8, C-16, C-25, S-2 |
| FR-17 live preview | **C-15 (DD-6)** |
| FR-21–FR-26 visualization | C-29, C-25, S-3 |
| FR-27–FR-30 run management | C-7, C-24, C-25 |
| FR-31–FR-33 export | C-19, S-3 |
| FR-34, FR-35 help and docs | C-28, U1 deliverables |
| NFR-1–NFR-3 packaging | DD-1, workspace layout |
| NFR-11 argument lists | C-5, C-14, C-18, C-21 — no shell anywhere |
| NFR-17 testability | C-1 … C-5 pure |
| NFR-18 fakeable Slurm | C-21 `Protocol` |
| G-1–G-12 job script conformance | C-23 |
| G-11, G-13 scratch and stage-out | C-14, C-15, C-19 |
| G-15–G-18 containers | C-23, U1 |

---

## 7. Deferred to Functional Design

Deliberately **not** settled here, per the lean-depth decision:

- **U2**: exact contig grammar edge cases; `fix_contigs` vs `fix_partial_contigs` selection rules;
  AnAnaS JSON parsing detail; the precise Hydra override ordering and quoting of the guiding-potential
  list; property-test invariants.
- **U3**: SQLite schema and migration approach; the full `run.json` / `progress.json` field list and
  versioning; `squeue`/`sacct` output parsing; the complete S-2 state reconciliation table.

Nothing in `rfd-web`'s presentation layer or `U1`'s container needs a functional design pass — the
former follows from the requirements, the latter is covered by Infrastructure Design.
