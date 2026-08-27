# U3 Slurm and Persistence — Code Generation Summary

**Unit**: U3 (`packages/rfd-web`)
**Stage**: CONSTRUCTION — Code Generation (Part 2)
**Date**: 2026-08-27
**Result**: **225 tests, 96% coverage, on real Python 3.9.25** — plus the pre-existing
231 tests (`rfd-core` 157, `rfd-runner` 74) re-run and still passing. **456 total.**

---

## Verification Actually Performed

Not claims — commands that were run, with their output:

| Command | Result |
|---|---|
| `uv run --package rfd-web pytest packages/rfd-web/tests -q` | **225 passed** |
| `… --cov=rfd_web` | **96%** (1023 statements, 36 uncovered) |
| `uv run --package rfd-core pytest packages/rfd-core/tests -q` | **157 passed** (unchanged) |
| `uv run --package rfd-runner pytest packages/rfd-runner/tests -q` | **74 passed** (unchanged) |
| `uv lock` | workspace resolves with three members at `==3.9.*` |

The suite uses **real** SQLite files in `tmp_path`, **real** directories, **real** `bash`,
and **real** subprocesses against stub Slurm binaries on `PATH`. The only thing faked is
Slurm itself — which is the seam NFR-18 exists for.

### Per-module coverage

| Module | Cover |
|---|---|
| `config.py`, `errors.py`, `status.py`, `schema.py`, `fake.py`, `__init__.py` | 100% |
| `services/submission.py` | 99% |
| `persistence/reconcile.py`, `slurm/partitions.py` | 98% |
| `slurm/script.py` | 97% |
| `services/query.py`, `slurm/states.py` | 96% |
| `persistence/repository.py` | 95% |
| `persistence/reader.py` | 93% |
| `slurm/adapter.py` | 92% |

The uncovered remainder is defensive error handling on real I/O (unreadable files mid-scan,
OSError paths) — the branches that exist so a login-node process does not die on a
filesystem hiccup.

---

## Files Created

All application code at the workspace root; nothing executable in `aidlc-docs/`.

### Package (`packages/rfd-web/`)

- `pyproject.toml` — `requires-python = ">=3.9,<3.10"`, depends on `rfd-core` only
- `README.md`
- `src/rfd_web/__init__.py` — 30 public exports · `py.typed`
- `src/rfd_web/config.py` — `WebConfig.from_env()`
- `src/rfd_web/errors.py` — `SlurmError`, `SlurmUnavailable`, `SlurmSubmitError`,
  `JobScriptError`, `PathContainmentError`
- `src/rfd_web/status.py` — `RunStatus`, `TERMINAL_RUN_STATUSES`

### Slurm (`src/rfd_web/slurm/`)

- `states.py` — `SlurmState`, `JobStatus`, the total state map, `parse_exit_code`
- `adapter.py` — `SlurmAdapter` (Protocol) and `CliSlurmAdapter` (**the only subprocess
  site in the package**, asserted by a test)
- `fake.py` — `FakeSlurmAdapter`, shipped in `src/` so U4 can run offline
- `partitions.py` — `PartitionInfo`, `discover_partitions`, `PartitionCache`
- `script.py` — `generate_job_script` (pure), `write_job_script`, `JobScriptGenerator`,
  `JobStage`

### Persistence (`src/rfd_web/persistence/`)

- `schema.py` — DDL, WAL/busy-timeout pragmas, `user_version`
- `repository.py` — `RunRepository`, `RunSummary`
- `reader.py` — `RunDirectoryReader` and its module-level functions
- `reconcile.py` — `RunIndexReconciler`, `status_from_record`

### Services (`src/rfd_web/services/`)

- `submission.py` — `SubmissionService` (`submit`, `resubmit`, `cancel`),
  `SubmissionOutcome`, `sanitise_run_id`
- `query.py` — `RunQueryService`, `RunView`, `ProgressView`, `record_is_finalised`

### Tests (`packages/rfd-web/tests/`, 225 tests)

`conftest.py`, `test_states.py`, `test_config.py`, `test_adapter.py`, `test_fake.py`,
`test_partitions.py`, `test_script.py`, `test_script_execution.py`, `test_repository.py`,
`test_reader.py`, `test_reconcile.py`, `test_submission.py`, `test_query.py`,
`test_boundaries.py`

### A test that was wrong, found by running the suites in sequence

`test_boundaries.py` originally asserted that `import rfd_runner` **raises** in the
`rfd-web` environment. It passed until the `rfd-core` and `rfd-runner` suites were run in
the same tree, and then failed — because **a uv workspace shares one `.venv`**, so running a
sibling package's tests makes that sibling importable. The assertion was testing the
interpreter's history, not `rfd-web`.

The code was never wrong; the test was. It is now split into the two claims that are
actually binding: importing `rfd_web` must not pull `rfd_runner` into `sys.modules`, and
`rfd-web`'s manifest must declare no dependency on it — the manifest being what decides
what `uv sync` installs on the login node, which is the thing NFR-2 is really about.

## Files Modified

- `pyproject.toml` (root) — corrected the Python-version comment (see below)
- `uv.lock` — `rfd-web` added as the third workspace member
- `env.example` — six new variables with their reasoning
- `aidlc-docs/construction/u3-slurm-persistence/functional-design/domain-entities.md` —
  §8 corrected
- `aidlc-docs/construction/plans/u3-code-generation-plan.md` — Step 1 correction recorded

---

## The One Correction Made During Generation

**`rfd-web` cannot target Python ≥ 3.11.** The plan, `domain-entities.md` §8, and the root
`pyproject.toml`'s own comment (written back in U2a) all said it did. `uv lock` refused
immediately:

```
error: Found conflicting Python requirements:
- rfd-core: >=3.9, <3.10
- rfd-runner: >=3.9, <3.10
- rfd-web: >=3.11
```

The deeper reason is not a uv quirk: **`rfd-web` depends on `rfd-core`, and `rfd-core` is
capped below 3.10 so it can import inside the U1 container.** Any environment that can
import `rfd-core` is therefore a 3.9 environment — the login node included. A 3.11
`rfd-web` was never installable, and the root comment's claim that "uv resolves each
package's own environment independently" is simply not how a uv workspace works: one
workspace, one lockfile, one `requires-python` intersection.

The alternative — making `rfd-web` a standalone project with its own lockfile — would
break DD-1's approved *"uv workspace, three packages"*. So the package targets
`>=3.9,<3.10` like its siblings, carries the same `UP045`/`UP007` ruff ignore for the same
pydantic reason, and the claim is corrected in all four places it appeared.

---

## Design Decisions Made During Generation

| # | Decision | Why |
|---|---|---|
| 1 | `RunStatus` lives in `rfd_web/status.py`, not in `services/query.py` as `domain-entities.md` §4 says | The repository *stores* it and the service *produces* it; importing the service from the repository would invert the layering and create a cycle. `services.query` re-exports it, so the documented import path still works |
| 2 | `SlurmAdapter.status()` returns `JobStatus`, not `SlurmState` | Refinement R-1, already recorded in the Functional Design: `state() -> SlurmState` cannot carry the exit code FR-19 requires |
| 3 | `squeue` is asked for `%T\|%r`, not just `%T` | The queue *reason* ("Resources", "Priority") is what makes a long PENDING legible instead of looking like a stall — mitigation R-6 in requirements.md §9 |
| 4 | `squeue`'s non-zero exit for an unknown job is **not** an outage | `squeue -j <finished>` exits 1 with "Invalid job id specified". Treating that as `SlurmUnavailable` would send every finished run down BR-4's stale path. The stderr is inspected to tell the two apart |
| 5 | `#SBATCH` values are whitelisted but **not** `shlex.quote`d; shell-body values are both | `#SBATCH` lines are read by Slurm, not by a shell — quoting there would put literal quote characters into a filename. A path that cannot be written unquoted is refused loudly instead (test: `test_br12_a_path_that_cannot_be_written_unquoted_is_refused`) |
| 6 | `cd "${SLURM_SUBMIT_DIR:-<run_dir>}"` is emitted with double quotes, not `shlex.quote` | `shlex.quote` would single-quote the expression and defeat the parameter expansion — a silent breakage. Safe because `_check_path` has already refused any `$`, quote, backslash or whitespace |
| 7 | `JobStage` is re-declared in `script.py` rather than imported from `rfd_runner` | `rfd-web` must never depend on `rfd-runner` (DD-1, NFR-2). It is a three-value command-line contract, not shared logic |

---

## What Is Proven, and What Is Not

**Proven locally, by execution:**

- The generated job script **runs** under real `bash` and resolves the container engine
  correctly in all four M1 scenarios: only `singularity` present, only `apptainer`
  present, neither (exit 127 with the G-15 message), and a missing `run.json` (exit 2
  *before* the exec, with the engine provably never invoked). The exec argv is captured
  and asserted — `--nv`, all four binds, and
  `/app/RFdiffusion/.venv/bin/python -m rfd_runner /opt/outputs/run --stage all`.
- A runner failure's exit code survives to the script's own exit code (`rc=$?`), which is
  what FR-19's `sacct` reporting depends on.
- G-1 … G-18 conformance, rule by rule, including a negative test that `--qos` never
  appears under any configuration and that no literal `apptainer exec`/`singularity exec`
  command is ever emitted.
- Every row of the S-2 reconciliation table, including the two that carry the most
  weight: Slurm `COMPLETED` with a non-finalised `run.json` reported as **FAILED**
  (BR-2), and `CANCELLED` suppressing the runner's misleading walltime sentence (BR-8).
- A terminal run issues **zero** further Slurm calls, asserted by call-counting on the
  fake (BR-3).
- The index rebuilds from run directories after the database is deleted (FR-29), skips a
  corrupt `run.json` without aborting startup (BR-20), and flags — never deletes — a
  vanished directory (BR-19).
- `rfd_web` imports with **no** `rfd_runner` installed, no HTTP framework, and no
  torch/JAX anywhere.

**Not proven, and stated plainly:**

- **No real Slurm was contacted.** `CliSlurmAdapter` was exercised against stub binaries
  emitting real Slurm output formats. That proves the parsing and the argument lists; it
  cannot prove Grex's Slurm emits exactly those strings. First real contact is a Grex
  gate.
- **No generated job has been submitted.** The script's control flow, engine detection and
  exec argv are proven; the container was not run.
- **`sinfo`'s real column content on Grex is unverified.** If the format differs,
  discovery degrades to a free-text partition field pre-filled from
  `RFD_DEFAULT_PARTITION` — a downgrade, not an outage.
- **`squeue`/`sacct`/`scancel` error strings are assumed.** The "Invalid job id" marker
  matching (decision 4) is based on documented Slurm messages, not on Grex's output.

---

## Two M1 Findings Resolved Here

`aidlc-state.md` recorded both as U4 prerequisites. Neither is deferred:

1. **`progress.json` freezes when BACKBONE ends** — `ProgressReporter` is wired only into
   `_run_backbone`. BR-5 reports that as *"validating (no step-level progress
   available)"*, not as a stalled bar (`test_stale_progress_during_validation_is_healthy_work_not_a_stall`).
2. **`ProgressState.frame_path` is never populated** — the orchestrator calls
   `update_step()` but never `set_frame()`. BR-6 derives `frame_available` from
   `current_frame.pdb` existing on disk, so FR-17's live preview works regardless
   (`test_frame_available_is_true_even_though_progress_frame_path_is_null`).

---

## Traceability

| Requirement | Implementation | Test |
|---|---|---|
| FR-6, NFR-8 | `script.py` `#SBATCH` block; `WebConfig` defaults | `test_script.py` G-4…G-8 |
| FR-6a | `partitions.py` — `sinfo`, no list in code | `test_partitions.py` |
| FR-7 | `sanitise_run_id` + `mkdir(exist_ok=False)` | `test_submission.py` |
| FR-11 | `SubmissionService.resubmit` | `test_submission.py`, `test_script_execution.py` |
| FR-14 | `SubmissionService.cancel` | `test_submission.py` |
| FR-15, FR-18 | `states.py`, `query.py` | `test_states.py`, `test_query.py` |
| FR-19 | `JobStatus.exit_code`, `log_tail` | `test_reader.py`, `test_query.py` |
| FR-27, FR-28 | `RunRepository.list`, schema | `test_repository.py` |
| FR-29, FR-33 | `RunIndexReconciler` | `test_reconcile.py` |
| NFR-10 | distinct QUEUED/FAILED/CANCELLED/TIMEOUT/UNKNOWN | `test_query.py` |
| NFR-11, NFR-13 | `CliSlurmAdapter._run` | `test_adapter.py::test_no_slurm_call_ever_uses_a_shell` |
| NFR-15, NFR-16 | timeouts, caches, terminal short-circuit, bounded log read | `test_adapter.py`, `test_partitions.py`, `test_query.py`, `test_reader.py` |
| NFR-18 | `SlurmAdapter` Protocol + `FakeSlurmAdapter` | `test_fake.py`, the whole suite |
| G-1 … G-18 | `script.py` | `test_script.py`, `test_script_execution.py` |
| BR-1 … BR-23 | throughout | every test file |

---

## Handover to U4

- **Use `RunQueryService.get()` for anything status-shaped.** It is the only place
  reconciliation is allowed to happen; a route that reads `run.json` and Slurm itself will
  start lying.
- **`RunView` is the render model.** `list_runs()` is index-only and makes no Slurm call —
  keep it that way for the run list, and refresh individual runs through `get()`.
- **`RunDirectoryReader.resolve_within()` already enforces path containment**, which is
  what S-3's `GET /runs/{id}/file/{path}` endpoint needs. Use it rather than re-deriving.
- **`PartitionCache.get()` returns a `DiscoveryResult`** carrying a `warning`; when it is
  set, render a free-text partition field pre-filled from `RFD_DEFAULT_PARTITION`.
  Incompatible partitions are present and selectable with an `incompatible_reason` —
  show it, do not filter them out.
- **`SubmissionService.submit()` takes a resolved template path.** C-27
  `TemplateUploadHandler` goes in front of it; nothing inside U3 needs changing.
- **`FakeSlurmAdapter` is importable from `rfd_web`**, so the whole app can be developed
  and demoed off-cluster.
