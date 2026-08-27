# U3 Verification on Grex

**What this is for.** U3's own suite — 228 tests, 96% coverage — passes locally against
`FakeSlurmAdapter` and stub binaries. That proves every reconciliation rule, every
argument list, and the whole job script including its execution under `bash`. What it
**cannot** prove is that Grex's Slurm emits the strings this code parses. This document
closes that gap, the way `docs/m1-verification.md` closed U1's.

U3 has **no web UI** — that is U4. So verification drives the services directly.

---

## Prerequisites

Everything M1 already required, plus a synced web environment:

```bash
cd ~/rfdiffusion-gui
git pull                       # or however this branch reaches the cluster
uv sync                        # installs rfd-core + rfd-web; no GPU, no PyTorch
```

`uv sync` must succeed with **Python 3.9** — `rfd-web` shares the workspace's
`requires-python` because it depends on `rfd-core`, which is capped below 3.10 so it can
import inside the container.

Then load your configuration into the environment. The script reads `os.environ`, not
`.env`, so source it first:

```bash
set -a && . .env && set +a
```

---

## Phase 1 — read-only (start here; costs nothing)

```bash
uv run --package rfd-web python scripts/u3-verify.py --phase read-only
```

No job is submitted. This is safe to run repeatedly on a login node and is where the
genuinely unverified things live.

| Check | What it proves | If it fails |
|---|---|---|
| 1. Environment | `.env` resolves to real paths | Fix `.env`; `WARN` on a not-yet-created path is fine |
| 2. **Partition discovery** | `sinfo -h -o '%P\|%G\|%l\|%a'` parses on **real Grex output** (FR-6a) | The highest-risk check here. Compare against `sinfo -h -o '%P\|%G\|%l\|%a'` run by hand |
| 3. **Job status parsing** | `squeue` → `sacct` fallback, `CANCELLED by <uid>`, `ExitCode` `X:Y` decoding, and the BR-4 distinction between "no such job" and "controller unreachable" | See below |
| 4. Job script | G-1 … G-18 on a script generated from a real `RunRecord`, plus `bash -n` | Compare the printed script against `scripts/m1-submit.sh` |
| 5. Index reconciliation | Your existing `m1-smoke-*` run directories are indexed into SQLite (FR-29) | If `indexed` is 0, check `RFD_OUTPUT_ROOT` |
| 6. **State reconciliation** | Real `sacct` cross-checked against what `RunQueryService` reports | A `MISMATCH` here is a genuine U3 bug — capture the output |

**Check 3 uses M1's job id (7556085) by default.** If Slurm's accounting retention has
expired it will `WARN` rather than fail; pass a fresher one:

```bash
sacct -X --format=JobID,State,ExitCode | tail -5
uv run --package rfd-web python scripts/u3-verify.py --phase read-only --job-id <id>
```

Worth running check 3 against **several** job ids of different outcomes if you have them —
a `COMPLETED`, a `FAILED`, and a `CANCELLED` between them exercise most of the parser. M1's
own history has all three (7441234 failed, 7556080 exited 127, 7556085 completed).

### The one output that needs your judgement

Check 4 prints the generated job script in full. Compare it against `scripts/m1-submit.sh`,
the script that actually completed. The differences should be **exactly** three:

- logs go into the run directory (`{run_dir}/job-%j.out`) instead of the submit directory
- the run directory is interpolated literally instead of taken as `$1`
- no `if [ $# -ne 1 ]` argument check

Anything else is worth a second look before you let it consume a GPU.

---

## Phase 2 — one real submission (consumes a GPU allocation)

```bash
uv run --package rfd-web python scripts/u3-verify.py --phase submit
```

Submits the **same 80-residue de novo smoke design M1 used**, through
`SubmissionService`, and tracks it to a terminal state, printing each status change. Using
M1's design on purpose: it has already completed on this hardware, so a failure here is a
U3 failure and not a new scientific unknown.

This is the check that matters — it is the first time a job script this code *generated*
is run by Slurm, rather than one written by hand.

Watch for:

- `PASS submitted run_id=… job=…` — `sbatch --parsable` parsed correctly
- the status line moving `queued → running → completed`
- `backbone step n/50` appearing, then `validating (no step-level progress available)` —
  that second message is **correct**, not a stall (the runner only reports steps during
  backbone generation)
- `[live frame available]` — FR-17's `current_frame.pdb` being published
- `PASS run completed` with the outputs listed

If it ends `failed`, the log tail is printed with it. Cross-check against
`sacct -j <id> --format=JobID,State,ExitCode,Elapsed`.

The run directory is left in place and is hand-resubmittable with
`cd <run_dir> && sbatch job.sh` (G-2) — which is itself worth doing once, to confirm the
retained script really is standalone.

---

## Phase 3 — cancellation

```bash
uv run --package rfd-web python scripts/u3-verify.py --phase cancel
```

Submits one more job and cancels it immediately; it usually never reaches a GPU. This
exercises the one place where two sources genuinely contradict each other: Slurm reports
`CANCELLED`, while the runner's SIGTERM handler — if it got far enough to run — writes
*"terminated (SIGTERM) — likely walltime exceeded"*. The check asserts the run is reported
as **cancelled**, attributed to this app, with that misleading walltime sentence
suppressed (BR-8).

---

## Exit criteria

U3 is functional on Grex when:

1. Phase 1 reports **0 FAIL**, with real partitions listed in check 2 and a real job state
   parsed in check 3.
2. Phase 2 completes: a generated job script is submitted by `sbatch`, runs, and is
   reported `completed` — with `run.json` finalised, not merely a zero exit code.
3. Phase 3 reports the cancelled run as **cancelled**, not failed, and not with a
   walltime message.
4. `sacct` agrees with what the reconciler reported, in every case.

---

## First real run of phase 1 (2026-08-27, `yak`): 33 PASS / 1 WARN / 0 FAIL

Everything the local suite could not prove, proved:

- **Real `sinfo` parses.** Nine GPU partitions discovered — `gpu`, `agpu`, `lgpu`, `livi`,
  `livi-b`, `mcordgpu`, `mcordgpu-b`, `stamps`, `stamps-b` — with `gpu` correctly marked
  default and `lgpu` correctly annotated image-incompatible. Note this is **more than
  `env.example`'s comment lists**: the non-preemptible `livi`, `mcordgpu` and `stamps` are
  real and carry 21-day walltimes. Exactly why FR-6a forbids a hard-coded list.
- **Real `squeue` → `sacct` fallback parses.** Job 7556085 → `COMPLETED`, `exit_code=0`,
  `signal=0`. An unknown job id → `UNKNOWN(known=False)`, not an exception — BR-4 holds
  against the real client.
- **Real `log_tail` works.** The failed M1 rounds surfaced their actual causes: the
  `ptxas`/XLA error and the `weights_only` `TypeError`. FR-19 is real, not theoretical.
- **Reconciliation over 11 existing run directories**, none skipped, none mis-flagged.

### Three things that run changed

1. **`log_tail` could return a partial first line.** Reading the last 64 KB lands mid-line,
   so the first line of a truncated read is a fragment. The fragment is now dropped
   (`test_a_truncated_tail_drops_the_partial_first_line`).
   **Caveat on the diagnosis**: this was prompted by a traceback tail that began
   `nt call last):`, which was attributed to the byte seek. The fix did not change that
   output on the next run, so that particular fragment is *not* the seek — it appears to
   be in the file on disk. The fix is still correct for the case it names; it was simply
   not the cause of what prompted it. Confirm with
   `wc -c` and `head -c 80` on that run's `job-*.err`.
2. **Recovered runs claimed a Slurm state nobody had asked for.** Runs indexed from
   `run.json` displayed `slurm=UNKNOWN` when no query had been made at all. Absence of
   knowledge is now `None`. (`test_a_run_recovered_from_disk_does_not_claim_a_slurm_state`)
3. **The `sacct` cross-check silently did nothing.** None of the 11 indexed runs carries a
   `slurm_job_id` in `run.json` — M1's runs were submitted by hand with
   `sbatch scripts/m1-submit.sh`, and only S-1 writes the job id into the record. The
   check reported PASS while proving nothing, which is the failure mode this whole
   document exists to avoid. It now emits a loud WARN naming the reason.

### Eight run directories will show as permanently "queued"

M1's hand-made `run.json` files have `backbone_state: pending` and no `slurm_job_id`, so
the reconciler reports them as `queued` — correct by the rules (a record with no job id
and no terminal state *is* pre-submission), but they are dead records that will sit in
U4's run list forever. They are real history, so nothing was deleted. Options when you get
to U4: remove those directories, or teach the run list to show a record with no job id and
no recent activity as *abandoned*. Not a U3 defect either way — every run U3 itself submits
gets its job id recorded before the index is written.

---

## Known gap, found while writing this

Phase 1 check 6 can emit:

> **WARN** known gap: `exit_code` is null in the reconciled view

A run that the app **submitted itself** is reconciled against live Slurm before it goes
terminal, so its exit code is captured. A run **recovered by startup reconciliation** — a
directory copied in, or an index rebuilt after the database was deleted — is marked
terminal from `run.json` alone, and BR-3 then stops `RunQueryService` from ever asking
Slurm about it. `sacct` has the exit code; the view does not.

This is reported rather than silently patched, because the fix is a design choice rather
than an obvious bug: `RunIndexReconciler` could leave such runs non-terminal so the first
read queries Slurm once and then caches, which preserves BR-3's intent (query once, cache
forever) at the cost of one `sacct` call per recovered run. Say the word and it is a small
change to `reconcile.py`.

It does not affect any exit criterion above: every run those criteria cover is one this
app submitted.

---

## What this still does not prove

- **U4's UI.** There is none yet. FR-16/FR-17 are proven at the data level here (progress
  and frame availability), not in a browser.
- **`DesignMode.FIXED`/`PARTIAL`, AnAnaS/`symmetry=auto`, and `--stage backbone` used
  alone.** These are M1's documented scope limits and remain unexercised by any real run;
  U3 does not change that. `--stage validate` *is* reachable now via
  `SubmissionService.resubmit()`, but this script does not drive it — worth a manual
  spot-check on a completed run directory before U4 exposes it.
- **Long-queue behaviour.** If the `gpu` partition is busy, phase 2 will sit in `queued`.
  That is the correct display, but it means the phase can time out (`--max-minutes`,
  default 60) without telling you anything about the code. Requesting a preemptible
  partition (`-b` suffix) is materially faster for a short job.

---

## Phases 2 and 3 passed (2026-08-27, `yak`)

**Phase 2 — real submission: 6 PASS / 0 FAIL.** Job **7556197**, run
`u3smoke-20260827T165320`. The first time Slurm ran a job script this code *generated*
rather than one written by hand.

```
16:53:21  queued    slurm=PENDING
16:53:36  running   slurm=RUNNING  backbone step 0/50 (starting)
16:54:21  running   slurm=RUNNING  backbone step 42/50 [live frame available]
16:54:36  running   slurm=RUNNING  backbone step 49/50 [live frame available]
16:55:06  completed slurm=COMPLETED
```

Queued 15 s, total elapsed ~1m45s. Outputs: backbone PDB, both trajectories (`pX0` and
`Xt-1`), `best.pdb`, `best_design.pdb`, and the result zip. What this establishes beyond
phase 1:

- **S-1 end to end** — validate, derive run id, create directory, write `run.json`,
  generate `job.sh`, `sbatch --parsable`, record the job id, index it.
- **The full status vocabulary against real Slurm** — `PENDING → RUNNING → COMPLETED`,
  each mapped correctly.
- **Live progress (FR-16) and the live frame (FR-17)** — step counts advanced from real
  `progress.json` writes, and `current_frame.pdb` appeared during the run.
- **BR-2 on a real success** — reported `completed` because Slurm said `COMPLETED` *and*
  `run.json` was finalised.
- **BR-3** — re-reading the finished run issued no further Slurm calls.
- **G-2** — the retained `job.sh` is resubmittable by hand.

**Phase 3 — cancellation: 5 PASS / 0 FAIL.** Job 7556200 submitted and cancelled:
reported as **cancelled**, attributed *"cancelled from this app at 16:56"* (BR-8 — the
runner's misleading walltime sentence suppressed), and a second `cancel()` was not an
error (BR-11).

### Exit criteria: all four met

U3's definition of done in `unit-of-work.md` — *"a run can be submitted, tracked to
completion, and cancelled programmatically"* — is satisfied, and satisfied against **real
Slurm** rather than only the fake the definition asks for.

### Still not exercised by a real run

- **BR-5's frozen-progress path.** Validation finished well inside the 120 s staleness
  window, so *"validating (no step-level progress available)"* never appeared. Covered by
  unit tests; not by this run. A longer design (`num_designs > 1`) would surface it.
- **`resubmit()` / `--stage validate`** (FR-11). Reachable now, but not driven here.
- M1's standing scope limits: `DesignMode.FIXED`/`PARTIAL`, and AnAnaS / `symmetry=auto`.

### Worth re-running phase 1 now

The phase-1 WARN — *"the sacct cross-check did not run on any indexed run"* — was true
because no M1 directory carried a `slurm_job_id`. The two runs from phases 2 and 3 do.
Re-running `--phase read-only` will now actually cross-check the reconciler against real
`sacct` for a `COMPLETED` and a `CANCELLED` job, which is the one check phase 1 could not
perform before.
