# U3 Slurm and Persistence — Business Rules

**Unit**: U3 (`packages/rfd-web/src/rfd_web/{slurm,persistence,services}`)
**Stage**: CONSTRUCTION — Functional Design
**Date**: 2026-08-27

Rules are numbered `BR-n` and are binding on Code Generation. Each states what must hold and why —
the "why" is the part that survives a refactor.

---

## 1. Source Precedence — Which Truth Wins

### BR-1 — Each source is authoritative for exactly one thing

- **Slurm** is authoritative for **job** state: queued, running, or how it ended.
- **`run.json`** is authoritative for **pipeline** state: which stage reached which outcome, the
  error text, the normalised contigs, the outputs.
- **`progress.json`** is authoritative for **within-stage** progress and nothing else.
- **SQLite** is authoritative for **nothing**. It is an index and a cache.

No component may consult a source outside its authority. `progress.json` never determines whether a
run succeeded; Slurm never determines which design files exist.

### BR-2 — Success requires agreement; failure does not

A run is reported `COMPLETED` **only** when Slurm reports `COMPLETED` **and** `run.json` is finalised
with `error` null. Any other combination that includes a terminal Slurm state is reported as a
failure with the log tail attached.

*Why*: the asymmetry is deliberate. A job killed after its last checkpoint but before writing its
terminal record exits 0 and looks, to Slurm alone, exactly like a success. Reporting that as success
hands the user output files that were never validated. Under-reporting success is recoverable; a
false success is not.

### BR-3 — A terminal state is written back once and never re-queried

When reconciliation yields a terminal status, the index row is updated with the state, exit code and
`terminal = 1`. Subsequent reads short-circuit before any Slurm call.

*Why*: NFR-16 — the run list must not fire an `sacct` per row per poll. This is also the only reason
the index is allowed to hold Slurm state at all.

### BR-4 — "Slurm has no record" and "Slurm is unreachable" are different states

`SlurmAdapter` returns `UNKNOWN` with `known=False` only when both `squeue` and `sacct` ran
successfully and returned no row. A command that fails, times out, or is missing from `PATH` raises
`SlurmUnavailable`.

`RunQueryService` treats them differently: the first is a fact about the job (accounting retention
expired), the second is a fact about the environment, answered by returning the last known view
marked `stale` with an explanation.

*Why*: conflating them turns a five-second controller hiccup into a UI that reports running jobs as
lost.

### BR-5 — A stale progress file is never rendered as live progress

`progress.json` is read only when the reconciled status is `RUNNING`, and only counted as current
when its `updated_at` is within `RFD_PROGRESS_STALE_SECONDS` (default 120). Beyond that:

- if `run.json` has `backbone_state = COMPLETED`, report **"validating (no step-level progress
  available)"**;
- otherwise report running with an explicit "no progress update for X minutes" warning.

*Why*: verified on the M1 pass — `ProgressReporter` is wired into `_run_backbone` only, so
`progress.json` **necessarily** freezes at the end of backbone generation and stays frozen for the
whole validation stage. Without this rule the UI shows a stalled bar during entirely healthy work.

### BR-6 — Live-preview availability is decided by the file, not by `progress.json`

`frame_available` is true when `current_frame.pdb` exists in the run directory. `ProgressState.frame_path`
is not consulted.

*Why*: also verified on the M1 pass — the orchestrator calls `update_step()` but never
`set_frame()`, so `frame_path` stays `null` for an entire successful run while the frame file is
published correctly. Trusting the field would disable FR-17 for no reason.

---

## 2. Slurm State Mapping

### BR-7 — The state map is total, and its fallback is `UNKNOWN`

Every Slurm state string maps through the table in business-logic-model.md §3.1. An unrecognised
state maps to `UNKNOWN` — never to `COMPLETED`, and never to `FAILED`.

*Why*: Slurm gains states across versions. A default of `COMPLETED` fabricates success; a default of
`FAILED` cries wolf. `UNKNOWN` is the only honest answer to an unrecognised word.

### BR-8 — `CANCELLED` suppresses the runner's walltime message (Q6=A)

When Slurm reports `CANCELLED`, the `error` string written by the runner's SIGTERM handler
(*"terminated (SIGTERM) — likely walltime exceeded"*) is **not** displayed. The reported detail is
derived from `cancel_requested_at` instead: set ⇒ *"cancelled from this app"*, unset ⇒ *"cancelled by
the scheduler or an administrator"*.

*Why*: `scancel` and a walltime kill are the same signal to the runner, so it cannot tell them apart
and guesses. Slurm can tell them apart. When Slurm says `CANCELLED`, the runner's guess is simply
wrong, and showing a wrong explanation is worse than showing none.

### BR-9 — `TIMEOUT` keeps the runner's message

When Slurm reports `TIMEOUT`, the same runner message **is** shown, together with the requested
walltime.

*Why*: in this case the runner's guess is correct and is the more informative of the two — it names
the stage and step the run had reached.

### BR-10 — The Slurm exit code comes from `sacct`, decoded from `State:Signal`

`sacct`'s `ExitCode` field has the form `X:Y`. The reported exit code is `X`; a non-zero `Y` (a
signal) is surfaced in the reason text.

*Why*: FR-19 requires the exit code specifically. Reporting `130:0` or the raw `X:Y` string to a user
who is trying to find out why their design failed is noise.

---

## 3. Submission

### BR-11 — Validate before creating anything; cancel is idempotent

**Submission**: `rfd_core.validate(request)` runs first. On rejection, no run directory, no record,
no script, no job (FR-5, G-9).

**Cancellation**: `scancel` against an already-finished job exits non-zero. That is a **success**,
not an error — the user asked for the job to stop and it has stopped.

*Why*: G-9 asks that cheap validation happen before a GPU is held. And an error dialog for "the thing
you wanted already happened" trains users to ignore error dialogs.

### BR-12 — Every value interpolated into a job script is whitelisted, then quoted

Before generation, each interpolated value must match its whitelist:

| Value | Whitelist |
|---|---|
| `run_id`, `job-name` | `[A-Za-z0-9._-]{1,64}` |
| `partition`, `account` | `[A-Za-z0-9_-]{1,64}` |
| `walltime` | `\d+-\d{2}:\d{2}:\d{2}` or `\d{1,3}:\d{2}:\d{2}` |
| `mem_per_cpu` | `\d+[KMGT]?` |
| `gpus`, `cpus_per_task` | positive integers, `gpus >= 1` |
| paths | absolute, no newline, no NUL |
| `stage` | one of `all`, `backbone`, `validate` |

A value that fails its whitelist raises — generation does not "sanitise and continue". Values that
pass are additionally emitted through `shlex.quote`.

*Why*: NFR-11 removes shell interpretation from *subprocess* calls, but a generated job script is a
shell script by definition, and its inputs come from a web form. Whitelist-then-quote is belt and
braces, and failing loudly is what keeps a silently mangled `--time` from turning into a job that
dies three hours in.

### BR-13 — A job script never names a container binary

Generated scripts must emit `module load singularity || module load apptainer`, resolve
`ENGINE=$(command -v singularity || command -v apptainer)`, and exit 127 with the G-15 message if
neither resolves. The literal strings `apptainer exec` and `singularity exec` must not appear as the
command.

*Why*: M1 job 7556080 died at exit 127 before the container started because the script named the
CCEnv binary while Grex's module provides `singularity`. It cost a GPU allocation to discover
something not GPU-dependent at all, and this generator would have reproduced that bug into every
job script the app ever writes.

### BR-14 — Every path resolved from a run directory must stay inside it

`RunDirectoryReader` resolves each requested path and refuses it unless the resolved result is
within the run directory. Symlinks are resolved before the check.

*Why*: U4's `GET /runs/{id}/file/{path}` endpoint takes a path parameter. Enforcing containment at
the reader means no route can be written that bypasses it.

### BR-15 — A failed submission keeps its run directory

When `sbatch` fails, the record is retained with `backbone_state = FAILED` and the real `sbatch`
stderr in `error`; the directory and generated script are left in place.

*Why*: NFR-10 — the user must see *why*. A retained directory with its script intact is also
hand-resubmittable once the cause is fixed, which cleanup would throw away.

### BR-16 — Run ids are made unique by `mkdir`, not by a prior existence check

Directory creation uses `exist_ok=False` and treats `FileExistsError` as the collision signal, then
retries with a fresh 4-hex suffix (up to 8 attempts).

*Why*: `if exists(): ...` followed by `mkdir()` is a race. Two submissions a millisecond apart must
never share a run directory — that would interleave two jobs' `run.json` writes.

### BR-17 — Resubmission requires a completed backbone and no live job

`resubmit` refuses unless `backbone_state = COMPLETED` and the run's reconciled status is terminal.
It writes `job-validate.sh` alongside `job.sh` and never overwrites the original.

*Why*: a second job writing into a directory a live job still owns corrupts both. And G-2 requires
that the script a run was originally submitted with remains on disk exactly as submitted.

---

## 4. Persistence

### BR-18 — The index is rebuildable, and startup rebuilds it (Q5=A)

Every column in the SQLite schema is derivable from a run directory. Startup scans
`RFD_OUTPUT_ROOT` and upserts every readable `run.json`.

*Why*: FR-29 plus FR-33. If the index held anything the directory does not, a lost database would be
a lost run, and self-describing run directories would be a claim nobody tested.

### BR-19 — A run directory that disappears is flagged, never deleted from the index

Rows whose `run_dir` no longer exists are marked `missing = 1`.

*Why*: deleting the row destroys the only remaining evidence the run existed. A flagged row lets the
UI say "this run's directory is gone", which is information; silence is not.

### BR-20 — One unreadable run directory must not prevent startup

Reconciliation skips a directory whose `run.json` is missing, empty or invalid, logs it, and
continues.

*Why*: `rfd_core.read_json` already returns `None` rather than raising for exactly this case. A
half-written record from a crashed job is an expected state, not a reason the app cannot start.

### BR-21 — SQLite writes are single-statement upserts under WAL

`INSERT ... ON CONFLICT(run_id) DO UPDATE`, WAL journal mode, one connection per operation, a busy
timeout set explicitly.

*Why*: the app is single-user (AD-7) but not single-threaded — HTMX polling and a submission can
overlap. WAL plus a busy timeout is what keeps a poll from failing with "database is locked" while a
submission commits. `RFD_DB` stays on `/home` because SQLite locking misbehaves on Lustre.

---

## 5. Resource Behaviour

### BR-22 — Every Slurm call is bounded

All `subprocess` invocations use an explicit timeout (`RFD_SLURM_TIMEOUT_SECONDS`, default 30). A
timeout raises `SlurmUnavailable` and is handled per BR-4.

*Why*: NFR-15 — this process lives on a shared login node. An unbounded `sacct` against a wedged
controller pins a worker indefinitely.

### BR-23 — Polling cadence is configurable, in seconds, and never per-row

Status polling defaults to 5 s (`RFD_STATUS_POLL_SECONDS`). Partition discovery is cached for 300 s.
A run-list render issues **no** Slurm call for terminal runs (BR-3), and batches the live ones into a
single `squeue` query rather than one call per run.

*Why*: NFR-16, explicitly contrasted in the requirements with the notebook's 10 Hz filesystem poll.
Grex's controller is shared infrastructure.

---

## 6. Grex Conformance Obligations on the Generator (G-1 … G-18)

These are conditions on the emitted script, and every one of them is a test.

| Rule | Obligation on `JobScriptGenerator` |
|---|---|
| **G-1** | Emit `#!/bin/bash`, the `#SBATCH` block, a `cd` into the submit directory, `echo "Starting run at: $(date)"`, and a closing `echo "Job finished with exit code $rc at: $(date)"` |
| **G-2** | Write the script into the run directory and never overwrite it; a bare `sbatch job.sh` must reproduce the run |
| **G-3** | **Never** emit `--qos=`, under any configuration; the explanatory comment is retained |
| **G-4** | Always emit `--time` and `--mem-per-cpu`; neither may be omitted or defaulted by Slurm |
| **G-5** | Always emit `--gpus=N` with `N >= 1` |
| **G-6** | Always emit `--partition=` |
| **G-7** | Default `gpus` to 1 |
| **G-8** | Default `cpus_per_task` to 6 and `mem_per_cpu` to `6000M` |
| **G-9** | Validation runs in the web app before submission, so no job is queued only to fail on bad input |
| **G-10** | One `sbatch` per user action; no loops, no automatic retry of a submission |
| **G-11** | Bind `$TMPDIR` to `/scratch`; per-step dumps never touch shared storage |
| **G-12** | `export SLURM_TMPDIR=$TMPDIR` |
| **G-13** | Outputs are written to the bound run directory, which is persistent storage — staging out is by construction, not by a copy step |
| **G-15** | `module load singularity \|\| module load apptainer`, then detection (BR-13) |
| **G-16** | Reference the pre-staged image by path; never pull |
| **G-17** | Emit `--nv` |
| **G-18** | Export both `APPTAINER_CACHEDIR` and `SINGULARITY_CACHEDIR` |

**G-14** (node-local scratch size) and **G-19/G-20** (SSH and MFA) place no obligation on this unit;
they are satisfied by U1's documentation and by the runner's `$TMPDIR` usage.

---

## 7. Failure Taxonomy

| Condition | Type | Surfaced as |
|---|---|---|
| Invalid `DesignRequest` | value — `ValidationOutcome(ok=False)` | Form errors; nothing created |
| `sbatch` non-zero | value — `SubmissionOutcome(ok=False)` | Run retained, `backbone_state = FAILED`, stderr shown (BR-15) |
| `squeue`/`sacct`/`sinfo` failure or timeout | exception — `SlurmUnavailable` | Last known view, marked stale (BR-4) |
| Job ended, record not finalised | reconciled value | `FAILED` plus log tail (BR-2) |
| Job cancelled | reconciled value | `CANCELLED` (BR-8) |
| Job timed out | reconciled value | `TIMEOUT` (BR-9) |
| Slurm has forgotten the job | reconciled value | Record outcome, or `UNKNOWN` if never finalised |
| Whitelist violation during generation | exception — `JobScriptError` | Programming/config error; must not reach a user as a mangled job |
| Path escapes the run directory | exception — `PathContainmentError` | Refused read (BR-14) |
| Unreadable `run.json` during reconciliation | logged and skipped | Startup continues (BR-20) |

Following U2a's established principle: **errors a user needs to see and act on are values**;
exceptions are reserved for states that indicate a bug in the calling code or an unusable
environment.
