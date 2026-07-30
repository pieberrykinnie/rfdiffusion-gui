# Services

Service definitions and orchestration patterns. Services coordinate components; they hold no domain
logic of their own.

---

## S-1 `SubmissionService` (`rfd-web`)

**Responsibility**: Turn a validated web form into a queued Slurm job and a persisted run record.

**Collaborators**: C-26 `RequestValidator`, C-27 `TemplateUploadHandler`, C-10 `PathLayout`,
C-7 `RunRecord`, C-23 `JobScriptGenerator`, C-21 `SlurmAdapter`, C-24 `RunRepository`.

**Orchestration**:
1. Validate the `DesignRequest` (C-26). **Reject before doing anything else** — no run directory, no
   job, no GPU consumed (G-9, FR-5).
2. Derive a collision-free run id/name (FR-7).
3. Create the run directory (C-10).
4. Persist any uploaded template into it (C-27).
5. Write the initial `RunRecord` with both stages `PENDING` (C-7).
6. Generate and write the `#SBATCH` script into the run directory (C-23).
7. Submit via `sbatch` (C-21); capture the job id.
8. Update the record with the job id and index it in SQLite (C-24).

**Failure handling**: if submission fails, the record is retained with `backbone_state = FAILED` and
the `sbatch` stderr stored — the user sees *why*, not merely that nothing happened (NFR-10).

**Transaction boundary**: the run directory plus `run.json` is the source of truth; the SQLite row is
an index. If SQLite write fails, the run is still recoverable by directory scan.

---

## S-2 `RunQueryService` (`rfd-web`)

**Responsibility**: Answer "what is the state of this run?" by reconciling four sources.

**Collaborators**: C-24 `RunRepository`, C-25 `RunDirectoryReader`, C-21 `SlurmAdapter`.

**Orchestration**:
1. Load the indexed record (C-24), falling back to `run.json` (C-25).
2. If not terminal, query Slurm for live state (C-21) — `squeue` first, then `sacct`.
3. Overlay `progress.json` for step-level detail (C-25).
4. Reconcile and return a unified view.

**Reconciliation rules** (detailed in U3 Functional Design):
- Slurm is authoritative for *job* state; `progress.json` is authoritative for *within-job* progress.
- Job `COMPLETED` but `run.json` not marked complete ⇒ the runner died before writing its terminal
  state; report `FAILED` with the log tail (FR-19), never a false success.
- Job `PENDING` ⇒ report queued; no progress file is expected yet.
- Terminal Slurm state is written back to SQLite so later reads need no `sacct` call.

**Why this service exists**: it is the only place where the "which source wins" question is answered.
Scattering that logic across routes is how status displays start lying.

---

## S-3 `ResultService` (`rfd-web`)

**Responsibility**: Locate and serve run artifacts.

**Collaborators**: C-25 `RunDirectoryReader`, C-10 `PathLayout`.

**Orchestration**: resolve the requested artifact (live frame, final backbone, trajectory, best-design
overlay, individual file, or zip) within the run directory; stream it. Resolves the best-design index
from `best.pdb`'s `REMARK 001` line (FR-24).

**Constraint**: all paths resolved **relative to the run directory** and checked to remain inside it —
the file endpoint takes a path parameter and must not become a directory traversal.

---

## S-4 `PipelineService` (`rfd-runner`, in-job)

**Responsibility**: Execute the full scientific pipeline in one process — the in-process successor to
the notebook's cell sequence.

**Collaborators**: C-11 … C-19, driven by C-20 `PipelineOrchestrator`.

**Orchestration** (`--stage all`):

1. Load `RunRecord` from the run directory; mark `backbone_state = RUNNING`.
2. Parse contigs (C-1) and infer mode (C-2).
3. Resolve symmetry (C-3); if `auto`, fetch the template and run AnAnaS (C-11, C-12) and fold the
   detected group back into the plan.
4. For `fixed`/`partial`: resolve and normalise the template, write `input.pdb`, `parse_pdb`.
5. Normalise contigs (C-13) → **`normalised_contigs`, `copies` held in memory**.
6. Plan iterations (C-4); build the inference argv (C-5).
7. Execute inference (C-14), with `on_step` driving `FramePublisher` (C-15) and `ProgressReporter`
   (C-16).
8. Post-process output PDBs (C-17).
9. Persist `normalised_contigs` and `copies` into `RunRecord`; mark backbone `COMPLETED`.
10. Mark `validate_state = RUNNING`; run validation (C-18) **using the in-memory values from step 5**.
11. Stage out of `$TMPDIR` and package results (C-19).
12. Write the terminal `RunRecord`.

**Stage selection** (FR-11):
- `--stage backbone` — steps 1–9, validation marked `SKIPPED`.
- `--stage validate` — load `RunRecord`, take `normalised_contigs`/`copies` from it, run steps 10–12.
  This is the one path where the values come from disk rather than memory, and it exists precisely so
  a failed validation can be retried without repeating backbone generation.

**Failure handling**: every exit path writes a terminal `RunRecord`. A crash that bypasses even that
is caught by S-2's reconciliation rule (Slurm terminal + record non-terminal ⇒ report failure).

**Why one service, one process**: this is AD-5. Keeping the pipeline in a single process is what lets
`normalised_contigs` and `copies` remain ordinary variables — the notebook's behaviour — and avoids a
second GPU queue wait.

---

## Service Interaction Overview

```mermaid
sequenceDiagram
    participant U as Browser
    participant R as Routes (C-28)
    participant S1 as SubmissionService
    participant SA as SlurmAdapter
    participant SL as Slurm
    participant P as PipelineService (in job)
    participant FS as Run directory
    participant S2 as RunQueryService

    U->>R: POST /runs (form)
    R->>S1: submit(request)
    S1->>S1: validate; reject early if invalid
    S1->>FS: create run dir, run.json, job script
    S1->>SA: sbatch
    SA->>SL: submit
    SL-->>S1: job id
    S1->>FS: record job id
    R-->>U: redirect to /runs/{id}

    SL->>P: job starts on GPU node
    loop each denoising step
        P->>FS: progress.json (every step)
        P->>FS: current_frame.pdb (every N steps)
    end
    P->>FS: outputs, trajectories, terminal run.json

    loop HTMX polling
        U->>R: GET /runs/{id}/status
        R->>S2: get_state(id)
        S2->>SA: squeue / sacct
        S2->>FS: run.json + progress.json
        S2-->>R: reconciled view
        R-->>U: HTML fragment
    end
```

**Text alternative**: The browser posts the form to Routes, which delegates to SubmissionService.
That service validates first and rejects invalid input before creating anything, then creates the run
directory, initial `run.json`, and job script, submits via SlurmAdapter, and records the returned job
id. When Slurm starts the job, PipelineService runs on the GPU node writing `progress.json` every
step and `current_frame.pdb` every N steps, and finally writes outputs and a terminal `run.json`.
Meanwhile the browser polls a status endpoint; RunQueryService reconciles Slurm state with the two
files and returns a unified view rendered as an HTML fragment.

---

## Design Notes

**No service-to-service calls.** Each service is invoked from a route (or from the runner's entry
point) and collaborates only with components. This keeps the dependency graph acyclic and each
service independently testable with faked components.

**Services are stateless.** All state is in the run directory and SQLite. This is what allows the web
app to be restarted at any time without losing track of a running job (FR-29) — there is nothing in
memory to lose.

**The process boundary is explicit.** S-1, S-2, S-3 run on the login node; S-4 runs on a GPU compute
node inside the container. They never call each other — they communicate only through the run
directory, using the `rfd-core` file-format contracts. That is why those models live in the shared
package.
