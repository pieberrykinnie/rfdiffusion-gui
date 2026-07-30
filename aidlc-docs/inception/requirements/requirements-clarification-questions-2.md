# Requirements Clarification — Round 2

Only one thing genuinely needs your input. The rest of this file records decisions now settled.

---

## Settled: Question 2a → A

Web app runs on a **Grex login node**, binds to `127.0.0.1`, reached via
`ssh -N -L 8080:localhost:8080 grex` with `ControlMaster` configured. SSH login is the authentication.

## Settled: Question 8 → `/home`, downside accepted

You've accepted the ~15–25 GB baseline against the 100 GB quota. Weights path, image path,
`APPTAINER_CACHEDIR`, and output root will still be individually configurable so relocating to
`/project` later is a config change.

---

## Settled: Question 6 → single-job pipeline (your proposal, adopted)

**Yes, that's possible — and it's better than what I proposed. Adopting it.**

You read my proposal correctly: I had the two stages as **two Slurm jobs** chained with
`--dependency=afterok`, which is what forced the normalised `contigs`/`copies` through a file. Your
version — **one program, one job, values stay in variables** — removes that problem rather than
solving it.

I checked the constraint that would have killed it. Grex's **`gpu` partition allows a 7-day maximum
walltime** (21 days on CPU partitions; the *default* is only 3 hours, so `--time` must always be
requested explicitly). Seven days is ample for backbone generation plus ProteinMPNN/AlphaFold even at
`num_designs=32`.

**Why your design is better, beyond simplicity:**

The decisive argument is queue contention. Grex's general GPU capacity is **2 nodes in `gpu`
(4× V100 each) and 2 nodes in `lgpu` (2× L40s each)**. Under `--dependency=afterok`, the validation
job returns to `PENDING` when the backbone job finishes and waits for a **brand-new GPU allocation** —
which on a contended cluster can mean hours of dead time between two stages of the same logical run.
One job means **one queue wait**. On this cluster that is not a minor optimisation.

Secondary wins: the Apptainer container, the CUDA context, and the page-cached model weights all stay
warm across the stage boundary. And `contigs`/`copies` stay ordinary Python variables exactly as
`run_diffusion()` returns them — faithful to the notebook, and less new code to get wrong.

**Tradeoffs, accepted:**

- `--time` must cover both stages. A longer request can reduce backfill priority — but one longer
  wait still beats two waits.
- Re-running validation alone would otherwise mean re-running the backbone. **Mitigation**: the
  runner takes a `--stage {all,backbone,validate}` flag, so validation can be resubmitted against an
  existing run directory. Cheap to add, and it also gives you a retry path if validation fails.
- If walltime is hit mid-validation, backbone outputs are already on disk and intact.

**What this changes about persistence** — `run.json` doesn't disappear, its *role* changes:

| | Before (my proposal) | Now (your proposal) |
|---|---|---|
| `contigs` / `copies` handoff | file, job 1 → job 2 | **in-memory variables** |
| `run.json` purpose | inter-job IPC channel | **job → web app** status, progress, provenance |
| Slurm jobs per run | 2, chained | **1** |

The job → web app channel is still needed regardless: the job and the web app are **separate
processes on different nodes**, so the app cannot see the job's memory. It's also how your Q5 answer
(full notebook-parity live progress) gets satisfied — the runner writes step counts and the app reads
them. And the viewer needs the normalised contigs for `get_Ls()` chain colouring, so recording them
remains useful as *output*, not as handoff.

**Resulting persistence design** (no further input needed unless you disagree):
- **SQLite on `/home`** — run index and status, for the run-list UI.
- **`run.json` per run directory** — parameters, normalised contigs, copies, Slurm job id, stage
  states, output paths. Written by the job, read by the app. Keeps each run directory self-describing.

---

## Question A — Extension opt-ins: which reading of "yes"?

This is the one item I don't want to assume, because it sets process rules for every remaining stage.

You wrote: *"For 9a, 10a, and 11a, yes."* That has two coherent readings:

- **Literal**: "yes" selects the affirmative option in each → **9a=A, 10a=A, 11a=A**
- **Assent to my recommendations**, which were → **9a=B, 10a=B, 11a=B**

I'm not guessing between them, for two reasons: you've knowingly diverged from my recommendations
before (Q3 and Q8), so assent can't be assumed; and **11a has no "yes" option at all** — its choices
are Yes-all / Partial / No.

**What each reading actually commits you to:**

| | Literal (A/A/A) | Recommendations (B/B/B) |
|---|---|---|
| **Security** | Full rule set enforced as a **blocking gate** — I cannot mark any stage complete until every applicable rule is satisfied, with per-rule compliance reported at each checkpoint | Ordinary good practice: argument-list subprocess calls, input validation, localhost binding, no secrets in repo |
| **Resiliency** | AWS Well-Architected Reliability practices applied across 15 areas; most will be marked N/A for a single-user HPC tool, but each must be assessed and justified | Slurm failure handling, honest job-state reporting, and run records surviving app restart — designed in as ordinary requirements |
| **PBT** | Property tests required across the codebase, including thin adapters and glue | Property tests focused on contig parsing, mode inference, and Hydra flag assembly — the logic that actually warrants them |
| **Effect on pace** | Noticeably slower; compliance reporting at every checkpoint | Faster; the substantive protections still get built |

Note that under **either** reading you get the things that prompted the questions: argument-list
subprocess calls (shell injection eliminated), failure/cancellation handling, and property tests on
the contig logic. The difference is whether formal rule sets become **blocking gates** with per-rule
reporting, or whether that engineering is simply done as part of the work.

### Question A
Which did you mean?

A) **Literal — enforce all three** (9a=A, 10a=A, 11a=A). Full security rule set as a blocking gate, resiliency baseline applied, PBT enforced across the codebase.

B) **My recommendations** (9a=B, 10a=B, 11a=B). No formal blocking gates; the substantive protections are built in as ordinary requirements, with property tests targeted at the contig/mode-inference logic. *(Recommended for a single-user tool behind an SSH tunnel with no authentication surface and no sensitive data.)*

C) **Mixed** — enforce security as a blocking gate, but skip the resiliency baseline and keep PBT targeted (9a=A, 10a=B, 11a=B).

X) Other (please describe after [Answer]: tag below — e.g. give a letter per question)

[Answer]:

---

## Anything else?

[Answer]:
