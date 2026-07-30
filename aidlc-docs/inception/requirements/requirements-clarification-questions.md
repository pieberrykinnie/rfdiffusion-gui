# Requirements Clarification Questions

Follow-ups to `requirement-verification-questions.md`. Five items need resolution.

**Recorded from your answers** (no action needed):

| Q | Answer | Decision |
|---|---|---|
| 1 | A | FastAPI + HTMX, server-rendered, no Node toolchain |
| 3 | B | `uv` for the web app; **Apptainer** for the RFdiffusion GPU runtime |
| 4 | C | Full pipeline, **chained automatically** — one click submits backbone + validation |
| 5 | A | Full notebook-parity live progress, per job (step counter + live structure preview) |
| 7 | A | Single user, no auth, bound to localhost behind your SSH tunnel |
| 8 | C | `/home` for now (paths will be configurable so this is reversible) |

---

## Resolved: Question 2 — Yes, the SSH tunnel works with Duo

**Short answer: yes, and Grex's own documentation tells you how.**

An SSH tunnel is not a special kind of connection — it is an ordinary SSH session that happens to
forward a port. You authenticate once, interactively, answer the Duo push, and the tunnel lives as
long as that session does. Duo does not re-challenge mid-session.

**Why your Claude Code attempt failed** is almost certainly this: an automated tool spawns
`ssh -N -L ...` as a subprocess **without a TTY**. Duo needs to prompt you, finds nowhere to print
the prompt and no way to read your answer, and the connection dies. The failure was about the
*absence of an interactive terminal*, not about tunnels being incompatible with MFA.

**The fix — connection multiplexing (ControlMaster).** This is documented on Grex's own MFA page as
the recommended way to cache MFA sessions. Put this in `~/.ssh/config`:

```
Host grex
    HostName grex.hpc.umanitoba.ca
    User <your-ccdb-username>
    ControlMaster auto
    ControlPath ~/.ssh/cm-%r@%h:%p
    ControlPersist 8h
```

Then, **once**, in a normal interactive terminal:

```bash
ssh grex
```

Answer the Duo push. Leave it open, or close it — `ControlPersist 8h` keeps the master socket alive
either way. Every subsequent SSH invocation to `grex`, including a non-interactive tunnel, rides the
existing socket and **never sees a Duo prompt**:

```bash
ssh -N -L 8080:localhost:8080 grex
```

Grex's docs show `ControlPersist 10m`; `8h` is the same mechanism tuned to a working day. This also
speeds up every `scp`/`rsync`/`sbatch`-over-SSH you do.

Two supporting notes from the docs:
- Grex warns that **SSH clients may need updating** to work with Duo at all. Your WSL2 OpenSSH is
  almost certainly fine, but worth knowing if something misbehaves.
- For genuinely unattended automation, Grex's preferred path is depositing a public key through
  **CCDB** (their docs mention this in the context of robot nodes), and they ask that users needing
  unattended access **contact support** rather than work around MFA. If you ever want the web app to
  start on boot without you present, that is the conversation to have — but for "I launch the
  webapp myself", ControlMaster is the right and sufficient answer.

### Question 2a
Given that the tunnel works, confirm the deployment target:

A) **Web app runs on a Grex login node; you reach it via `ssh -N -L 8080:localhost:8080 grex`** with ControlMaster configured as above. The app binds to `127.0.0.1` only. *(Recommended — matches your Q7 answer, and the app is I/O-light: it shells out to `sbatch`/`squeue` and serves small HTML pages.)*

B) As (A), but I want to **check with Grex support first** whether a persistent user web process on a login node is acceptable under their policies before we build around it.

C) Run the web app **inside a long-running CPU-partition Slurm job** instead, and tunnel to the compute node — avoids login-node policy questions entirely at the cost of holding an allocation to serve a UI.

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

## Question 6 — Run-state persistence, elaborated

### What actually has to be remembered

In the notebook, all of this lived in Python globals and evaporated when the kernel restarted. Under
submit-and-track it must outlive the HTTP request, the browser, and the app process itself:

| Category | Fields |
|---|---|
| **Identity** | run id, user-facing name, run directory path, created-at |
| **Submitted parameters** | contigs, pdb, iterations, symmetry, order, hotspot, chains, add_potential, num_designs, use_beta_model, partial_T, plus the ProteinMPNN/AlphaFold settings (num_seqs, sampling temp, rm_aa, soluble, initial_guess, recycles, multimer) |
| **Derived values** | inferred mode (`free`/`fixed`/`partial`), **normalised contigs**, **copies** |
| **Slurm linkage** | backbone job id, validation job id, partition, account, submit/start/end times |
| **Status** | per-stage state (PENDING/RUNNING/COMPLETED/FAILED/CANCELLED), current denoising step, exit codes, error text |
| **Outputs** | paths to final PDBs, trajectories, `best.pdb`, the result zip |

### The thing that makes this architecturally interesting

Your Q4 answer — **full pipeline, one click** — creates a real constraint that changes my
recommendation.

The validation stage needs `--contig` and `--copies`. Those are **not** the values you typed into the
form: they are the *normalised* contigs, produced inside `run_diffusion()` by `parse_pdb()` +
`fix_contigs()`/`fix_partial_contigs()`, after the template has been fetched and symmetry resolved.
In the notebook this was invisible — `run_diffusion()` returned them into globals and the next cell
just used them.

If we submit both jobs up front with `--dependency=afterok:<backbone_job_id>` — which is what makes
"one click" work — then **at submission time those values do not exist yet.** They only come into
being partway through job 1.

So job 1 must write them somewhere job 2 can read them. That means a **per-run JSON file in the run
directory is not redundant bookkeeping — it is the inter-job communication channel** that makes the
chained pipeline possible at all.

That reframes the options:

### Question 6a
Which persistence approach?

A) **SQLite (on `/home`) for the run index and status, plus a per-run `run.json` in each run directory.** The database answers "show me my runs and their status" for the UI; the JSON is written by the backbone job and read by the validation job to hand over normalised contigs and copies, and it leaves every run directory fully self-describing if you copy it elsewhere. Each half has a distinct job rather than duplicating the other. *(Recommended — the per-run JSON is required by your one-click choice regardless, so the only real question is whether to add the SQLite index on top.)*

B) **Per-run JSON only, no database.** The filesystem is the state; the run list is built by scanning run directories. One less moving part and nothing to corrupt or migrate, at the cost of a directory scan on every page load and clumsier sorting/filtering as runs accumulate. Perfectly viable for a single user with tens of runs.

C) **SQLite only**, with the job-to-job handoff done some other way (for example, the validation stage re-derives the normalised contigs itself by re-reading `input.pdb`). Avoids the JSON file but duplicates normalisation logic in two places — I'd advise against it, and I'm listing it only so the tradeoff is explicit.

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

## Question 9a — Security extension: confirming your answer

You wrote: *"Argument list is ideal, this shouldn't break."*

Agreed, and that's happening either way — every external invocation (`sbatch`, `squeue`, `sacct`,
`apptainer exec`, `run_inference.py`) will be built as an **argument list** passed to `subprocess`
with no shell, so quoting and injection stop being a category of problem. The notebook's
quote-stripping hack (which also silently corrupted legitimate input) goes away entirely.

Your comment answers the *technique*, but Question 9 was asking something narrower: whether the
**security extension's full rule set becomes a blocking gate** on every stage from here on — meaning
I cannot present a stage as complete until every applicable rule is satisfied, and I report per-rule
compliance at each checkpoint.

### Question 9a
Should the security extension rules be enforced as blocking constraints?

A) **Yes** — enforce the full SECURITY rule set as blocking constraints at every stage.

B) **No** — skip the formal rule set. Apply ordinary good practice instead: argument-list subprocess calls, input validation on the design parameters, localhost-only binding, and no secrets in the repo. *(Reasonable for a single-user tool behind an SSH tunnel with no authentication surface and no sensitive data — and note that the specific issue that prompted the question, shell injection, is already resolved by the argument-list decision.)*

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

## Question 10a — Resiliency extension (not yet answered)

Should the resiliency baseline be applied? Full framing was in Question 10 of the original file; the
short version is that it applies AWS Well-Architected (Reliability Pillar) design-time practices.

A) **Yes** — apply the resiliency baseline as directional design-time guidance.

B) **No** — skip it. *(This extension is framed around AWS cloud workloads; for a single-user app on a university HPC cluster most of it would be marked N/A. The parts that genuinely matter here — handling failed and cancelled Slurm jobs, surfacing job state honestly, not losing a run record if the app restarts mid-job — are already core requirements and will be designed in regardless.)*

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

## Question 11a — Property-based testing extension (not yet answered)

A) **Yes** — enforce all PBT rules as blocking constraints across the codebase.

B) **Partial** — apply PBT only to pure functions and round-trips. In practice this means **contig parsing and design-mode inference** (`free`/`fixed`/`partial`), plus the Hydra flag assembly derived from it. That logic is the highest-value thing carried over from the notebook, it has zero tests today, and it is exactly the shape property tests are good at — arbitrary contig strings should always yield a valid mode, and normalisation should be idempotent. *(Recommended)*

C) **No** — skip PBT; rely on conventional example-based unit tests only.

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

## Note on Question 8 (no answer needed — flagging a consequence)

You chose `/home` for now, which is fine and I'll build to it. Recording the arithmetic so it isn't
a surprise later, given the **100 GB `/home` quota**:

| Item | Approx. size |
|---|---|
| RFdiffusion checkpoints (3) | ~4 GB |
| AlphaFold parameters | ~4 GB |
| Apptainer image (RFdiffusion + JAX/CUDA) | ~5–10 GB |
| Apptainer build/pull cache (`APPTAINER_CACHEDIR`) | can transiently equal the image size again |
| Per-run outputs + trajectories | tens to hundreds of MB per design |

So roughly **15–25 GB** before you generate anything, with trajectories accumulating on top. That
fits, but it is a real fraction of your quota, and the Apptainer cache in particular has a habit of
quietly filling `/home` unless `APPTAINER_CACHEDIR` is pointed somewhere deliberate.

**What I'll do about it without asking**: make weights path, image path, cache dir, and output root
individually configurable via environment variables with `/home` defaults. Moving any of them to
`/project` later becomes a one-line config change rather than a code change.

---

## Anything else?

[Answer]:
