# U3 Slurm and Persistence — Domain Entities

**Unit**: U3 (`packages/rfd-web/src/rfd_web/{slurm,persistence,services}`)
**Stage**: CONSTRUCTION — Functional Design
**Date**: 2026-08-27

Entities introduced by this unit. Everything already defined by `rfd-core` (U2a) — `DesignRequest`,
`RunRecord`, `RunOutputs`, `ProgressState`, `StageState`, `PathLayout`, `ValidationOutcome`,
`DesignMode` — is **reused unchanged**. This unit adds no field to any `rfd-core` model.

---

## 1. `SlurmState`

```python
class SlurmState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"
```

Exactly the seven values Application Design specifies. Slurm's wider vocabulary is folded into these
by the total map in business-logic-model.md §3.1 (BR-7). `str, Enum` rather than `StrEnum`, matching `rfd-core`'s
3.9-compatible idiom — and, per the correction in section 8, required rather than merely
conventional.

**Terminal states**: `COMPLETED`, `FAILED`, `CANCELLED`, `TIMEOUT`. `UNKNOWN` is deliberately **not**
terminal — a job Slurm cannot currently describe may still be running.

---

## 2. `JobStatus`

```python
@dataclass(frozen=True)
class JobStatus:
    state: SlurmState
    exit_code: Optional[int] = None    # X from sacct's "X:Y"  (BR-10)
    signal: Optional[int] = None       # Y from sacct's "X:Y"
    reason: Optional[str] = None       # squeue Reason, or the raw Slurm state word
    known: bool = True                 # False only when both queries succeeded with no row
```

Refinement **R-1** to `component-methods.md`'s `state(job_id) -> SlurmState`, which cannot carry the
exit code FR-19 requires. `known` is what lets BR-4 distinguish "Slurm has forgotten this job" from
"Slurm is unreachable" — the latter raises `SlurmUnavailable` instead.

---

## 3. `PartitionInfo`

```python
@dataclass(frozen=True)
class PartitionInfo:
    name: str
    has_gpu: bool
    max_walltime: Optional[str]        # sinfo %l, e.g. "7-00:00:00"; None when "infinite"
    is_default: bool                   # sinfo marks the default partition with a trailing "*"
    available: bool                    # sinfo %a == "up"
    compatible: bool = True            # Q3=A -- annotation, never a filter
    incompatible_reason: Optional[str] = None
```

`compatible` is driven by `RFD_INCOMPATIBLE_PARTITIONS` (default `lgpu`), so no partition name
appears in code — FR-6a forbids a hard-coded list, and this list is configuration describing the
*image*, not the cluster. Incompatible partitions remain listed and selectable, carrying a reason
such as *"the current image targets CUDA 11.6 (sm_70/sm_80); lgpu is L40s (sm_89)"*.

---

## 4. `RunStatus` and `RunView`

`RunView` is the **reconciled read model** — the single answer S-2 produces, and the only shape U4
renders. Nothing else in the system may reconcile sources for itself.

```python
class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProgressView:
    stage: str                         # "backbone" | "validate"
    design_index: int
    total_designs: int
    step: int
    total_steps: int
    stale: bool                        # BR-5
    note: Optional[str] = None         # e.g. "validating (no step-level progress available)"


@dataclass(frozen=True)
class RunView:
    run_id: str
    name: str
    created_at: datetime
    status: RunStatus
    slurm_job_id: Optional[str]
    slurm_state: Optional[SlurmState]
    exit_code: Optional[int]
    mode: Optional[DesignMode]
    backbone_state: StageState
    validate_state: StageState
    progress: Optional[ProgressView]   # only when status is RUNNING (BR-5)
    frame_available: bool              # from current_frame.pdb on disk, NOT progress.frame_path (BR-6)
    message: Optional[str]             # human-readable detail, per the 9.2 table
    log_tail: Optional[str]            # only for FAILED / TIMEOUT / UNKNOWN (FR-19)
    outputs: Optional[RunOutputs]      # rfd-core, unchanged
    stale: bool = False                # True when Slurm was unreachable (BR-4)
    cancel_requested_at: Optional[datetime] = None
```

`RunStatus` is separate from `SlurmState` on purpose. They are not the same vocabulary: Slurm's
`COMPLETED` becomes `RunStatus.FAILED` whenever `run.json` was never finalised (BR-2). One enum
would make that distinction inexpressible.

---

## 5. `RunSummary` and the SQLite Schema

`RunSummary` is the list-row projection (FR-27) — cheap to produce for a hundred runs, no run
directory read, no Slurm call:

```python
@dataclass(frozen=True)
class RunSummary:
    run_id: str
    name: str
    created_at: datetime
    status: RunStatus                  # last reconciled status
    mode: Optional[DesignMode]
    partition: str
    num_designs: int
    contigs: str
    slurm_job_id: Optional[str]
    terminal: bool
    missing: bool                      # run directory has gone away (BR-19)
```

### 5.1 Schema

```sql
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;
PRAGMA user_version = 1;               -- schema version; mirrors RunRecord.schema_version

CREATE TABLE IF NOT EXISTS runs (
    run_id              TEXT PRIMARY KEY,
    name                TEXT    NOT NULL,
    run_dir             TEXT    NOT NULL,
    created_at          TEXT    NOT NULL,     -- ISO 8601 UTC
    updated_at          TEXT    NOT NULL,

    contigs             TEXT    NOT NULL,
    mode                TEXT,
    num_designs         INTEGER NOT NULL DEFAULT 1,
    partition           TEXT    NOT NULL,

    slurm_job_id        TEXT,
    job_id_history      TEXT    NOT NULL DEFAULT '[]',   -- JSON array; resubmissions (section 8)
    slurm_state         TEXT,
    exit_code           INTEGER,

    backbone_state      TEXT    NOT NULL,
    validate_state      TEXT    NOT NULL,
    status              TEXT    NOT NULL,                -- last reconciled RunStatus

    terminal            INTEGER NOT NULL DEFAULT 0,      -- BR-3: short-circuits Slurm queries
    missing             INTEGER NOT NULL DEFAULT 0,      -- BR-19
    cancel_requested_at TEXT                             -- BR-8 / Q6=A
);

CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_live       ON runs (terminal, slurm_job_id);
```

**Every column is derivable from a run directory** (BR-18) — except `job_id_history` and
`cancel_requested_at`, which are index-only by design:

- `job_id_history` exists because `RunRecord.slurm_job_id` is a single field and this unit does not
  reopen an approved `rfd-core` model to store a convenience (business-logic-model.md §8). Losing it
  costs nothing: the job logs of every attempt remain in the run directory.
- `cancel_requested_at` records that a human pressed Cancel in this app. Losing it degrades BR-8's
  message from *"cancelled from this app"* to *"cancelled by the scheduler or an administrator"* —
  softer, never wrong.

`idx_runs_live` is what lets a run-list render collect every non-terminal job id in one query and
issue a **single** batched `squeue` (BR-23).

Dates are stored as ISO 8601 UTC text. SQLite has no date type, and text dates sort correctly, stay
readable in `sqlite3`, and round-trip through pydantic without a converter.

---

## 6. Errors

```python
class SlurmError(Exception): ...
class SlurmUnavailable(SlurmError): ...       # command failed, timed out, or is not on PATH (BR-4)
class SlurmSubmitError(SlurmError): ...       # sbatch returned non-zero; carries stderr (BR-15)
class JobScriptError(Exception): ...          # whitelist violation during generation (BR-12)
class PathContainmentError(Exception): ...    # resolved path escapes the run directory (BR-14)
```

`SubmissionOutcome` is a **value**, not an exception, because a rejected or failed submission is
something the user must see and act on (business-rules.md §7):

```python
@dataclass(frozen=True)
class SubmissionOutcome:
    ok: bool
    run_id: Optional[str] = None
    slurm_job_id: Optional[str] = None
    errors: List[str] = field(default_factory=list)      # from ValidationOutcome, or sbatch stderr
    warnings: List[str] = field(default_factory=list)
```

---

## 7. Configuration — new environment variables

`WebConfig.from_env()` mirrors `PathLayout.from_env()` and `RunnerConfig.from_env()`: plain
`os.environ` reads, no new config format. The `RFD_DEFAULT_*` variables already exist in
`env.example`; the rest are added by this unit.

| Variable | Default | Purpose |
|---|---|---|
| `RFD_STATUS_POLL_SECONDS` | `5` | HTMX status poll cadence (NFR-16, D-4) |
| `RFD_SLURM_TIMEOUT_SECONDS` | `30` | Per-command subprocess timeout (BR-22) |
| `RFD_PARTITION_CACHE_SECONDS` | `300` | `sinfo` result cache lifetime |
| `RFD_PROGRESS_STALE_SECONDS` | `120` | Age past which `progress.json` is stale (BR-5) |
| `RFD_INCOMPATIBLE_PARTITIONS` | `lgpu` | Comma-separated; annotation only (Q3=A) |
| `RFD_LOG_TAIL_LINES` | `50` | Lines of job log attached to a failure (FR-19) |

Existing and unchanged: `RFD_OUTPUT_ROOT`, `RFD_DB`, `RFD_IMAGE`, `RFD_WEIGHTS`,
`RFD_PROJECT_ROOT`, `APPTAINER_CACHEDIR`, `SINGULARITY_CACHEDIR`, `RFD_DEFAULT_PARTITION`,
`RFD_DEFAULT_ACCOUNT`, `RFD_DEFAULT_GPUS`, `RFD_DEFAULT_CPUS_PER_TASK`,
`RFD_DEFAULT_MEM_PER_CPU`, `RFD_DEFAULT_WALLTIME`.

---

## 8. Module Layout

```
packages/rfd-web/src/rfd_web/
├── config.py                 WebConfig.from_env()
├── slurm/
│   ├── states.py             SlurmState, JobStatus, the total state map
│   ├── adapter.py            SlurmAdapter (Protocol), CliSlurmAdapter
│   ├── fake.py               FakeSlurmAdapter  (shipped, not test-only -- NFR-18)
│   ├── partitions.py         PartitionInfo, discover_partitions, cache
│   └── script.py             JobScriptGenerator
├── persistence/
│   ├── schema.py             DDL, PRAGMAs, user_version
│   ├── repository.py         RunRepository, RunSummary
│   ├── reader.py             RunDirectoryReader
│   └── reconcile.py          RunIndexReconciler   (Q5=A)
└── services/
    ├── submission.py         S-1 SubmissionService, SubmissionOutcome
    └── query.py              S-2 RunQueryService, RunView, RunStatus, ProgressView
```

`rfd-web` depends on `rfd-core` **only** — never on `rfd-runner` (DD-1), which is what keeps PyTorch
out of the login-node environment (NFR-2).

**Corrected 2026-08-27 during Code Generation Step 1**: this section previously said
`pyproject.toml` targets Python ≥ 3.11. It targets **`>=3.9,<3.10`**, like the rest of the
workspace. `rfd-web` depends on `rfd-core`, which is capped below 3.10 so it can import inside the
U1 container — so any environment that can import `rfd-core` is a 3.9 environment, the login node
included, and `>=3.11` was never installable. `uv lock` rejects the mismatch outright
(*"Found conflicting Python requirements"*), and the only way to keep `>=3.11` would have been to
make `rfd-web` a standalone project with its own lockfile, breaking DD-1's approved "uv workspace,
three packages". The login node's *system* `python3` is 3.6.8 and unusable; `uv` supplies 3.9
there, as `docs/setup.md` describes.

`fake.py` ships in `src/`, not `tests/`, so U4 can run the entire application offline against it.

---

## 9. What This Unit Does NOT Define

- **HTTP anything** — routes, request/response models, templates, HTMX fragments: all U4.
- **`TemplateUploadHandler` (C-27)** — needs FastAPI's `UploadFile`. S-1 takes an already-resolved
  path (Q1=A).
- **`RequestValidator` (C-26)** — already shipped as `rfd_core.validate` / `preview_mode`
  (finding F-5). U3 calls it.
- **`ResultService` (S-3)** — U4. `RunDirectoryReader` provides the reads it will need, including
  the containment rule (BR-14) that S-3's file endpoint depends on.
- **Any change to `rfd-core` models** — `RunRecord`, `ProgressState` and `DesignRequest` are used
  exactly as approved in U2a.
- **Any change to the runner's SIGTERM behaviour** — Q6=A resolves the cancel/timeout contradiction
  in the reconciler rather than reopening U2b, which is approved and proven on real hardware.
