# Requirements Verification Questions

Please answer each question by filling in the letter choice after the `[Answer]:` tag.
If none of the options match your needs, choose the last option (**Other**) and describe your preference.

**Already decided** (from our conversation — no need to re-answer):
- Architecture: **submit-and-track**. You launch the web app independently; it submits Slurm batch jobs, tracks them, and survives both the browser closing and the 6-hour OpenOnDemand cap.

**Context that shapes these questions** (from reverse engineering):
- The web app is a *Slurm client*, not a compute process — it needs **no GPU and no PyTorch**. This naturally splits the project into two environments: a **light web app env** and a **heavy RFdiffusion runtime env**. Several questions below turn on that split.
- The riskiest part of the port is the GPU dependency stack (torch 2.4 / CUDA 12.4 / DGL / e3nn / JAX), which the notebook never pinned at all.

---

## Question 1
Which web framework and UI approach should the application use?

A) **FastAPI + server-rendered HTML with HTMX** — a small dependency set, no Node/npm build step, no JavaScript bundler. Pages are Jinja templates; polling for job status is a few HTMX attributes. 3Dmol.js is loaded as a single vendored `<script>` for structure viewing. Best fit for "lightweight" and for an air-gapped-ish HPC node. *(Recommended)*

B) **FastAPI + a React/Vite single-page app** — richer interactivity, but adds a Node toolchain, a build step, and a bundle to ship. Heavier to install and maintain on a cluster.

C) **Gradio** — fastest to write and it already handles file upload and job queuing, but you inherit its opinionated UI, a fairly large dependency tree, and awkward control over Slurm-backed long-running jobs.

D) **Streamlit** — quick to build, but its rerun-on-interaction execution model fits poorly with submit-and-track and long-lived external jobs.

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

## Question 2
Where will the web app process run, and how will you reach it in a browser?

A) **On a Grex login node, reached over an SSH tunnel** (`ssh -L 8080:localhost:8080`). Simplest for submit-and-track: the app is a tiny always-available process that shells out to `sbatch`/`squeue`. Note Grex discourages heavy compute on login nodes — this app is I/O-light, so it should be acceptable, but it is worth confirming with support. *(Recommended)*

B) **As an OpenOnDemand interactive app** — nicest UX and no manual tunnel, but OOD sessions are capped at 6 hours, so the *tracking UI* would die every 6 hours even though the submitted jobs survive. Acceptable if you treat the UI as disposable.

C) **On your own workstation, talking to Grex remotely over SSH** — keeps all load off the cluster, but requires the app to drive Slurm over SSH and to read results across the network, which complicates file handling considerably.

D) **Inside a long-running Slurm batch job on a CPU partition** — no login-node policy concerns and can run for days, but you must discover the assigned node and tunnel to it, and it consumes an allocation just to serve a UI.

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

## Question 3
How should the **RFdiffusion runtime environment** (the GPU-side dependencies) be provisioned?

This is the highest-risk decision in the project. Note that `uv` will manage the project either way — the question is what `uv` is responsible for installing.

A) **`uv` for both environments** — the web app *and* the RFdiffusion runtime are `uv` projects with locked dependencies. Uses `[[tool.uv.index]]` for the DGL CUDA wheel index and a path dependency for the vendored SE3Transformer. Maximum fidelity to your "port it to uv" request and fully reproducible, but this is the stack that historically fights back (DGL/torch/CUDA ABI coupling), so expect real iteration to land the lockfile. *(Recommended, with the caveat noted)*

B) **`uv` for the web app; Apptainer container for RFdiffusion** — the fragile GPU stack is frozen inside an image (`--nv` for GPU passthrough, which Grex documents), while `uv` cleanly manages everything you actually maintain. Most robust and most reproducible; the cost is building/obtaining the image and a slightly less direct answer to "port it to uv".

C) **`uv` for the web app; CCEnv modules + a `uv` venv for RFdiffusion** — follows Grex's documented "virtualenv + pip with Alliance wheels" guidance most closely and reuses the cluster's tested `cuda`/`cudnn` modules, but ties your lockfile to Grex's module versions and reduces portability off this cluster.

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

## Question 4
Which parts of the pipeline should the **first version** cover?

A) **Backbone generation only** (BT-2, BT-3, BT-4, BT-7) — submit an RFdiffusion run, track it, view the resulting backbone and trajectory, download results. Leaves ProteinMPNN/AlphaFold to a later iteration. Smallest coherent deliverable; also avoids the ~4 GB AlphaFold parameter staging entirely for now.

B) **The full pipeline** (BT-2 through BT-7) — backbone generation *and* the ProteinMPNN + AlphaFold designability validation, as separate trackable jobs, plus the best-design comparison view. Matches what the notebook does today end to end. *(Recommended if you want feature parity)*

C) **Full pipeline, chained automatically** — as (B), but validation is submitted automatically as a Slurm dependency (`--dependency=afterok:`) when backbone generation succeeds, so one form submission produces the whole result.

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

## Question 5
How much live progress detail do you want while a job runs?

The notebook streams each denoising timestep by having RFdiffusion dump per-step PDBs to `/dev/shm` and polling them. That trick can be carried over (writing to a per-run scratch directory instead, to avoid the multi-user collision noted as TD-13), but it adds meaningful complexity.

A) **Slurm state + step progress + live structure preview** — full parity with the notebook: a progress bar driven by per-step dumps and a 3D preview of the structure as it denoises. Highest fidelity, most moving parts.

B) **Slurm state + step progress, no live structure** — poll the per-step dumps only to count completed timesteps and drive a progress bar. Gives a real sense of progress at much lower complexity. *(Recommended)*

C) **Slurm state only** — show PENDING / RUNNING / COMPLETED / FAILED from `squeue`/`sacct`, plus the job log tail. Simplest and fully sufficient for submit-and-track, but during a long RUNNING phase you see no forward motion.

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

## Question 6
How should run state be persisted? (Required regardless — the notebook's cross-cell globals cannot survive a submit-and-track model.)

A) **SQLite via the Python standard library** — one file, no server, transactional, easy to query for the run list. Well-suited to a single-user app. Note that SQLite on Lustre (`/project`) can behave badly with locking, so the database should live on `/home`. *(Recommended)*

B) **One JSON metadata file per run directory** — no database at all; the filesystem *is* the state, and a run directory remains fully self-describing if copied elsewhere. Simplest to inspect and debug by hand; needs care around concurrent writes.

C) **SQLite plus per-run JSON** — database for the run index and status, JSON in each run directory for provenance. Redundant but very robust to either half being lost.

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

## Question 7
Who can reach the application, and what authentication is needed?

A) **Single user, no authentication** — the app binds to `127.0.0.1` and is reachable only through your own SSH tunnel, so the SSH login *is* the authentication. Simplest and genuinely secure for personal use. *(Recommended given "I can launch the webapp")*

B) **Single user, but with a shared secret / token** — as (A) plus a token in the URL or a login form, as defence in depth against another user on the same login node reaching your port.

C) **Multiple users, each with their own runs and their own Slurm identity** — substantially larger scope: authentication, per-user isolation, and the question of which account submits jobs.

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

## Question 8
Where should model weights and run outputs live on Grex?

Recall the constraint: `/home` has a **100 GB per-user quota**, `/project` has **5 TB per group** on Lustre. Weights are roughly **8 GB** (3 RFdiffusion checkpoints plus ~4 GB of AlphaFold parameters).

A) **Both weights and outputs on `/project`**, with the app and its database on `/home` — keeps the quota-heavy data on the large filesystem and the latency-sensitive database off Lustre. *(Recommended)*

B) **Weights on `/project`, outputs on `/home`** — outputs stay in your personal space and are easier to browse, but a batch of designs plus trajectories can grow quickly against the 100 GB quota.

C) **Everything on `/home`** — simplest paths, but ~8 GB of weights immediately consumes a noticeable share of your quota before you generate anything.

D) **Make both locations configurable, ship the (A) layout as the default** — slightly more code, but avoids hard-coding site-specific paths and makes the app usable by a colleague or on another cluster.

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

## Question 9: Security Extensions
Should security extension rules be enforced for this project?

A) Yes — enforce all SECURITY rules as blocking constraints (recommended for production-grade applications)

B) No — skip all SECURITY rules (suitable for PoCs, prototypes, and experimental projects)

X) Other (please describe after [Answer]: tag below)

[Answer]:

> Context for your decision: reverse engineering flagged **TD-7, shell injection** — every user parameter in the notebook is interpolated into a shell command string, defended only by stripping quote characters. That is tolerable in a single-tenant Colab VM where you can only attack yourself; it is a different proposition when a web form reaches a shared university cluster. Some hardening here is worth doing regardless of how you answer, but this question decides whether the full rule set is enforced as a blocking gate.

---

## Question 10: Resiliency Extensions
Should the resiliency baseline be applied to this project?

**What this extension is.** Enabling it applies a set of **directional, design-time best practices** for building resilient systems, derived from the **AWS Well-Architected Framework (Reliability Pillar)** and resilience-review guidance. It steers requirements, design, and code toward fault tolerance, high availability, observability, and recoverability — covering 15 practice areas across business goals, change management, observability, high availability, disaster recovery, and continuous improvement.

**What this extension is NOT.** Enabling it does **not** make your workload production-ready, nor does it certify or guarantee any availability, RTO, or RPO target. It is a **starting point** that scaffolds good resiliency decisions early — it is not a substitute for a formal **AWS Well-Architected Review** of the built system.

Treat the output as a well-grounded **first draft of your resiliency posture** to build on and validate — not a finished, production-certified result.

A) Yes — apply the resiliency baseline as directional best practices and design-time guidance (recommended for business-critical workloads, as an informed starting point that you can validate and harden before go-live)

B) No — skip the resiliency baseline (suitable for PoCs, prototypes, and experimental projects where rapid iteration matters more than reliability)

X) Other (please describe after [Answer]: tag below)

[Answer]:

> Context for your decision: this extension is framed around AWS cloud workloads, and this project is a single-user application on a university HPC cluster — so much of it will likely be marked N/A. The parts that *would* genuinely apply are job-failure handling, retry behaviour, and observability of Slurm state.

---

## Question 11: Property-Based Testing Extension
Should property-based testing (PBT) rules be enforced for this project?

A) Yes — enforce all PBT rules as blocking constraints (recommended for projects with business logic, data transformations, serialization, or stateful components)

B) Partial — enforce PBT rules only for pure functions and serialization round-trips (suitable for projects with limited algorithmic complexity)

C) No — skip all PBT rules (suitable for simple CRUD applications, UI-only projects, or thin integration layers with no significant business logic)

X) Other (please describe after [Answer]: tag below)

[Answer]:

> Context for your decision: the port contains one genuinely property-shaped piece of logic — **contig parsing and design-mode inference** (`free` / `fixed` / `partial`), plus the Hydra flag assembly built from it. That code has zero tests today and is the single highest-value thing to characterise before rewriting it. Option (B) would target exactly that and little else.

---

## Anything else?

If there are constraints, preferences, or goals not covered above — a deadline, a colleague who also needs to use this, a specific Slurm account or partition you must use, or features the notebook lacks that you want in the port — please describe them here.

[Answer]:
