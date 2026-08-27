# U3 Slurm and Persistence — Code Generation Plan

**Unit**: U3 Slurm and Persistence (`packages/rfd-web`)
**Stage**: CONSTRUCTION — Code Generation
**Date**: 2026-08-27
**Workspace root**: `/home/pieberrykinnie/rfdiffusion-gui` (this worktree:
`.claude/worktrees/u3`)

> Single source of truth for this generation pass. Steps are executed in order; each is ticked `[x]`
> in this file in the same interaction the work is completed.

---

## Local Capability Check (performed before writing this plan)

Unlike U1 and U2b, **this unit is fully verifiable locally**. `unit-of-work.md` says so — *"testable
without cluster: ✓ with fake Slurm"* — and the toolchain confirms it:

- `uv 0.10.11`, with **`cpython-3.9.25` already installed** — the interpreter `rfd-web` targets.
  *(Corrected during Step 1: this plan first said `>=3.11`. See Step 1's note — `rfd-web` depends on
  `rfd-core`, which is capped below 3.10, so a 3.11 `rfd-web` was never installable and `uv lock`
  refuses the workspace outright.)*
- No Slurm binaries here, which is the point: every Slurm call goes through the C-21 `Protocol`, and
  the whole suite runs against `FakeSlurmAdapter` (NFR-18, D-5).
- Real SQLite via the stdlib `sqlite3` module — the persistence layer is tested against **real
  databases in `tmp_path`**, not a mock.
- Real `bash`, so the M1 lesson is testable: the generated job script is **executed** against a stub
  `singularity`/`apptainer` on `PATH`, not merely string-matched.

So this plan claims local verification and must deliver it. Nothing here is deferred to Grex.

---

## Unit Context

**Requirements owned**: FR-6, FR-6a, FR-7, FR-11 (the caller), FR-14, FR-15, FR-18, FR-19, FR-27,
FR-28, FR-29, FR-33 (read side) · NFR-8, NFR-10, NFR-11, NFR-13, NFR-15, NFR-16, NFR-18 ·
G-1 … G-18 (job-script conformance).

**Source of truth for behaviour**: the three approved artifacts at
`aidlc-docs/construction/u3-slurm-persistence/functional-design/` —
`business-logic-model.md`, `business-rules.md` (BR-1 … BR-23), `domain-entities.md`. Component
contracts: `components.md` / `component-methods.md` C-21 … C-25, `services.md` S-1 and S-2.

**Dependencies**: `rfd-core` (U2a, approved) — `DesignRequest`, `RunRecord`, `RunOutputs`,
`ProgressState`, `StageState`, `DesignMode`, `PathLayout`, `validate`, `preview_mode`,
`read_json`/`write_json_atomic`. **`rfd-web` must never depend on `rfd-runner`** (DD-1, NFR-2) —
this is a resolver-enforced boundary, and Step 16 tests it.

**Consumed by**: U4, which adds routes, templates and `TemplateUploadHandler` on top of S-1/S-2 and
`RunDirectoryReader`.

**Not in this unit**: HTTP, Jinja2, HTMX, 3Dmol.js, `RequestValidator` (already shipped as
`rfd_core.validate` — finding F-5), `ResultService` (S-3), `TemplateUploadHandler` (C-27).

---

## Decisions Carried In (already settled, not reopened here)

From the approved Functional Design: Q1=A (S-1 built here, minus browser upload), Q2=A (M1-proven
script shape), Q3=A (partitions annotated, never filtered), Q4=A (sanitised name + suffix on
collision), Q5=A (startup reconciliation), Q6=A (Slurm wins on the kind of ending;
`cancel_requested_at` recorded), Q7=A (`.err` then `.out`), Q8=A (`resubmit`), and D-1 … D-6.

**One decision made without asking, recorded here**: `rfd-web`'s `pyproject.toml` declares **no
FastAPI/uvicorn/Jinja2 dependency in this pass**. U3 contains no HTTP code, and adding a web
framework the unit does not import would put unused packages in `uv.lock` and make "does this unit
really have no HTTP in it?" unanswerable from the manifest. U4 adds them when it adds the routes.
Reversible in one line; changes no behaviour here.

---

## Target Layout (application code — never `aidlc-docs/`)

```
packages/rfd-web/
├── pyproject.toml
├── README.md
├── src/rfd_web/
│   ├── __init__.py            public exports
│   ├── py.typed
│   ├── config.py              WebConfig.from_env()
│   ├── errors.py              SlurmError, SlurmUnavailable, SlurmSubmitError,
│   │                          JobScriptError, PathContainmentError
│   ├── slurm/
│   │   ├── __init__.py
│   │   ├── states.py          SlurmState, JobStatus, the total state map
│   │   ├── adapter.py         SlurmAdapter (Protocol), CliSlurmAdapter
│   │   ├── fake.py            FakeSlurmAdapter  (shipped, not test-only)
│   │   ├── partitions.py      PartitionInfo, discover_partitions, TTL cache
│   │   └── script.py          JobScriptGenerator
│   ├── persistence/
│   │   ├── __init__.py
│   │   ├── schema.py          DDL, PRAGMAs, user_version
│   │   ├── repository.py      RunRepository, RunSummary
│   │   ├── reader.py          RunDirectoryReader
│   │   └── reconcile.py       RunIndexReconciler
│   └── services/
│       ├── __init__.py
│       ├── submission.py      S-1 SubmissionService, SubmissionOutcome
│       └── query.py           S-2 RunQueryService, RunView, RunStatus, ProgressView
└── tests/
    ├── conftest.py
    ├── test_states.py
    ├── test_config.py                added during generation (WebConfig defaults/fallbacks)
    ├── test_adapter.py
    ├── test_fake.py
    ├── test_partitions.py
    ├── test_script.py
    ├── test_script_execution.py      executes the script against a stub engine
    ├── test_repository.py
    ├── test_reader.py
    ├── test_reconcile.py
    ├── test_submission.py
    ├── test_query.py
    └── test_boundaries.py            no rfd_runner import; no HTTP framework
```

---

## Steps

### Step 1: Project Structure Setup
- [x] Create `packages/rfd-web/pyproject.toml` — `requires-python = ">=3.9,<3.10"`, depends on
      `rfd-core` as a workspace member, dev group `pytest>=8.0`; hatchling build;
      `[tool.pytest.ini_options] testpaths = ["tests"]`; `[tool.ruff] target-version = "py39"` with
      the same `UP045`/`UP007` ignore the sibling packages carry.
      **CORRECTION MADE DURING THIS STEP.** The plan, `domain-entities.md` §8 and the root
      `pyproject.toml`'s own comment all said `rfd-web` targets `>=3.11`. It cannot. `rfd-web`
      depends on `rfd-core`, which is pinned `>=3.9,<3.10` so it can import inside the U1 container
      — so **any** environment able to import `rfd-core` is a 3.9 environment, the login node
      included. `uv lock` proved it immediately:
      `error: Found conflicting Python requirements: rfd-core >=3.9,<3.10 / rfd-runner >=3.9,<3.10
      / rfd-web >=3.11`. A uv workspace has one lockfile and one requires-python intersection;
      keeping `>=3.11` would have required making `rfd-web` a standalone project with its own lock,
      breaking DD-1's approved "uv workspace, three packages". Corrected in all four places
      (this plan, `domain-entities.md`, the root `pyproject.toml` comment, and the package
      manifest), and the `UP045`/`UP007` ignore **is** therefore needed here after all.
- [x] Create `src/rfd_web/{__init__.py,py.typed}`, the three subpackage `__init__.py` files, and
      `tests/`
- [x] Confirm the root `pyproject.toml` `members = ["packages/*"]` glob picks it up (no edit
      expected) and run `uv sync` to prove the workspace resolves with the new member

### Step 2: Business Logic Generation — configuration and errors
- [x] `src/rfd_web/config.py` — `WebConfig.from_env()` in `PathLayout.from_env()`'s idiom, reading
      the six new variables (`RFD_STATUS_POLL_SECONDS`, `RFD_SLURM_TIMEOUT_SECONDS`,
      `RFD_PARTITION_CACHE_SECONDS`, `RFD_PROGRESS_STALE_SECONDS`, `RFD_INCOMPATIBLE_PARTITIONS`,
      `RFD_LOG_TAIL_LINES`) plus the existing `RFD_DEFAULT_*` submission defaults
      *(domain-entities.md §7)*
- [x] `src/rfd_web/errors.py` — the five exception types *(domain-entities.md §6)*

### Step 3: Business Logic Generation — Slurm state vocabulary (C-21 part 1)
- [x] `src/rfd_web/slurm/states.py` — `SlurmState`, `JobStatus`, `TERMINAL_STATES`, and the **total**
      state map with an `UNKNOWN` fallback *(business-logic-model.md §3.1, BR-7)*

### Step 4: Business Logic Generation — `SlurmAdapter` (C-21 part 2)
- [x] `src/rfd_web/slurm/adapter.py` — `SlurmAdapter` `Protocol` (`submit`, `status`, `cancel`,
      `partitions`) and `CliSlurmAdapter`:
      `sbatch --parsable`; `squeue -h -j <id> -o "%T"` then `sacct -n -P -X -j <id> -o State,ExitCode`;
      `scancel`; `sinfo -h -o "%R|%G|%l|%a"` — all argument lists, `shell=False`, stdout/stderr
      captured, exit codes checked, explicit timeout *(D-1, NFR-11, NFR-13, BR-22)*
- [x] Implement the BR-4 distinction: no row ⇒ `JobStatus(state=UNKNOWN, known=False)`; command
      failure/timeout/missing binary ⇒ `SlurmUnavailable`
- [x] Implement BR-10: decode `sacct`'s `ExitCode` `X:Y` into `exit_code` and `signal`

### Step 5: Business Logic Generation — `FakeSlurmAdapter`
- [x] `src/rfd_web/slurm/fake.py` — scripted queue: increasing job ids, recorded submissions,
      programmable state sequences, `cancel` moving a job to `CANCELLED`, fixture partitions,
      and an injectable "raise `SlurmUnavailable`" mode so BR-4's unreachable path is testable
      *(NFR-18, D-5)*

### Step 6: Business Logic Generation — `PartitionDiscovery` (C-22)
- [x] `src/rfd_web/slurm/partitions.py` — `PartitionInfo`, `discover_partitions(adapter, config)`:
      GPU filter, de-duplication by name, default-partition `*` handling, compatibility
      **annotation** from `RFD_INCOMPATIBLE_PARTITIONS`, TTL cache, and empty-list-plus-warning
      degradation when `sinfo` is unavailable *(FR-6a, Q3=A, business-logic-model.md §4)*

### Step 7: Business Logic Generation — `JobScriptGenerator` (C-23)
- [x] `src/rfd_web/slurm/script.py` — `generate_job_script(record, layout, config, stage) -> str`
      as a **pure function** (no filesystem), and `write_job_script(...) -> Path` writing `job.sh`
      or `job-validate.sh` *(D-6)*
- [x] Emit the corrected `deployment-architecture.md` §3 template verbatim in shape: engine
      **detection** (BR-13), no `--qos` ever (G-3), `--account` only when configured, single-run
      bind, `/app/RFdiffusion/.venv/bin/python -m rfd_runner /opt/outputs/run --stage {stage}`,
      logs into the run directory, fail-fast preconditions, `rc=$?` / `exit $rc`
- [x] Implement BR-12: whitelist every interpolated value, raise `JobScriptError` on violation,
      then `shlex.quote`

### Step 8: Business Logic Unit Testing — Slurm layer
- [x] `tests/test_states.py` — the map is total; unknown words map to `UNKNOWN`, never to
      `COMPLETED`/`FAILED` (BR-7); terminal-state set is correct and excludes `UNKNOWN`
- [x] `tests/test_adapter.py` — `CliSlurmAdapter` against a **stub `PATH`** carrying fake
      `sbatch`/`squeue`/`sacct`/`scancel`/`sinfo` shell scripts: job-id parsing (with and without
      `;cluster`), squeue-then-sacct ordering, `CANCELLED by 1234` first-token handling, `X:Y` exit
      code decoding, no-row ⇒ `known=False`, non-zero exit ⇒ `SlurmUnavailable`,
      timeout ⇒ `SlurmUnavailable`, and an assertion that **no call passes `shell=True`**
- [x] `tests/test_fake.py` — the fake honours the same protocol (a shared contract test parametrised
      over both adapters where the stub `PATH` makes that possible)
- [x] `tests/test_partitions.py` — GPU filtering, de-duplication, default marker, annotation not
      filtration (an incompatible partition is still **returned**), cache hit/expiry,
      `SlurmUnavailable` ⇒ empty list + warning
- [x] `tests/test_script.py` — G-1 … G-18 conformance assertions **rule by rule**, including a
      negative test that `--qos` never appears under any configuration (G-3), that no literal
      `apptainer exec`/`singularity exec` command appears (BR-13), account omitted when unset, and
      `JobScriptError` for each whitelist class (BR-12)

### Step 9: Business Logic Unit Testing — the M1 lesson, by execution
- [x] `tests/test_script_execution.py` — write a generated script to `tmp_path` and **run it under
      `bash`** with a stub engine on `PATH`, covering the four scenarios the M1 fix was verified
      against: only `singularity` present, only `apptainer` present, neither present (exit 127 with
      the G-15 message), and a missing `run.json` (exit 2 **before** the exec). Assert the captured
      exec argv contains `--nv`, all four binds, and the runner invocation.
      *(This is the second M1 lesson from `aidlc-state.md`: round 7's bug was invisible to every
      existing test and cost a GPU allocation. `bash -n` alone would not have caught it.)*

### Step 10: Business Logic Summary
- [x] Record the Slurm-layer decisions and the exact command lines in the unit code summary
      (written in Step 19)

### Step 11: Repository Layer Generation — schema and `RunRepository` (C-24)
- [x] `src/rfd_web/persistence/schema.py` — the DDL from domain-entities.md §5.1 verbatim, WAL,
      `busy_timeout`, `user_version = 1`, idempotent `CREATE TABLE IF NOT EXISTS` + indexes
- [x] `src/rfd_web/persistence/repository.py` — `RunSummary`; `create`, `get`, `list(limit)`,
      `update_state(run_id, **fields)`, `upsert_from_record`, `live_job_ids`,
      `mark_terminal`, `mark_missing`, `mark_cancel_requested`, `append_job_id`
      — single-statement upserts, one connection per operation *(BR-21)*

### Step 12: Repository Layer Generation — `RunDirectoryReader` (C-25)
- [x] `src/rfd_web/persistence/reader.py` — `read_record`, `read_progress`, `current_frame`,
      `list_designs`, `best_design_index` (parses `REMARK 001` of `best.pdb`), `log_tail`
- [x] `log_tail` per Q7=A: newest `job-*.err`, falling back to newest `job-*.out` when empty or
      missing; bounded read of at most 64 KB from the end *(NFR-15)*
- [x] Path containment enforced on every resolved path, symlinks resolved first *(BR-14)*

### Step 13: Repository Layer Generation — startup reconciliation
- [x] `src/rfd_web/persistence/reconcile.py` — `RunIndexReconciler.reconcile_all()`: scan
      `output_root`, upsert every readable `run.json`, flag rows whose directory is gone
      (`missing = 1`, **never** delete), skip-and-warn on an unreadable record *(Q5=A, BR-18/19/20)*

### Step 14: Repository Layer Unit Testing
- [x] `tests/test_repository.py` — against **real SQLite files in `tmp_path`**: create/get/list
      ordering, upsert idempotency, terminal flag, `live_job_ids`, `job_id_history` JSON round-trip,
      WAL and `user_version` actually set, concurrent-writer busy-timeout behaviour
- [x] `tests/test_reader.py` — `.err`-then-`.out` fallback including the empty-`.err` case and
      newest-by-mtime selection across two job ids; `REMARK 001` parsing (present, absent,
      malformed); 64 KB bound honoured on a large log; containment refusal for `../`, an absolute
      path, and a symlink pointing outside the run directory
- [x] `tests/test_reconcile.py` — index rebuilt from directories after the DB is deleted (FR-29);
      a corrupt `run.json` is skipped without aborting the scan (BR-20); a vanished directory is
      flagged, not deleted (BR-19)

### Step 15: Repository Layer Summary
- [x] Record the schema, its index-only columns, and the rebuild guarantee in the unit code summary

### Step 16: Service Layer Generation — S-1 and S-2
- [x] `src/rfd_web/services/submission.py` — `SubmissionOutcome`; `submit(request, template_path)`
      in the documented order (validate → run id → mkdir → template → `run.json` → `job.sh` →
      `sbatch` → index); `resubmit(run_id, stage)` with its preconditions;
      `cancel(run_id)` writing `cancel_requested_at` **before** `scancel` and treating an
      already-finished job as success *(BR-11, BR-15, BR-16, BR-17, §7, §8, §10)*
- [x] Run-id derivation using `mkdir(exist_ok=False)` as the collision test, 4-hex suffix, 8
      attempts *(Q4=A, BR-16)*
- [x] `src/rfd_web/services/query.py` — `RunStatus`, `ProgressView`, `RunView`;
      `get(run_id)` implementing the §9.1 algorithm and the §9.2 reconciliation table exactly;
      `list_runs(limit)` batching one `squeue` for all live runs *(BR-23)*
- [x] Progress overlay per BR-5 (four cases, including the frozen-during-VALIDATE case) and
      `frame_available` from `current_frame.pdb` on disk per BR-6

### Step 17: Service Layer Unit Testing
- [x] `tests/test_submission.py` — invalid request creates **nothing** on disk (FR-5, G-9, BR-11);
      run-id collision produces a suffixed directory and never reuses one; `sbatch` failure retains
      the directory with `backbone_state = FAILED` and the real stderr (BR-15); success writes
      `run.json`, `job.sh` and indexes the job id; `resubmit` refuses without a completed backbone
      or with a live job, and writes `job-validate.sh` without touching `job.sh` (BR-17);
      `cancel` writes `cancel_requested_at` before calling the adapter, and an already-finished job
      is not an error
- [x] `tests/test_query.py` — **one test per row of the §9.2 table**, including the two that matter
      most: `COMPLETED` + non-finalised record ⇒ `FAILED` with log tail (BR-2), and `CANCELLED` ⇒
      cancelled with the runner's walltime sentence suppressed (BR-8). Plus: `TIMEOUT` keeps that
      sentence (BR-9); `SlurmUnavailable` ⇒ last known view marked `stale`, never a state change
      (BR-4); terminal runs issue **zero** Slurm calls on re-read (BR-3, asserted by call counting
      on the fake); the four BR-5 progress cases; `frame_available` true with
      `ProgressState.frame_path` null (BR-6)
- [x] `tests/test_boundaries.py` — `rfd_web` imports with **no** `rfd_runner` on the path (DD-1,
      NFR-2), and no HTTP framework is imported anywhere in the package

### Step 18: Deployment Artifacts
- [x] Update `env.example` **in place** — add the six new variables from domain-entities.md §7 with
      their defaults and the reasoning comments, in the existing file's style
- [x] `packages/rfd-web/README.md` — what the package is, what it deliberately excludes, and how to
      run its suite offline against `FakeSlurmAdapter`

### Step 19: Documentation Generation
- [x] `aidlc-docs/construction/u3-slurm-persistence/code/u3-code-summary.md` — files created,
      test counts and coverage, traceability to FR/NFR/G ids, and an explicit statement of what is
      **not** proven locally (see below)

### Step 20: Verification
- [x] `uv run --package rfd-web --python 3.9 pytest packages/rfd-web/tests -q` — the full U3 suite
      on the real target interpreter
- [x] `uv run --package rfd-core --python 3.9 pytest packages/rfd-core/tests -q` and the same for
      `rfd-runner` — prove this unit's arrival broke nothing (the 231-test baseline from M1)
- [x] Record actual pass counts in the summary. **No test count is claimed before it is observed.**

---

## What This Plan Does Not Claim

Honesty about scope, following the U2b precedent:

- **No real Slurm is exercised.** `CliSlurmAdapter` is tested against stub `sbatch`/`squeue`/`sacct`/
  `sinfo` scripts that emit real Slurm output formats. That proves the parsing and the argument
  lists; it cannot prove Grex's Slurm emits exactly those strings. First real contact is a Grex
  gate, and the plan does not pretend otherwise.
- **No job generated here has been submitted.** Step 9 proves the script's control flow, engine
  detection and exec argv by executing it against a stub engine — which is precisely the class of
  bug that cost M1 a GPU allocation — but the container is not run.
- **`sinfo`'s real column content on Grex is unverified.** Discovery degrades to a free-text
  partition field if the format differs, so a mismatch is a downgrade, not an outage.

---

## Traceability

| Requirement | Steps |
|---|---|
| FR-6, NFR-8 | 2, 7, 8 |
| FR-6a | 6, 8 |
| FR-7 | 16, 17 |
| FR-11 | 16, 17 |
| FR-14 | 16, 17 |
| FR-15, FR-18 | 3, 4, 16, 17 |
| FR-19 | 4, 12, 16, 17 |
| FR-27, FR-28 | 11, 14 |
| FR-29, FR-33 | 13, 14 |
| NFR-10 | 4, 16, 17 |
| NFR-11, NFR-13 | 4, 8 |
| NFR-15, NFR-16 | 2, 4, 6, 12, 16 |
| NFR-18 | 5, 8, 17 |
| G-1 … G-18 | 7, 8, 9 |
| BR-1 … BR-23 | 4–9, 11–14, 16, 17 |
