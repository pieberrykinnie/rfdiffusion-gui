# Application Design Plan

**Stage**: INCEPTION — Application Design
**Depth**: Lean (per approved execution plan; user priority is speed)
**Date**: 2026-07-31

---

## Plan Steps

### Step 1: Context Analysis
- [x] Read `requirements.md` (24 FR, 18 NFR, 20 G-rules, 12 constraints, 8 ADs)
- [x] Read reverse-engineering artifacts (architecture, api-documentation, interaction-diagrams)
- [x] Read `execution-plan.md` (4 units, critical path, overlap strategy)
- [x] Identify key business capabilities from the 7 business transactions
- [x] Determine design scope: component boundaries and interfaces only — detailed business logic
      deferred to Functional Design for U2 and U3

### Step 2: Resolve Open Design Questions
- [ ] User answers the 5 questions below
- [ ] Analyze answers for vagueness, contradiction, or missing detail
- [ ] Raise follow-up questions if any ambiguity remains

### Step 3: Generate Design Artifacts
- [ ] `components.md` — component definitions, responsibilities, interfaces
- [ ] `component-methods.md` — method signatures with input/output types
- [ ] `services.md` — service definitions and orchestration patterns
- [ ] `component-dependency.md` — dependency matrix, communication patterns, data flow
- [ ] `application-design.md` — consolidated view of the above
- [ ] Validate design completeness and consistency against FR/NFR/G traceability

---

## ⚠️ Design Finding That Needs Your Decision

Working through the component boundaries surfaced a problem with the combination of two approved
requirements. Raising it now rather than discovering it during code generation.

**FR-17** requires a **live 3D preview** of the structure as it denoises.
**G-11** requires per-step PDB dumps to go to **`$TMPDIR`**.

`$TMPDIR` is **node-local scratch on the compute node**. The web app runs on a **login node**. The
login node **cannot see the compute node's `$TMPDIR`.** As specified, the web app has no way to read
the frames it is supposed to display.

Both requirements are individually correct — G-11 is the documented Grex idiom and keeps thousands of
small files off the shared filesystem, and FR-17 is notebook parity. They just need a bridge.

**The fix**: the churn stays on node-local scratch, and the runner **publishes only the latest frame**
to the persistent run directory — one small file, overwritten in place, written atomically
(temp file + `os.replace`) so the web app never reads a half-written PDB. Bulk trajectory data still
never touches the shared filesystem until the job stages its real outputs out at the end (G-13).

That leaves one genuine tradeoff for you: **how often to publish**. That is Question 3.

---

## Design Questions

### Question 1 — Repository and packaging layout

The project needs a shared domain library: mode inference must run in **both** the web app (to show
the inferred protocol before submission, FR-4) **and** the runner inside the container (to build the
real Hydra command). It must therefore be importable from two different environments, and it must
stay **pure Python with no ColabDesign or PyTorch dependency** so the web app environment stays light
(NFR-2).

How should the repository be laid out?

A) **`uv` workspace with three packages**: `rfd-core` (pure domain, no heavy deps), `rfd-runner` (the in-job program, depends on core + ColabDesign/RFdiffusion), `rfd-web` (FastAPI app, depends on core only). One lockfile, clean dependency boundaries that are *enforced* rather than merely intended, and the web app provably cannot pull in PyTorch. *(Recommended — the boundary that matters most in this project is exactly the one this layout enforces.)*

B) **Single package with modules** (`rfdgui/core/`, `rfdgui/runner/`, `rfdgui/web/`) and optional dependency groups. Simpler to start and fewer files, but the "web app must not depend on torch" rule becomes a convention rather than something the tooling checks.

C) **Two packages**: `rfd-core` (shared, pure) and `rfd-app` (web + runner together). Middle ground; keeps the critical purity boundary but merges two things with very different dependency weights.

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

### Question 2 — How the runner's code reaches the container

The runner executes **inside** the Apptainer image. Its Python source can get there two ways, and
this materially affects how fast you can iterate.

A) **Bind-mount the source at runtime** (`apptainer exec --bind $PROJECT:/opt/rfdgui …`). The image contains only the *dependency stack* (torch, CUDA, DGL, JAX, RFdiffusion, ColabDesign) and never needs rebuilding when your code changes. Edit a Python file, submit a job, and the change is live. *(Recommended — given ASAP, rebuilding a multi-GB GPU image to fix a typo is the difference between a minute and an hour.)*

B) **Bake the source into the image.** One self-contained, fully reproducible artifact with no external path dependency — genuinely better for archival reproducibility, but every code change means an image rebuild.

C) **Bind-mount during development, bake for a tagged release.** Best of both, at the cost of maintaining two build paths.

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

### Question 3 — Live preview frame publishing frequency

Given the fix described above, how often should the runner copy the current frame from `$TMPDIR` to
the persistent run directory?

Context: the notebook rendered **every** timestep, but it was reading from local tmpfs in the same
process. Here each publish is a small file write to `/home` over NFS from a compute node. A typical
run is 50 timesteps per design.

A) **Every timestep.** Full notebook parity — the preview animates smoothly through denoising. ~50 small writes per design; each frame is a backbone-only PDB, so tens of KB. Modest but non-zero shared-filesystem traffic.

B) **Every N timesteps, configurable, default N=5.** Roughly 10 updates per design — still clearly "live", with ~80% less filesystem traffic. Step *count* still updates every step (that's read from the job log, not from frames), so the progress bar stays smooth even though the structure updates less often. *(Recommended — you keep the sense of live progress and drop most of the I/O.)*

C) **Time-based, e.g. at most one publish per 2 seconds.** Adapts automatically to fast and slow models rather than assuming a step duration.

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

### Question 4 — Progress channel between runner and web app

The runner (compute node) must report progress to the web app (login node). `run.json` holds the
run's durable record; progress is high-frequency and would mean rewriting that file constantly.

A) **Separate `progress.json`**, written atomically, holding current stage, current step, total steps, current design index, and a timestamp. `run.json` is written once at start and once at completion. Clean separation of "durable record" from "volatile status"; a corrupt or stale progress file can never damage the run record. *(Recommended)*

B) **Append-only `events.jsonl`** — every state change appended as a line. Gives a full audit trail of the run and is robust to partial writes, but the web app must scan to the end to get current state.

C) **Single `run.json` rewritten on every update.** Fewest files, but couples volatile and durable data and risks the run record being lost to a partial write mid-job.

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

### Question 5 — Disposition of the original `diffusion.py`

The rollback plan (execution plan §5) depends on `diffusion.py` remaining untouched as a working
Colab fallback. Where should it live once the port exists?

A) **Move to `reference/diffusion.py`** with a short README noting it is the unmodified Colab original, retained as reference and fallback. Keeps the repo root clean while preserving provenance. *(Recommended)*

B) **Leave it at the repository root**, untouched.

C) **Delete it** once the port is verified working.

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

## Anything else?

If any component boundary, interface, or design pattern preference matters to you that I have not
asked about, describe it here.

[Answer]:
