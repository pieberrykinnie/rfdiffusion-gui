# U3 Slurm and Persistence — Functional Design Plan

**Unit**: U3 Slurm and Persistence (`rfd-web/{slurm,persistence,services}`)
**Stage**: CONSTRUCTION — Functional Design (Part 1: planning + questions)
**Date**: 2026-08-27
**Unblocked by**: Milestone M1 ✅ PASSED 2026-08-27 (job 7556085, real V100, 00:01:27)

---

## Unit Context

**Scope** (from `unit-of-work.md`): C-21 `SlurmAdapter`, C-22 `PartitionDiscovery`,
C-23 `JobScriptGenerator`, C-24 `RunRepository`, C-25 `RunDirectoryReader`, and
S-2 `RunQueryService` — the state-reconciliation service.

**Requirements owned**: FR-6, FR-6a, FR-7, FR-14, FR-15, FR-18, FR-19, FR-27, FR-28, FR-29,
FR-33 · NFR-8, NFR-10, NFR-11 (argument lists, never a shell string), NFR-13, NFR-16, NFR-18 ·
G-1 … G-18 (job-script conformance).

**Depends on**: U2a `rfd-core` (`RunRecord`, `ProgressState`, `PathLayout`, `validate`,
`preview_mode`, atomic JSON) and U1 (the job-script template and bind map).

**Definition of done** (`unit-of-work.md`): a run can be submitted, tracked to completion, and
cancelled programmatically; the full suite passes against a **fake Slurm** with no cluster access.

**Not in scope**: HTTP routes, templates, 3Dmol.js, the submission form — all U4.

**Explicitly deferred to this stage by `services.md`**: S-2's reconciliation rules. The Application
Design says only *"Reconciliation rules (detailed in U3 Functional Design)"* — writing them
precisely is the central deliverable here.

---

## Research Completed Before This Plan

Read against the code that actually ran on Grex, not against the design documents alone. Four
discrepancies between design docs and shipped code were found. None is resolved silently; each is
either a question below or a stated decision.

### F-1 — The section-3 job-script template does not match the runner's real CLI

`deployment-architecture.md` section 3 emits:

```
python3.9 -m rfd_runner --run-dir /opt/outputs/{run_id} --scratch /scratch --stage {stage}
```

The shipped runner (`packages/rfd-runner/src/rfd_runner/__main__.py`) accepts a **positional**
`run_dir` and **only** `--stage`; there is no `--run-dir` and no `--scratch` flag (scratch is
`OrchestratorDeps.dump_dir`, fixed at `/scratch` in the container). The container's interpreter is
`/app/RFdiffusion/.venv/bin/python` (`containers/rfdiffusion.def:467`), not `python3.9` on `PATH`.
The **M1-proven** `scripts/m1-submit.sh` uses the correct form. → **Question 2.**

### F-2 — Bind map: whole output root vs. the single run directory

Section 2's bind map binds `$RFD_OUTPUT_ROOT → /opt/outputs`; the proven M1 script binds only
`${RUN_DIR} → /opt/outputs/run`. The second is tighter (a job cannot see or corrupt other runs) and
is the one with a real successful execution behind it. → **Question 2.**

### F-3 — `scancel` produces a *contradiction* between Slurm and `run.json`

`orchestrator.py:294-303` installs a SIGTERM handler that writes
`backbone_state = FAILED, error = "terminated (SIGTERM) — likely walltime exceeded"` and exits 1.
`scancel` sends SIGTERM. So a **user-initiated cancel** leaves Slurm reporting `CANCELLED` while
`run.json` reports `FAILED` with a message about walltime. S-2 must reconcile this or the UI will
tell the user a cancelled run crashed. → **Question 6.**

### F-4 — Runtime partition discovery can offer a partition the image cannot run on

`env.example` records the verified fact: the Phase 1 CUDA 11.6 image runs on `gpu`, `stamps-b`,
`livi-b` (V100, sm_70) and `agpu`, `mcordgpu-b` (A30, sm_80), but **not** on `lgpu` (L40s, sm_89).
FR-6a mandates runtime discovery and forbids a hard-coded list — so discovery will surface `lgpu`,
which would produce a job that fails on arrival at the GPU. → **Question 3.**

### F-5 — C-26 `RequestValidator` already exists, in `rfd-core`

`rfd_core.validation` already ships `validate()` and `preview_mode()` with the exact
`ValidationOutcome` shape Application Design assigns to C-26. U3 does not re-implement it; S-1 (if
in scope — **Question 1**) calls it.

### F-6 — Two M1 lessons carried in by `aidlc-state.md`

(a) `JobScriptGenerator` must emit **engine detection** (`module load singularity || module load
apptainer`, then `command -v`), never a hardcoded binary name — a hardcoded `apptainer` cost M1 a
whole GPU allocation (job 7556080, exit 127). The fix is already in section 3's template.
(b) `JobScriptGenerator` must be **unit-testable against a fake engine** — that bug was invisible to
every existing test.

---

## Decisions Made Without Asking

Recorded here for visibility; say so in any `[Answer]:` below if you want one revisited.

| # | Decision | Rationale |
|---|---|---|
| D-1 | `SlurmAdapter` invokes `sbatch`/`squeue`/`sacct`/`scancel`/`sinfo` via `subprocess.run` with **argument lists and `shell=False`**, capturing stdout+stderr and checking exit codes | NFR-11, NFR-13 — non-negotiable, already settled at Requirements |
| D-2 | `squeue`/`sacct`/`sinfo` are parsed from **explicit machine formats** (`--noheader --format=…` / `--parsable2 --noheader --format=…`), never from human-readable default output | Default column layouts drift between Slurm versions; parsing them is how status displays start lying |
| D-3 | SQLite is opened with **WAL journal mode**, one connection per request; the DB is an **index**, never the source of truth | AD-6 plus services.md's transaction-boundary note; `RFD_DB` already defaults to `/home` because SQLite locking misbehaves on Lustre |
| D-4 | Poll cadence stays configurable (NFR-16) with a default **status poll of 5 s**, and a **terminal-state cache** so a finished run never triggers another `sacct` | NFR-16 says seconds, not milliseconds; the terminal write-back is already specified in services.md |
| D-5 | Every U3 module is importable with **no cluster present**; all Slurm access goes through the C-21 `Protocol` so the whole suite runs against a fake | NFR-18 and U3's definition of done |
| D-6 | Job scripts are written as `job.sh` inside the run directory and **retained** — never regenerated in place; a resubmit writes `job-validate.sh` alongside | G-2: every run must stay hand-resubmittable exactly as it was submitted |

---

## Plan Steps

- [x] User answers the 8 questions below
- [x] Analyse answers for ambiguity; raise follow-up questions if any answer is vague
      — **all 8 answered `A` (the recommended option); no vague or conditional answers, no follow-ups needed**
- [x] Generate `aidlc-docs/construction/u3-slurm-persistence/functional-design/business-logic-model.md`
      — submission flow, tracking flow, cancellation flow, partition discovery, job-script
      generation, and the S-2 reconciliation algorithm as an explicit state table
- [x] Generate `aidlc-docs/construction/u3-slurm-persistence/functional-design/business-rules.md`
      — reconciliation precedence rules, Slurm-state mapping, submission-failure handling,
      collision/run-id rules, the G-1…G-18 conformance obligations on the generator, and
      path-containment rules
- [x] Generate `aidlc-docs/construction/u3-slurm-persistence/functional-design/domain-entities.md`
      — `SlurmState`, `PartitionInfo`, `RunSummary`, the reconciled read model, the SQLite schema,
      and how each maps to the `rfd-core` contracts
- [x] Update `deployment-architecture.md` section 3's template to match whatever Question 2 settles
      (so the generator and the documented template cannot drift apart again — F-1/F-2)
- [x] Update `aidlc-state.md` and `audit.md`
- [ ] Present the standardised 2-option completion message and wait for explicit approval

---

## Questions

### Question 1
`unit-of-work.md` assigns **S-1 `SubmissionService` to U4**, but U3's own definition of done is
*"a run can be submitted, tracked to completion, and cancelled programmatically"* — which requires
S-1. Everything S-1 needs already exists or is in U3 except C-27 `TemplateUploadHandler` (which
needs FastAPI's `UploadFile`, genuinely U4). How should this be resolved?

A) **Build S-1 in U3**, minus the upload step — it takes an already-resolved template path, and U4
later adds only the HTTP upload handling in front of it. U3's definition of done then becomes
literally achievable and testable end-to-end against a fake Slurm. *(Recommended — the DoD cannot be
met otherwise, and the alternative leaves U3 unverifiable until U4 lands.)*

B) **Leave S-1 in U4** and narrow U3's definition of done to "a job script can be generated and a
job submitted, tracked and cancelled through C-21/C-23/C-24" — the orchestration that ties them
together arrives with U4.

C) Build S-1 in U3 **including** non-HTTP template resolution (server-side path / PDB code / UniProt
accession), leaving only browser file upload to U4.

X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

### Question 2
Finding F-1/F-2: the documented job-script template in `deployment-architecture.md` section 3 does
**not** match either the runner's real CLI or the bind layout of the M1 script that actually
succeeded on Grex. What should `JobScriptGenerator` emit?

A) **Follow the M1-proven script**: bind the single run directory to `/opt/outputs/run`, invoke
`"$ENGINE" exec --nv … "$IMAGE" /app/RFdiffusion/.venv/bin/python -m rfd_runner /opt/outputs/run
--stage {stage}`, and update section 3's template to match. *(Recommended — this exact form has one
successful real execution behind it; the template has none, and F-1's flags do not exist.)*

B) Follow the M1-proven **invocation** but keep the section-2 bind map (bind
`$RFD_OUTPUT_ROOT → /opt/outputs`, pass `/opt/outputs/{run_id}`), so one mount serves every run.

C) Invoke the container's `%runscript` instead of naming the interpreter
(`"$ENGINE" run --nv … "$IMAGE" /opt/outputs/run --stage {stage}`), so the interpreter path lives in
the image definition only and the generator never hardcodes it.

X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

### Question 3
Finding F-4: FR-6a requires partitions be **discovered at runtime**, never hard-coded — but
discovery will surface `lgpu`, which the Phase 1 CUDA 11.6 image cannot run on (L40s, sm_89).
What should `PartitionDiscovery` do about known-incompatible partitions?

A) **Discover all GPU partitions, annotate compatibility, and let the user choose** — marking
incompatible ones with a warning driven by a *configurable* env list
(`RFD_INCOMPATIBLE_PARTITIONS="lgpu"`) rather than a constant in code. FR-6a is satisfied (the list
itself is discovered) and the sm_89 trap is visible without being hidden. *(Recommended.)*

B) **Discover all GPU partitions and offer them all, unfiltered** — the image is the user's to
change, and any filtering risks becoming the hard-coded list FR-6a forbids.

C) **Discover, then filter incompatible partitions out entirely** so an unusable choice cannot be
made at all.

D) Read GPU **architecture** per partition from `sinfo`'s GRES/feature fields and compare it against
a compatibility floor declared by the image, so no partition name is ever named anywhere.

X) Other (please describe after [Answer]: tag below)

[Answer]:  A

---

### Question 4
FR-7 requires a collision-free run name, *"preserving the notebook's behaviour of appending a random
suffix when the chosen name is taken."* `PathLayout.run_dir(run_id)` makes `run_id` the directory
name, so it must be filesystem-safe. What should `run_id` be?

A) **Sanitised user name, with a random suffix only on collision** — `my-binder`, then
`my-binder_a3f9` if that directory already exists. Closest to notebook parity; directory names stay
human-meaningful. *(Recommended.)*

B) **Sanitised name + UTC timestamp, always** — `my-binder-20260827T210500Z`. Never collides, sorts
chronologically, and matches what `scripts/m1-prepare-run.sh` already does.

C) **Opaque id** (UUID/ULID) as the directory name, with the human name carried only inside
`run.json` and the SQLite index.

X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

### Question 5
FR-29 requires surviving a web-app restart with **no loss of run state, including for jobs still
running**. The SQLite index can be stale or absent (deleted DB, a run directory copied in from
elsewhere, a crash between the `run.json` write and the SQLite insert — services.md explicitly
permits that ordering). What should happen at startup?

A) **Scan `RFD_OUTPUT_ROOT` at startup and reconcile** every `run.json` found into SQLite
(insert-or-update), so the directory tree is provably the source of truth and a lost DB costs
nothing. *(Recommended — FR-33's self-describing run directories only pay off if something actually
reads them back.)*

B) **Lazy repair**: trust SQLite for the run list, and reconcile a run from its directory only when
that run is opened. Cheaper at startup; a run missing from the index stays invisible until found.

C) **Scan at startup and on every run-list render**, so a directory dropped in while the app is
running appears without a restart.

X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

### Question 6
Finding F-3: after `scancel`, Slurm reports `CANCELLED` while the runner's own SIGTERM handler has
already written `backbone_state = FAILED` with the message *"terminated (SIGTERM) — likely walltime
exceeded"*. Both `TIMEOUT` and a user cancel reach the runner as the same signal. How should S-2
reconcile this?

A) **Slurm wins on the *kind* of ending; `run.json` supplies the detail.** `CANCELLED` → report
cancelled, suppressing the runner's misleading walltime message; `TIMEOUT` → report timed out and
keep it. Additionally record `cancel_requested_at` when the app issues `scancel`, so a user cancel
is distinguishable from an admin cancel or a preemption. *(Recommended.)*

B) Slurm wins on the kind of ending, **without** recording who requested the cancel — a cancel is a
cancel, and the extra field is state the UI does not need.

C) Fix it at the source instead: change the runner's SIGTERM handler (U2b) to write a neutral
`error` string, and have S-2 map Slurm's state straight through. Cleaner, but reopens an approved
unit and would want another real-hardware run to confirm.

X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

### Question 7
FR-19 requires surfacing failures with **the tail of the job log and the Slurm exit code**. The
generated script writes `job-%j.out` and `job-%j.err` into the run directory, and
`RunDirectoryReader` already has `log_tail(run_dir, lines=50)`. Which log should it read?

A) **`.err` first, falling back to `.out` when `.err` is empty** — the failure is nearly always in
stderr, and the Python traceback that ended M1 rounds 1–6 was always there. *(Recommended.)*

B) **Both, concatenated and labelled** (`--- job-*.err ---` then `--- job-*.out ---`) — the M1 chain
repeatedly needed both together (round 7's exit 127 was one line in `.err`, but the context that
made it legible was in `.out`).

C) **`.out` only** — it carries the script's own `Starting run at` / `Job finished with exit code`
markers, which frame the failure.

X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

### Question 8
FR-11 gives the runner `--stage {all,backbone,validate}` *"so validation can be resubmitted against
an existing run directory without repeating backbone generation."* Nothing in U3's component list
exposes that. Should U3 support resubmission?

A) **Yes — U3 provides `resubmit(run_id, stage)`**, generating a second job script
(`job-validate.sh`), submitting it, and resetting `validate_state` to pending. FR-11 otherwise has
no caller anywhere in the system. *(Recommended — the capability was built in U2b and verified;
leaving it unreachable wastes it.)*

B) **No — defer to U4**, which owns the UI that would trigger it; U3 ships submit/track/cancel only.

C) Yes, and **generalise it**: one `submit(run_id, stage)` path, where the initial submission is
simply `stage=all` — two entry points collapse into one.

X) Other (please describe after [Answer]: tag below)

[Answer]: A
