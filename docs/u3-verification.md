# U3 Verification on Grex

**What this is for.** U3's own suite — 225 tests, 96% coverage — passes locally against
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
