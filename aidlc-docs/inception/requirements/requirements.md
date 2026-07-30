# Requirements — RFdiffusion Web UI for Grex HPC

**Depth**: Comprehensive
**Date**: 2026-07-30
**Status**: Awaiting approval

---

## 1. Intent Analysis Summary

| Aspect | Assessment |
|---|---|
| **User Request** | *"Let's port the content of this notebook to use the `uv` package manager and become a lightweight web UI application that is appropriate for use with https://um-grex.github.io/docs/grex/"* |
| **Request Type** | **Migration** (Colab notebook → standalone web application) combined with **Upgrade** (ad-hoc runtime `pip install` → `uv`-managed, locked dependencies) |
| **Scope** | **System-wide** — effectively a rewrite that preserves one core algorithm |
| **Complexity** | **Complex** — HPC target, Slurm integration, two distinct runtime environments, a notoriously version-sensitive GPU dependency stack, and a multi-user execution context the original never contemplated |
| **Requirements Depth** | **Comprehensive** |
| **Overriding user priority** | **Speed** — *"I need this working ASAP"* |

### Source system

`diffusion.py`: a 6-cell Colab notebook export of the ColabDesign RFdiffusion example. Cells 1, 2 and
4 are commented out by Colab's `%%time` exporter, so the file is **not executable Python as shipped**.
Roughly 120 lines — `run_diffusion()` plus the contig mode-inference block — constitute the real
intellectual content; everything else is provisioning, Colab glue, or notebook-bound presentation.
See `aidlc-docs/inception/reverse-engineering/` for the full analysis.

---

## 2. Architectural Decisions (settled)

| Ref | Decision | Rationale |
|---|---|---|
| **AD-1** | **Submit-and-track** model | The web app is launched independently of any run, submits Slurm batch jobs, and survives both the browser closing and Grex's 6-hour OpenOnDemand cap. |
| **AD-2** | **FastAPI + HTMX**, server-rendered | No Node toolchain, no bundler, no JS build step. Smallest thing that satisfies "lightweight" on a cluster node. |
| **AD-3** | Web app on a **Grex login node**, bound to `127.0.0.1`, reached by SSH tunnel | The app is I/O-light — it shells out to `sbatch`/`squeue` and serves small HTML pages. SSH login is the authentication. |
| **AD-4** | **`uv`** manages the web app project; **Apptainer** image supplies the GPU runtime | Quarantines the fragile torch/CUDA/DGL/JAX stack inside an image while `uv` cleanly manages everything actually maintained by hand. |
| **AD-5** | **One Slurm job runs the entire pipeline** as a single program | Grex's general GPU capacity is 2 nodes in `gpu` + 2 in `lgpu`. A `--dependency=afterok` second job would return to `PENDING` and wait for a *new* allocation — potentially hours of dead time mid-run. One job = one queue wait. Also keeps `contigs`/`copies` as in-memory variables, exactly as the notebook had them. |
| **AD-6** | **SQLite index + per-run `run.json`** | SQLite answers the run-list UI. `run.json` is the job → web app channel for status, progress and provenance — required because the job and the app are separate processes on different nodes. |
| **AD-7** | **Single user, no authentication** | Bound to localhost behind the user's own SSH tunnel; no auth surface, no sensitive data. |
| **AD-8** | All filesystem paths **configurable via environment variables**, defaulting to `/home` | User chose `/home` and accepted the quota tradeoff; configurability makes relocation to `/project` a config change rather than a code change. |

---

## 3. Functional Requirements

### 3.1 Design Submission

| ID | Requirement | Priority |
|---|---|---|
| **FR-1** | Provide a web form exposing every RFdiffusion parameter the notebook exposed: `contigs`, `pdb`, `iterations`, `hotspot`, `num_designs`, `symmetry`, `order`, `chains`, `add_potential`, `partial_T`, `use_beta_model`, plus a run `name`. | Must |
| **FR-2** | Provide the ProteinMPNN and AlphaFold parameters in the same form: `num_seqs`, `mpnn_sampling_temp`, `rm_aa`, `use_solubleMPNN`, `initial_guess`, `num_recycles`, `use_multimer`. | Must |
| **FR-3** | Accept a template structure by **PDB code** (4 characters → RCSB `.pdb1`), **UniProt accession** (→ AlphaFold DB), **server-side path**, or **browser file upload**. Upload replaces the notebook's `google.colab.files.upload()`. | Must |
| **FR-4** | Validate contigs before submission and **display the inferred design mode** (`free` / `fixed` / `partial`) back to the user, so the protocol RFdiffusion will run is visible rather than implicit. | Must |
| **FR-5** | Reject invalid input with a clear message rather than submitting a job that will fail: malformed contigs, `order` outside 1–12, non-numeric `partial_T`, unresolvable PDB identifier, `iterations` out of range. | Must |
| **FR-6** | Expose Slurm submission parameters with defaults drawn from Grex's own GPU job guidance: `--gpus=1`, `--cpus-per-task=6`, `--mem-per-cpu=6000M`, plus partition, account and walltime. Walltime and memory **must** be set explicitly (Grex defaults are 3 hours and 2500M/CPU). Single GPU is the correct default — the documentation advises starting with one and RFdiffusion does not scale across GPUs. | Must |
| **FR-6a** | Discover available partitions at runtime (`sinfo` / Grex's `partition-list`) rather than hard-coding a list. Grex's own documentation is internally inconsistent here — the partitions page lists `gpu` and `lgpu`, while the batch-jobs page lists `gpu`, `stamps-b`, `livi-b`, `agro-b` — so a hard-coded list would be wrong on arrival. | Must |
| **FR-7** | Derive a collision-free run name, preserving the notebook's behaviour of appending a random suffix when the chosen name is taken. | Must |
| **FR-8** | Submit the complete pipeline — backbone generation **and** validation — from **one action** ("one click"). | Must |

### 3.2 Job Execution

| ID | Requirement | Priority |
|---|---|---|
| **FR-9** | Submit a **single Slurm batch job** per run, executing backbone generation followed by ProteinMPNN/AlphaFold validation in one program, with `contigs` and `copies` passed in memory between stages. | Must |
| **FR-10** | Execute the scientific workload inside the **Apptainer image with `--nv`** for GPU passthrough. | Must |
| **FR-11** | Support a `--stage {all,backbone,validate}` flag on the runner so validation can be resubmitted against an existing run directory without repeating backbone generation. | Must |
| **FR-12** | Preserve the notebook's design logic **exactly**: mode inference, symmetry resolution (`cyclic`→`cN`/N copies, `dihedral`→`dN`/2N copies, `auto`→AnAnaS), `partial_T="auto"` ⇒ `int(80 * iterations/200)`, contig replication by copy count, guiding-potential flags, and post-run `fix_pdb` rewriting of all outputs and trajectories. | Must |
| **FR-13** | Write per-step scratch dumps to **`$TMPDIR`** — Grex's documented per-job node-local scratch — instead of the notebook's fixed `/dev/shm/{n}.pdb` paths. This is the sanctioned Grex idiom, is unique per job (resolving collision finding TD-13 without inventing a namespacing scheme), is node-local SSD, is auto-cleaned at job end, and matches the documentation's explicit guidance to use local disk for workloads producing large numbers of small files. Also `export SLURM_TMPDIR=$TMPDIR` for CCEnv script compatibility. | Must |
| **FR-14** | Allow a queued or running job to be **cancelled** from the UI (`scancel`). | Should |

### 3.3 Progress and Status Tracking

| ID | Requirement | Priority |
|---|---|---|
| **FR-15** | Display Slurm job state — `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`, `TIMEOUT` — sourced from `squeue` while active and `sacct` after completion. | Must |
| **FR-16** | Display **live denoising progress** at notebook parity: current timestep out of total, per design, driven by the per-step structure dumps. | Must |
| **FR-17** | Display a **live 3D preview** of the structure as it denoises, matching the notebook's `visual="interactive"` behaviour. | Must |
| **FR-18** | Distinguish and display **pipeline stage** (backbone vs. validation) within a running job. | Must |
| **FR-19** | Surface job failures with the **tail of the job log** and the Slurm exit code, rather than only a status colour. | Must |
| **FR-20** | Update status without a full page reload (HTMX polling). | Should |

### 3.4 Visualization

| ID | Requirement | Priority |
|---|---|---|
| **FR-21** | Render the final backbone in 3D using **3Dmol.js vendored locally** — the notebook loaded it from `3dmol.org` at render time, which must not be relied upon from a cluster node. | Must |
| **FR-22** | Support the notebook's colour modes: **rainbow**, **by chain** (using normalised contigs for chain lengths), and **by pLDDT** (B-factor gradient). | Must |
| **FR-23** | Animate the denoising **trajectory**, with selection between the `pX0` and `Xt-1` trajectories. | Should |
| **FR-24** | Display the **best design overlay** — RFdiffusion backbone superposed with the AlphaFold prediction coloured by pLDDT — reading the best index from the `REMARK 001` line of `best.pdb`. | Must |
| **FR-25** | When `num_designs > 1`, allow selection between designs (replacing the notebook's `ipywidgets.Dropdown`). | Must |
| **FR-26** | Show validation scores (RMSD, pLDDT) per design. | Should |

### 3.5 Run Management

| ID | Requirement | Priority |
|---|---|---|
| **FR-27** | List all runs with name, status, creation time, and key parameters. | Must |
| **FR-28** | Persist every run's full parameter set, inferred mode, **normalised contigs**, `copies`, Slurm job id, stage states, timestamps, and output paths. | Must |
| **FR-29** | Survive a web app restart with no loss of run state, including for jobs still running. | Must |
| **FR-30** | Allow a completed run's parameters to be **reloaded into the form** as the basis for a new run. | Should |

### 3.6 Results and Export

| ID | Requirement | Priority |
|---|---|---|
| **FR-31** | Package a run's outputs and trajectories into a **zip** and serve it over HTTP, replacing `google.colab.files.download()`. | Must |
| **FR-32** | Allow download of individual PDB files without zipping the whole run. | Should |
| **FR-33** | Keep each run directory **self-describing** — `run.json` alongside outputs, so a copied directory retains full provenance. | Must |

### 3.7 Documentation and Help

| ID | Requirement | Priority |
|---|---|---|
| **FR-34** | Present the notebook's contig-syntax instructions **in-app**, contextually near the contigs field — covering unconditional, binder design, motif scaffolding, and partial diffusion with the original worked examples. This is genuinely good documentation and must not be lost in the port. | Must |
| **FR-35** | Document setup end to end: building/obtaining the Apptainer image, staging model weights, `uv sync`, configuring the SSH tunnel with `ControlMaster`, and launching the app. | Must |

---

## 4. Non-Functional Requirements

### 4.1 Packaging and Dependencies

| ID | Requirement |
|---|---|
| **NFR-1** | The web app is a **`uv` project** with `pyproject.toml` and a committed `uv.lock`. |
| **NFR-2** | The web app environment contains **no PyTorch, no JAX, no CUDA** and requires no GPU — it is a Slurm client. |
| **NFR-3** | The web app installs and starts with **no Node.js, npm, or bundler**. All static assets are vendored. |
| **NFR-4** | The GPU runtime is an **Apptainer image** pinning torch/CUDA/DGL/e3nn/JAX, RFdiffusion, and ColabDesign — including commit SHAs for the two git-sourced packages, which the notebook left floating. |
| **NFR-5** | Model weights are **staged once** to persistent storage, never downloaded at job start, and never via `apt-get`/`aria2c` (no root on Grex). |

### 4.2 Environment and Configuration

| ID | Requirement |
|---|---|
| **NFR-6** | Weights path, Apptainer image path, `APPTAINER_CACHEDIR`, output root, and database path are **each independently configurable** via environment variables, defaulting to `/home`. |
| **NFR-7** | No Colab-specific code paths remain: no `google.colab`, no `dist-packages` symlink, no `apt-get`. |
| **NFR-8** | Slurm account and partition are configurable, not hard-coded. |

### 4.3 Correctness and Robustness

| ID | Requirement |
|---|---|
| **NFR-9** | Design logic ported from the notebook must be **behaviour-preserving**; where behaviour changes deliberately (e.g. scratch path namespacing), the change is documented. |
| **NFR-10** | Job failure, cancellation, timeout, and Slurm submission failure are each handled and surfaced distinctly — never silently. |
| **NFR-11** | All external commands are invoked via `subprocess` with **argument lists and no shell**. This eliminates the notebook's shell-injection surface (TD-7) and its input-corrupting quote-stripping workaround. |
| **NFR-12** | Replace the notebook's bare `except:` in symmetry detection (TD-8) with specific exception handling that distinguishes "no symmetry found" from "AnAnaS failed". |
| **NFR-13** | Subprocess calls capture stderr and check exit codes — the notebook's `os.system` checked neither. |
| **NFR-14** | The HTTP server binds **`127.0.0.1` only**, never `0.0.0.0`. |

### 4.4 Performance and Resource Use

| ID | Requirement |
|---|---|
| **NFR-15** | The web app's resident footprint must be small enough to be an unobtrusive login-node process; no compute, no model loading, no polling hot loops. |
| **NFR-16** | Status polling intervals are configurable and default to values that do not stress the Slurm controller (`squeue` polling measured in seconds, not milliseconds — unlike the notebook's 10 Hz filesystem poll). |

### 4.5 Testability

| ID | Requirement |
|---|---|
| **NFR-17** | **Contig parsing, design-mode inference, symmetry resolution, and Hydra flag assembly** are pure, importable functions with unit tests — including property tests over arbitrary contig strings. This logic has zero tests today and is the highest-value thing carried over. |
| **NFR-18** | Slurm interaction is isolated behind an interface that can be faked, so the app is testable without a cluster. |

---

## 5. Environment Constraints (verified against Grex documentation)

| ID | Constraint | Consequence |
|---|---|---|
| **C-1** | Slurm scheduler; jobs must name a partition | Partition is a required, configurable submission parameter |
| **C-2** | GPU partitions: `gpu` (2 nodes × 4 V100 32 GB), `lgpu` (2 nodes × 2 L40s 48 GB) | Scarce capacity — the reason for the single-job design (AD-5) |
| **C-3** | GPU-partition jobs are **rejected** unless they request GPUs | Submission must always include `--gpus=` |
| **C-4** | Default walltime **3 hours**; max **7 days** on `gpu` | `--time` must always be explicit; 7 days is ample for one full pipeline |
| **C-4a** | Default memory **2500M per CPU**; memory limits are **enforced** | `--mem-per-cpu` must be explicit and accurate, or the job is killed |
| **C-4b** | `--qos=` is documented as **"Not to be used on Grex!"** | Never emitted (G-3) |
| **C-4c** | Grex sets **`TMPDIR`**, not `SLURM_TMPDIR` | Per-job scratch uses `$TMPDIR`; `SLURM_TMPDIR` exported for CCEnv compatibility (G-11, G-12) |
| **C-4d** | Documented GPU partition names are **inconsistent between Grex's own pages** (`gpu`/`lgpu` vs. `gpu`/`stamps-b`/`livi-b`/`agro-b`) | Partitions discovered at runtime, never hard-coded (FR-6a) |
| **C-5** | **No root access** | No `apt-get install aria2`; weights pre-staged |
| **C-6** | **No system-wide conda**; virtualenv + pip explicitly preferred | Validates the `uv` choice |
| **C-7** | Apptainer/Singularity available; `--nv` for GPU | Basis of AD-4 |
| **C-8** | `/home` 100 GB per user; `/project` 5 TB per group (Lustre) | ~15–25 GB baseline accepted on `/home`; SQLite kept off Lustre |
| **C-9** | MFA (Cisco Duo) mandatory for SSH | Tunnel works via `ControlMaster`; unattended startup would need CCDB keys and a support conversation |
| **C-10** | OpenOnDemand sessions capped at 6 hours | Not used for hosting; submit-and-track makes the cap irrelevant to job survival |
| **C-11** | Login nodes not intended for heavy compute | App must stay I/O-light (NFR-15) |
| **C-12** | Containers should be pulled beforehand, not at job start | Image staged as part of setup |

---

## 5A. Grex Documentation Adherence (binding)

**User constraint**: *"My only constraint is making sure https://um-grex.github.io/docs/ are very strongly adhered to."*

The application submits **ordinary `sbatch` batch jobs** exactly as documented in
[running-jobs/batch-jobs](https://um-grex.github.io/docs/running-jobs/batch-jobs/). The web app is a
thin wrapper that generates a conventional `#SBATCH` job script and submits it — it introduces **no
alternative execution mechanism**. Anything the user does by hand in CLI mode, the app does
programmatically, following the documented templates.

### 5A.1 Job script conventions (from the documented templates)

| ID | Requirement | Source |
|---|---|---|
| **G-1** | Generated scripts follow the documented template shape: `#!/bin/bash`, an `#SBATCH` directive block, `cd ${SLURM_SUBMIT_DIR}`, `echo "Starting run at: \`date\`"`, and `echo "Job finished with exit code $? at: \`date\`"`. | batch-jobs templates |
| **G-2** | Submission is via `sbatch <script>`. Job scripts are written to the run directory and retained, so every run is reproducible by hand with `sbatch` and inspectable after the fact. | batch-jobs |
| **G-3** | **Never emit `--qos=`.** The documentation states explicitly: *"Not to be used on Grex!"* | batch-jobs directive table |
| **G-4** | Always request walltime (`--time=DD-HH:MM:SS`) and memory explicitly; never rely on the 3-hour / 2500M-per-CPU defaults. | scheduling policies |
| **G-5** | GPU jobs must always request GPUs via `--gpus=N` (the GTRES plugin syntax) — Grex **rejects** GPU-partition jobs that don't. | slurm-partitions, batch-jobs |
| **G-6** | Always specify `--partition=` explicitly; Grex has no automatic partition selection beyond a default. | slurm-partitions |

### 5A.2 Fair resource use

| ID | Requirement | Source |
|---|---|---|
| **G-7** | Default to **one GPU**. The documentation advises starting with a single GPU because *"many codes cannot scale to utilize more than one"* — RFdiffusion among them. | batch-jobs, "How many GPUs to ask for?" |
| **G-8** | Default to **6 CPUs per GPU and 4–8 GB RAM per CPU**, matching the documented starting point and their own GPU template (`--cpus-per-task=6 --mem-per-cpu=6000M`). | batch-jobs |
| **G-9** | Do not run CPU-only work on GPU nodes wastefully. Grex asks users *"not to allow for deliberate waste of resources (such as … running CPU-only calculations on GPU nodes)."* **Compliance rationale**: both pipeline stages (RFdiffusion, and ProteinMPNN + AlphaFold) are genuinely GPU workloads, so holding one GPU for the job is correct. The CPU-only portions — template download, AnAnaS symmetry detection, final zip packaging — total seconds against a run measured in minutes to hours, which is ordinary job overhead rather than deliberate waste. **Mitigation**: all cheap validation (contig parsing, mode inference, parameter range checks) happens in the web app *before* submission, so no job is ever queued only to fail on malformed input. | batch-jobs |
| **G-10** | Stay within documented scheduling limits: max 4000 queued jobs per user, 400 CPU cores per accounting group without a RAC, and 1 GPU per job on contributed hardware. Not binding at this application's scale, but the app must not submit in unbounded loops. | scheduling policies |

### 5A.3 Storage and scratch

| ID | Requirement | Source |
|---|---|---|
| **G-11** | Use **`$TMPDIR`** for per-job scratch — Slurm creates it per job, it is node-local, and it is deleted at job end. This replaces the notebook's `/dev/shm` and is the correct home for the per-step PDB dumps, which are exactly the "large number of small files" pattern the documentation says to keep off Lustre. | using-localdisks |
| **G-12** | Set `export SLURM_TMPDIR=$TMPDIR` in generated job scripts. Grex sets `TMPDIR`, not `SLURM_TMPDIR`, and the documentation notes CCEnv scripts may expect the latter. | using-localdisks, batch-jobs |
| **G-13** | Stage results **out of** `$TMPDIR` before job end — node-local scratch does not survive. Final PDBs, trajectories and `run.json` are written to the persistent run directory. | using-localdisks |
| **G-14** | Node-local scratch is ~100–200 GB; do not assume more. Bulk data stays on the persistent filesystem. | using-localdisks |

### 5A.4 Containers

| ID | Requirement | Source |
|---|---|---|
| **G-15** | Obtain the container runtime via `module load singularity` (SBEnv), or Apptainer via CCEnv — the documentation states the two are largely interchangeable. | containers |
| **G-16** | **Pull or build the image ahead of time**; never pull from a registry at job start. The documentation warns this risks the whole cluster being banned by registries for bulk downloads. | containers |
| **G-17** | Use `--nv` for GPU passthrough. | containers |
| **G-18** | Set `APPTAINER_CACHEDIR` / `SINGULARITY_CACHEDIR` deliberately, since the cache otherwise grows silently in `/home` against the 100 GB quota. | containers, quotas |

### 5A.5 Access

| ID | Requirement | Source |
|---|---|---|
| **G-19** | Document SSH access using the `ControlMaster` / `ControlPersist` configuration that Grex's MFA page itself recommends for caching Duo sessions. | connecting/mfa |
| **G-20** | Do not attempt to work around MFA. If unattended startup is ever wanted, the documented path is a CCDB-deposited key plus a conversation with Grex support — not an automated credential workaround. | connecting/mfa, connecting/ssh |

---

## 6. Out of Scope (v1)

- Multi-user support, authentication, and per-user isolation
- Fold conditioning (the separate `diffusion_foldcond` notebook)
- Unattended/boot-time startup of the web app
- Automated Apptainer image building in CI
- Result sharing, publishing, or Globus integration
- Historical run analytics or cross-run comparison
- Non-Grex cluster support (though configurability should not preclude it)

---

## 7. Traceability to Business Transactions

| Business Transaction (from reverse engineering) | Requirements | Disposition |
|---|---|---|
| **BT-1** Provision Environment | NFR-1, NFR-4, NFR-5, FR-35 | **Replaced** — `uv` + Apptainer + one-time weight staging supersede the 35 lines of runtime `os.system` installs |
| **BT-2** Generate Backbone | FR-1, FR-3–FR-13 | **Ported**, logic preserved |
| **BT-3** Monitor Progress | FR-15–FR-20 | **Rewritten** — ipywidgets → server-side state + HTMX polling |
| **BT-4** Review Backbone | FR-21–FR-23, FR-25 | **Rewritten** — py3Dmol → vendored 3Dmol.js |
| **BT-5** Design + Validate Sequence | FR-2, FR-9, FR-11 | **Ported**, now in-process with backbone generation |
| **BT-6** Review Best Design | FR-24, FR-26 | **Rewritten**, and the `plot_pdb` shadowing bug (TD-10) resolved by separating the two views |
| **BT-7** Export Results | FR-31–FR-33 | **Rewritten** — `files.download` → HTTP endpoint |

---

## 8. Extension Configuration

| Extension | Enabled | Decision |
|---|---|---|
| security/baseline | **No** | 9a = B |
| resiliency/baseline | **No** | 10a = B |
| testing/property-based | **No** | 11a = B |

No extension rules are enforced as blocking constraints at any stage, and their full rules files were
not loaded. The substantive protections that prompted those questions remain in scope as ordinary
requirements: **NFR-11** (argument lists, no shell), **NFR-14** (localhost binding), **FR-5** (input
validation), **NFR-10/12/13** (failure handling), and **NFR-17** (property tests on contig logic).

---

## 9. Risks

| ID | Risk | Severity | Mitigation |
|---|---|---|---|
| **R-1** | The Apptainer image is the critical path — torch/CUDA/DGL/e3nn/JAX ABI coupling is historically fragile, and the notebook pinned almost none of it | **High** | Build/validate the image early, before app development. Prefer an existing published RFdiffusion image if one matches. Treat "GPU inference runs in the container on a Grex GPU node" as the first milestone. |
| **R-2** | `dgl` was installed `--no-dependencies` from a `torch-2.4/cu124` wheel index; its true transitive requirements are undocumented | **High** | Resolve inside the container where the full environment is controlled; record the working version set explicitly. |
| **R-3** | The `ananas` binary is precompiled with unverified provenance and glibc requirements | Medium | Test early inside the container; `symmetry="auto"` is the only feature that depends on it and can degrade gracefully. |
| **R-4** | Persistent user web process on a login node may conflict with Grex policy | Medium | App is I/O-light by design (NFR-15). Confirm with Grex support; fallback is hosting inside a long-running CPU-partition job. |
| **R-5** | `/home` quota pressure — ~15–25 GB baseline plus accumulating trajectories | Medium | Accepted by the user. All paths configurable (NFR-6); set `APPTAINER_CACHEDIR` deliberately. |
| **R-6** | GPU queue wait makes the UI appear stalled during long `PENDING` periods | Low | `PENDING` shown as a distinct, explained state (FR-15). |
| **R-7** | Live progress depends on RFdiffusion's per-step dump behaviour, which is an implementation detail of a pinned upstream fork | Low | Degrade to Slurm-state-only display if dumps are absent; never block on them. |

---

## 10. Success Criteria

1. `uv sync` produces a working web app environment on a Grex login node with **no GPU, no PyTorch, and no Node toolchain**.
2. From a browser over an SSH tunnel, a user submits a design with **one click** and a single Slurm job is queued.
3. The UI shows `PENDING` → `RUNNING` with live denoising step progress and a live 3D preview, then `COMPLETED`.
4. Backbone, trajectory, and best-design overlay are all viewable in-browser.
5. Results download as a zip.
6. Closing the browser, and restarting the web app, leave a running job and its record intact.
7. All four design protocols from the notebook's instructions — unconditional, binder, motif scaffolding, partial diffusion — produce correct Hydra invocations, verified by tests.
8. No `google.colab`, no `apt-get`, no shell-string command construction anywhere in the codebase.
9. **Every generated job script is one a Grex user could have written by hand** from the documented templates — conventional `#SBATCH` directives, explicit walltime/memory/GPU/partition, no `--qos=`, `$TMPDIR` for scratch, results staged out before job end. The retained script in each run directory is resubmittable with plain `sbatch` and passes review against `https://um-grex.github.io/docs/` requirement-by-requirement (G-1 … G-20).
