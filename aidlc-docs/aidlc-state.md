# AI-DLC State Tracking

## Project Information
- **Project Name**: rfdiffusion-gui
- **Project Type**: Brownfield
- **Start Date**: 2026-07-30T22:57:31Z
- **Current Phase**: **CONSTRUCTION** (INCEPTION complete and fully approved)
- **Current Stage**: **U3 Slurm and Persistence — Code Generation APPROVED 2026-08-27
  ("Approve and Park"). WORKFLOW PARKED at the U3/U4 boundary by user request.** U3 is
  complete and verified on real Grex hardware. **U4 Web Application (Code Generation only)
  is the next stage and has NOT been started.** To resume: begin U4 Code Generation Part 1
  (planning), per the execution plan. U3's Code Generation was verified before approval: U3's definition of done from
  unit-of-work.md — *"a run can be submitted, tracked to completion, and cancelled
  programmatically"* — is met against **real Slurm**, not merely against the fake the
  definition asks for: `scripts/u3-verify.py` phase 1 (34 PASS / 1 WARN / 0 FAIL,
  real `sinfo`/`squeue`/`sacct`), phase 2 (**job 7556197 submitted from a GENERATED job
  script, ran, and completed** — queued 15 s, elapsed ~1m45s, full output set), and
  phase 3 (job 7556200 cancelled and correctly reported as cancelled, attributed to the
  app, with the runner's misleading walltime sentence suppressed per BR-8). See
  `docs/u3-verification.md`. Functional Design approved, the 20-step code-generation plan approved, and all
  43 plan checkboxes ticked. `packages/rfd-web` now exists: **225 tests, 96% coverage, on real
  Python 3.9.25**, with the pre-existing 231 (`rfd-core` 157 + `rfd-runner` 74) re-run and
  unchanged — **456 total**. Summary at
  `aidlc-docs/construction/u3-slurm-persistence/code/u3-code-summary.md`. U1 (PASS 13/FAIL 0, 2026-08-07),
  U2a and U2b are complete and approved, and **Milestone M1 PASSED 2026-08-27** on real Grex
  hardware (job 7556085), which is what unblocked U3.

## ✅ U1 Verification — First Real Execution (2026-08-06, node `n339`)

**The decisive result: check 3 PASSED.** The sokrypton fork is on `PYTHONPATH` at the pinned sha
`597d37f2a686e23941440fddf6daa4cb778e7bc7` with both `dump_pdb` keys present. **FR-16 (step
progress) and FR-17 (live 3D preview) are achievable.** This was the single finding that could have
invalidated the whole approach, and it is now retired.

**Also confirmed**: `jaxlib 0.4.25+cuda11.cudnn86` is intact in the shipped image — the §8.1e
silent-clobbering fix held. `torch 1.12.1+cu116`, `dgl 1.0.2+cu116`, `e3nn 0.3.3` all import.
Checkpoints, the schedules symlink, and AlphaFold params are all present.

**Verification does not require a GPU end to end.** Checks 3, 5, 6, 7 and the jaxlib half of 4 are
filesystem and import tests. With the `gpu` partition quoting a **five-day** queue, these were run
on a `skylake` CPU node instead. Only checks 1, 2 and the JAX device test are GPU-gated — and that
is now the entire remaining U1 surface.

**Queue lesson for U3** (`--partition=` UI): `gpu` is the *smallest* compatible pool. Requesting
multiple partitions (`--partition=agpu,stamps-b,mcordgpu-b,gpu,livi-b`), using the preemptible `-b`
pool, and keeping `--time` short for backfill are all materially cheaper than waiting on `gpu`.
Preemptible partitions carry a 1-hour minimum runtime guarantee, so short jobs cannot be preempted.

**Two defects found in `verify-image.sh` itself** (not in the image) — both fixed 2026-08-06:
1. **Check 4 could not fail.** Its GPU assertion grepped all output for `cuda|gpu` and matched the
   jaxlib version string `0.4.25+cuda11.cudnn86`, reporting a GPU pass against `[CpuDevice(id=0)]`.
   It passed whenever the pin held — exactly when it needed to fail. Scoped to the `^devices` line.
   **The JAX/CUDA-11 risk from §3 therefore remains genuinely untested.**
2. **Check 6 omitted `mkdir -p /scratch/schedules`**, so every fork import raised `FileExistsError`
   — see the U2b constraint below, which this confirms live.

**Open item**: `ananas` unavailable (upstream 404). WARN, not a gate — costs `symmetry="auto"` only.
Carries into **U3** (symmetry UI must degrade) and **U2b** (its ananas-unavailable fail-fast rule is
now a live path).

## ⚠️ U1 Verification — Second Real Execution (2026-08-06, same node) — Defect 3, in the image

Both `verify-image.sh` fixes confirmed working: check 4 now correctly FAILS on this CPU node
(previously a false PASS), and Defect 2's predicted `FileExistsError` did not recur — import
proceeded past the schedules symlink to a **different, later, real** failure:

```
ModuleNotFoundError: No module named 'icecream'
```

**This is the first defect found in the image itself**, not the verification script — and it was
only visible because the Defect 2b stderr fix had just landed.

**Root cause, run to ground by downloading the fork source at the pinned commit and reading every
import** rather than patching one `ModuleNotFoundError` at a time across repeated cluster round
trips: `reference/diffusion.py`'s commented-out Colab cell 2 installed six packages
(`jedi omegaconf hydra-core icecream pyrsistent pynvml decorator`) that `rfdiffusion.def` never
carried over, because it inherits the **RosettaCommons** base image's install list — built for a
codebase that imports none of them.

**Two are genuinely required**: `icecream` (entry point + five other fork modules import it
unconditionally) and `pyrsistent` (`inference/symmetry.py` — this project's symmetry feature).
**Three are not**: `jedi` (zero references anywhere in the fork), `pynvml`/`decorator` (real deps of
SE3Transformer's *own* `requirements.txt`, but that file is decorative — `setup.py` declares no
`install_requires`, and both are imported only by `se3_transformer.runtime`, which RFdiffusion never
touches — it imports only `se3_transformer.model`).

**Fixed in `containers/rfdiffusion.def`**: `uv pip install icecream pyrsistent` added after the
`dump_pdb` assertion.

## ✅ U1 Verification — Third Real Execution (2026-08-06, same node) — CPU surface fully clean

Rebuilt and re-verified. **PASS 9 / FAIL 3.** Check 6 now passes in full — Defect 3 confirmed fixed,
no further hidden import gap surfaced. The 3 FAILs are exactly the predicted set: checks 1, 2, and
the JAX device test, all genuinely GPU-gated.

**Three rounds, three real defects found and fixed** (two in `verify-image.sh`, one in the image
itself), each confirmed by the *next* real execution rather than assumed fixed on inspection alone.
**U1's entire CPU-verifiable surface is now clean.** Only a short GPU allocation for checks 1, 2, and
the JAX device test remains — see Stage Progress below for the exact command. The §3 JAX/CUDA-11
risk is the one open question a full U1 pass still has to answer.

**Confirmed no further script change needed**: both packages sit on one eager top-level import chain
(`run_inference.py` → `inference.utils` → `inference.model_runners` → `inference.symmetry` →
`pyrsistent`), so the existing check 6 exercises both without modification.

## ⚠️ U1 Verification — First GPU Execution (2026-08-06, same node) — §3 risk materialized

The one thing three CPU rounds structurally could not test: the JAX device check, on a real GPU. It
**failed**, and correctly so — this is the §3 risk finally happening, not a fourth script or image
defect:

```
CUDA backend failed to initialize: Found CUDA version 11060, but JAX was built against
version 11080, which is newer.
```

**Inverted from how §3 originally framed it.** The risk was written as "ColabDesign may need newer
JAX than CUDA 11.6 permits." What actually happened: **JAX itself needs newer CUDA than this base
has.** `jaxlib 0.4.25` — confirmed intact through every CPU round — was built against CUDA 11.8; the
base runs CUDA 11.6.2. CUDA's compatibility model runs one direction only (newer runtime tolerates
older-build code, never the reverse), so this was never going to work once actually run on a GPU.

**Root-caused from JAX's own `CHANGELOG.md`**: `jax 0.4.8` (2023-03-29) is the exact release that
"dropped CUDA 11.4 support... JAX GPU wheels only support CUDA 11.8 and CUDA 12." Every cuda11
jaxlib from 0.4.8 on requires CUDA ≥ 11.8. `jaxlib 0.4.7` is the newest build that predates this —
confirmed against the full wheel index, and it is the *ceiling*, not an arbitrary older choice: there
is no cuda11 jaxlib release between 0.4.7 and 0.4.8 to try instead.

**A second, cascading problem found before touching the cluster again**: `chex==0.1.86` requires
`jax>=0.4.16`, incompatible with `jax==0.4.7`. Traced chex's PyPI history to find the newest release
that still accepts `jax>=0.4.6`: **`chex==0.1.82`**.

## ⚠️ U1 — First Build Attempt With the Re-Pin Fails: `optax` Check Was Incomplete

`optax==0.2.2` was left unchanged based on checking only its `jax` bound (`jax>=0.1.55`, satisfied).
Its **full** `requires_dist` also declares `chex>=0.1.86` unconditionally — a direct conflict with
`chex==0.1.82` above. The real `uv pip install` caught it immediately, before staging:

```
x No solution found when resolving dependencies:
  `-> Because optax==0.2.2 depends on chex>=0.1.86 and you require chex==0.1.82, we can
      conclude that your requirements and optax==0.2.2 are incompatible.
```

This is `containers/rfdiffusion.def`'s "one resolution pass" design working as intended — a loud
failure at build time, not a silently broken image, and cheaper than the GPU-time failure it's
already prevented once (§8.1g). Re-checked optax's PyPI history for a release contemporary with
`chex 0.1.82`: **`optax==0.1.7`** (2023-07-26) requires only `chex>=0.1.5` and `jax>=0.1.55`. Also
checked `dm-haiku==0.0.12`'s *unconditional* `flax>=0.7.1` dependency this time (separate from its
optional `[jax]` extra, not checked in the first pass) — `flax 0.7.1` requires only `jax>=0.4.2`, so
`dm-haiku==0.0.12` genuinely needs no change.

**Fixed in `containers/rfdiffusion.def`**: `jax==0.4.7`, `jaxlib==0.4.7+cuda11.cudnn86` (cuDNN 8.6
kept — that's a separate, already-working fix, untouched), `chex==0.1.82`, `optax==0.1.7`. **Not yet
rebuilt or re-verified.**

**If the build still fails at resolution**: re-derive from `requires_dist` again — check every
explicitly pinned package's full dependency list, not just the constraint under active suspicion.
**If it builds but the JAX device check still fails on GPU**: the CUDA-11 ceiling is now firmly
established — no more cuda11 options exist to try. Next step is Tier 2 of §3: two images,
`colabdesign.sif` on a CUDA 12 base.

## U2b Runner — Verified Facts (from source research, not assumption)
1. **Hydra `config_path` resolves relative to the script file**, not cwd — `InferenceExecutor` needs
   no `cd` into `/opt/RFdiffusion`.
2. ⚠️ **`ValidationExecutor` MUST launch `designability_test.py` with `cwd=/opt/weights/alphafold`.**
   No override flag exists; ColabDesign's vendored AlphaFold loader defaults to `data_dir="."` and
   falls back through `{cwd}/params_{model}.npz` — confirmed against the official DeepMind download
   script's flat-extraction convention, which matches `stage-weights.sh`'s existing layout.
3. **G-13 ("stage out before job end") is satisfied by construction**: the notebook already separated
   `output_prefix` (final, persistent) from `dump_pdb_path` (ephemeral). Pointing the former at the
   bind-mounted run directory and the latter at `/scratch` means nothing needs copying at job end
   except the result zip.
4. `designability_test.py` has a real `__main__` guard — invokable as
   `python -m colabdesign.rf.designability_test`, no symlink hack needed.

## U2b Decision Made Without Asking
- **`RFD_STEP_TIMEOUT_SECONDS` default 1800** (30 min) — per-step stall detection. Not put to the
  user: Slurm's own `--time` is already a hard backstop, so the downside of any value here is bounded
  and reversible via one env var. Exists to surface *which step* stalled quickly, rather than the
  user waiting out the full walltime for an undifferentiated `TIMEOUT`.

## U2a Code Generation Result
- **157 tests, 100% statement coverage**, all verified against a locally-provisioned Python 3.9.25
  (`uv python install 3.9`) — the exact interpreter the U1 container uses, not a stand-in.
- **Dependency tree confirmed pydantic-only** via `uv pip tree` — no accidental torch/JAX/ColabDesign
  import anywhere in `rfd-core` (NFR-2 proven, not assumed).
- **Incident found and fixed**: `ruff check --fix` silently rewrote `Optional[X]` to `X | None`
  throughout the source — invalid at runtime on Python 3.9 (pydantic `eval()`s string annotations;
  the `|` type operator is a 3.10+ runtime feature). Caught immediately by re-running the 3.9 suite
  after the lint pass, reverted, and **`UP045`/`UP007` permanently suppressed** in
  `packages/rfd-core/pyproject.toml` with an explanatory comment — `target-version` alone does NOT
  gate these rules. Full detail in `u2a-code-summary.md`.
- Package layout: `pyproject.toml` (root, virtual workspace) + `packages/rfd-core/` with
  `requires-python=">=3.9,<3.10"` pinned tight — confirmed to correctly *refuse* Python 3.13.

## U2a Functional Design Decisions
- **Q1 = no numeric ceiling** (positivity floor retained — see business-rules.md §0)
- **Q2 = symmetry order capped at 12** (stricter than the real 26/52 chain-letter limit, deliberately)
- **Q3 = hotspot/chain cross-validation deferred** (needs a parsed PDB; out of scope for this pure unit regardless)
- **`get_Ls` added to `rfd-core` scope** (pure, needed by U4 for FR-22 chain colouring)
- **Notebook bug found and fixed**: `"0"`-length contig segments are silently dropped by ColabDesign's
  `fix_contig`; `rfd-core` rejects them instead (documented NFR-9 deviation)
- Artifacts: `business-logic-model.md`, `business-rules.md`, `domain-entities.md` in
  `aidlc-docs/construction/u2a-core-domain/functional-design/`

## ⚠️ Upstream Bit-Rot: `files.ipd.uw.edu/krypton/` is GONE (404, verified 2026-08-01)
Two assets the original notebook downloads no longer exist. `/pub/RFdiffusion/` still works.

| Asset | Impact | Resolution |
|---|---|---|
| `schedules.zip` | none | Diffuser computes and caches schedules on demand into `/scratch/schedules` |
| `ananas` | **`symmetry="auto"` unavailable** | Staging is best-effort and non-fatal; `RFD_ANANAS_URL` or manual placement re-enables it |

**Requirement impact — `symmetry="auto"` is conditionally available:**
- **U4**: the symmetry selector must detect whether `ananas` is present and, if not, disable the
  `auto` option with an explanatory note. `none` / `cyclic` / `dihedral` are unaffected.
- **U2b**: `SymmetryDetector` (C-12) must fail with a clear, actionable message when `auto` is
  requested without the binary — never a bare exception or a silent fallback to no symmetry.
- **Note**: the original notebook is now broken in these same two respects, so the Colab fallback
  has partially bit-rotted too.

## ⚠️ Constraint Carried Into U2b (from U1 build findings)
- ⚠️ **Runner must `mkdir -p /scratch/schedules` before invoking `run_inference.py`.**
  `/opt/RFdiffusion/schedules` is a symlink to `/scratch/schedules` (bound from `$TMPDIR`). The fork
  does `os.mkdir()` on that path **at import**, which raises `FileExistsError` on a dangling symlink,
  and it *writes* there for uncached `T` values, which a read-only SIF cannot satisfy.
  **There is NO seed to copy** — `/opt/schedules-seed` does not exist. Pre-seeding was dropped when
  `files.ipd.uw.edu/krypton/schedules.zip` went 404; it was only ever an optimisation, and the
  `Diffuser` computes any missing schedule on CPU. *(Corrected 2026-08-06 — this entry previously
  described a seed that the shipped image does not contain.)*
  **CONFIRMED LIVE 2026-08-06**: `verify-image.sh` omitted this `mkdir` and failed with exactly this
  error. The precondition is load-bearing, not defensive.
- **The container's Python is `/app/RFdiffusion/.venv/bin/python`** (a uv venv), not `python3.9` on
  PATH in the usual sense. Anything invoking the interpreter explicitly must use that path.

## ⚠️ Constraints Carried Into U2a
- **`rfd-core` MUST target Python 3.9** (container base image). No `StrEnum` → `class X(str, Enum)`;
  no runtime PEP 604 unions → `Optional[...]` + `from __future__ import annotations`; no `match`.
- **`rfd-web` uses a uv-managed Python ≥3.11** — the login node's system `python3` is **3.6.8**.
- Partition selector must offer the CUDA-11.6-compatible set (`gpu`, `agpu`, `stamps-b`, `livi-b`,
  `mcordgpu-b`) and mark **`lgpu` incompatible** with the Phase 1 image (U3).
- Walltime limits are **per-partition** (`lgpu` = 3 d, others 7–21 d) — read from `sinfo`, never a
  constant (U3, FR-6a).

## U1 Infrastructure Decisions (Q1=D, Q2=A, Q3=A, Q4=A)
- **Phase 1**: one image `FROM rosettacommons/rfdiffusion` (CUDA 11.6 / torch 1.12.1+cu116 /
  dgl 1.0.2+cu116 / e3nn 0.3.3 / Python 3.9), targeting **`gpu` (V100) only**, with the
  **sokrypton fork** cloned in for `dump_pdb` and ColabDesign/JAX overlaid. Built on Grex `--fakeroot`.
- **Phase 2 deferred**: CUDA 12.x variant for `lgpu`. `RFD_IMAGE` is configurable, so swapping is a
  config change, not a code change.
- ⚠️ **RISK + PRE-PLANNED FALLBACK**: ColabDesign may need newer JAX than CUDA 11.6 allows (JAX cuda11
  wheels are off-PyPI, on the `jax-releases` index, and old). If verification step 6 fails, fall back
  to **two images** — torch and JAX run as sequential subprocesses, so differing CUDA versions in
  separate containers is not a conflict. No re-decision needed.
- ⚠️ **HARD CONSTRAINT ON U2a**: base image is **Python 3.9**, so **`rfd-core` must target 3.9** —
  no `StrEnum` (use `class X(str, Enum)`), no runtime PEP 604 unions (use `Optional[...]` plus
  `from __future__ import annotations`), no `match`. `rfd-web` is unconstrained.
- **e3nn 0.3.3, not 0.5.5** — the notebook used 0.5.5 only because Colab's newer torch required it;
  on torch 1.12 the inherited pin is the correct one.

## U1 Research Findings (2026-07-31)
1. **Official `rosettacommons/rfdiffusion` container exists but is unusable as-is.**
   `inference.dump_pdb` / `dump_pdb_path` exist **only in the sokrypton fork** — they are the entire
   mechanism behind FR-16 and FR-17. The official image cannot provide live progress.
   Its *pinned dependency set* is still valuable as a base.
2. **Two viable stacks, far apart**: official = CUDA 11.6 / torch 1.12.1+cu116 / dgl 1.0.2+cu116 /
   e3nn 0.3.3, **fully pinned and proven**; notebook = CUDA 12.4 / torch 2.4 / e3nn 0.5.5,
   **almost entirely unpinned**.
3. ⚠️ **The proven stack cannot run on `lgpu`.** `gpu` = V100 (sm_70), `lgpu` = L40s (**sm_89**).
   CUDA 11.6 predates Ada Lovelace (sm_89 needs ≥11.8), so torch 1.12.1+cu116 is **V100-only**.
   Supporting `lgpu` means resolving the CUDA 12.x stack ourselves — R-1/R-2 in full.

## Units (5, amended from 4 by Units Generation Q1=A)
| Unit | Package / dir | Depends on | Testable without cluster |
|---|---|---|---|
| **U1** Runtime and Container | `containers/`, `scripts/`, `docs/` | — | no |
| **U2a** Core Domain | `rfd-core` | — | **fully** |
| **U2b** Runner | `rfd-runner` | U1, U2a | partially |
| **U3** Slurm and Persistence | `rfd-web/{slurm,persistence,services}` | U2a, U1 (template) | with fake Slurm |
| **U4** Web Application | `rfd-web/{routes,templates,static}` | U2a, U3 | yes |

- **Milestone M1** "working CLI pipeline" after U1+U2a+U2b, verified by hand-written `sbatch`
- **Phase A parallelism**: U1 and U2a both start immediately — the largest schedule lever
- **U2a is deliberately OFF the critical path** — the point of the split

## Application Design Decisions
| Ref | Decision |
|---|---|
| DD-1 | `uv` **workspace, three packages**: `rfd-core` (pure), `rfd-runner` (GPU), `rfd-web` (login node). `rfd-web` → `rfd-core` only, resolver-enforced, keeping PyTorch out of the web env |
| DD-2 | Runner source **bind-mounted** into the container; image holds dependencies only (fast iteration) |
| DD-3 | Live frame published **every N steps, default 5, configurable** |
| DD-4 | **Separate `progress.json`** (volatile) from `run.json` (durable), both written atomically |
| DD-5 | Original notebook moved to **`reference/diffusion.py`**, unmodified (rollback path preserved) |
| DD-6 | **`current_frame.pdb` bridge** — resolves the FR-17 / G-11 conflict discovered during design: `$TMPDIR` is node-local to the compute node and invisible to the login-node web app, so per-step churn stays on scratch (G-11) while only the latest frame is atomically published to persistent storage |

## Execution Plan Summary
- **Units**: U1 Runtime and Container · U2 Core Domain and Runner · U3 Slurm Integration and
  Persistence · U4 Web Application
- **Critical path**: U1 → U2 → U3 → U4, with U1's *validation* deliberately overlapped onto U2's
  development window (U1 is highest-risk but independent; U2 is pure Python needing no cluster)
- **Stages to execute**: Application Design, Units Generation, Infrastructure Design (U1 only),
  Functional Design (U2 and U3 only), Code Generation (all 4 units), Build and Test
- **Stages to skip**: User Stories; NFR Requirements (all units); NFR Design (all units);
  Functional Design (U1, U4); Infrastructure Design (U2, U3, U4)
- **Risk level**: HIGH (R-1/R-2, the Apptainer GPU dependency stack)
- **Rollback**: EASY — `diffusion.py` is never modified and remains a working Colab fallback

## Confirmed Architectural Decisions
- **Runtime model**: **Submit-and-track** (user decision, 2026-07-30). The web app is launched
  independently of any run, submits Slurm batch jobs, tracks them, and survives both the browser
  closing and the 6-hour OpenOnDemand interactive cap.
- **Implications**: web app is GPU-free and PyTorch-free; run state must be persisted outside
  process memory; the app is a Slurm client (sbatch/squeue/sacct), not a compute process;
  two distinct environments are implied (light web app env + heavy RFdiffusion runtime env).

## Settled Requirements Decisions (Requirements Analysis)
| Ref | Decision |
|---|---|
| Q1 | **FastAPI + HTMX**, server-rendered, no Node toolchain; 3Dmol.js vendored as a single script |
| Q2a | Web app on a **Grex login node**, bound to `127.0.0.1`, reached via SSH tunnel with `ControlMaster` (Duo answered once interactively; tunnel reuses the master socket) |
| Q3 | **`uv`** for the web app project; **Apptainer** image for the RFdiffusion/JAX GPU runtime |
| Q4 | **Full pipeline, one click** — backbone generation + ProteinMPNN/AlphaFold validation |
| Q5 | **Full notebook-parity live progress** per job (step counter + live structure preview) |
| Q6 | **Single Slurm job running one program** (user's proposal, adopted). `contigs`/`copies` stay in-memory variables. Persistence = SQLite index on `/home` + `run.json` per run directory as the job→web-app status/progress/provenance channel. Runner takes `--stage {all,backbone,validate}` for retry. |
| Q7 | **Single user, no auth**; SSH login is the authentication |
| Q8 | **`/home`** for now, downside explicitly accepted; all paths configurable via env vars |
| Q9/10/11 | **B / B / B** — all extensions opted out; no blocking compliance gates |

## Binding Constraint: Grex Documentation Adherence
User constraint (2026-07-31): *"My only constraint is making sure https://um-grex.github.io/docs/
are very strongly adhered to."* Captured as requirements **G-1 through G-20** in requirements.md
section 5A. Execution model confirmed as ordinary **`sbatch` batch jobs** per
running-jobs/batch-jobs; the web app is a thin wrapper generating a conventional `#SBATCH` script,
introducing no alternative execution mechanism.

Key documented idioms now binding:
- `$TMPDIR` for per-job scratch (replaces the notebook's `/dev/shm`); `export SLURM_TMPDIR=$TMPDIR`
- Never emit `--qos=` (documented as "Not to be used on Grex!")
- Always explicit `--time`, `--mem-per-cpu`, `--gpus=`, `--partition=`
- GPU defaults from Grex's own template: `--gpus=1 --cpus-per-task=6 --mem-per-cpu=6000M`
- Container image pulled/built ahead of time, never at job start; `--nv` for GPU
- Partitions discovered at runtime — Grex's own pages disagree on GPU partition names

## Verified Grex Constraints
- Default walltime **3 hours** — `--time` must always be requested explicitly
- Max walltime **7 days on `gpu`** partition (21 days on CPU partitions) — ample for a single-job full pipeline
- General GPU capacity is small: **2 nodes in `gpu` (4x V100 32GB), 2 nodes in `lgpu` (2x L40s 48GB)** — this is why a chained second job was rejected: it would re-queue for a new allocation
- GPU-partition jobs are **rejected unless they request GPUs** (`--gpus=`)
- Grex MFA docs explicitly recommend `ControlMaster`/`ControlPersist` to cache Duo sessions

## Intent Analysis (Requirements Analysis Step 2)
- **Request Clarity**: Clear in intent, incomplete in detail
- **Request Type**: Migration (Colab notebook to standalone web app) + Upgrade (ad-hoc pip to uv)
- **Scope**: System-wide — effectively a rewrite preserving one core algorithm
- **Complexity**: Complex
- **Requirements Depth Selected**: **Comprehensive**

## Workspace State
- **Existing Code**: Yes
- **Programming Languages**: Python (single file: `diffusion.py`, Colab-exported notebook)
- **Build System**: None detected (no pyproject.toml, requirements.txt, package.json, setup.py)
- **Project Structure**: Single-script / notebook export (not a packaged application)
- **Reverse Engineering Needed**: Yes
- **Workspace Root**: /home/pieberrykinnie/rfdiffusion-gui

## User Objective
Port the Colab RFdiffusion notebook (`diffusion.py`) into:
1. A project managed by the **uv** package manager
2. A **lightweight web UI application**
3. Appropriate for deployment on the **Grex HPC cluster** (University of Manitoba)

## Target Environment Summary (Grex HPC)
- **Scheduler**: Slurm
- **GPU partitions**: `gpu` (2 nodes x 4x V100 32GB), `lgpu` (2 nodes x 2x L40s 48GB)
- **CPU partitions**: skylake, largemem, genoa, genlm, test
- **Web access**: OpenOnDemand (ood.hpc.umanitoba.ca), max 6h interactive walltime, MFA + VPN required
- **Python policy**: NO system-wide conda (Anaconda licensing); virtualenv + pip explicitly preferred
- **Containers**: Apptainer / Singularity-CE available, `--nv` for GPU passthrough
- **Modules**: CCEnv (Alliance stack) + SBEnv
- **Storage**: /home 100 GB per user; /project 5 TB per group (Lustre)

## Code Location Rules
- **Application Code**: Workspace root (NEVER in aidlc-docs/)
- **Documentation**: aidlc-docs/ only
- **Structure patterns**: See code-generation.md Critical Rules

## Extension Configuration
| Extension | Enabled | Decided At |
|---|---|---|
| security/baseline | **No** | Requirements Analysis (2026-07-30, user answered 9a=B) |
| resiliency/baseline | **No** | Requirements Analysis (2026-07-30, user answered 10a=B) |
| testing/property-based | **No** | Requirements Analysis (2026-07-30, user answered 11a=B) |

**Deferred rule loading**: all three extensions opted OUT, so their full rules files were NOT loaded
(`security-baseline.md`, `resiliency-baseline.md`, `property-based-testing.md`). No extension rules
are enforced as blocking constraints at any stage. Substantive protections remain in scope as
ordinary requirements — see NFR-11 through NFR-14 and FR-21 in requirements.md.

**User priority**: speed — *"I need this working ASAP"* (2026-07-30). This informs depth selection at
Workflow Planning and favours skipping optional stages.

## Stage Progress

## Reverse Engineering Status
- [x] Reverse Engineering - Artifacts generated on 2026-07-30T22:57:31Z (awaiting user approval)
- **Artifacts Location**: aidlc-docs/inception/reverse-engineering/
- **Artifacts**: business-overview.md, architecture.md, code-structure.md, api-documentation.md,
  component-inventory.md, interaction-diagrams.md, technology-stack.md, dependencies.md,
  code-quality-assessment.md, reverse-engineering-timestamp.md

## Key Reverse Engineering Findings (carried into Requirements Analysis)
- `diffusion.py` is a 6-cell Colab notebook export; cells 1, 2, 4 are commented out and are NOT
  executable Python as shipped. They hold the provisioning logic and every helper function.
- 7 business transactions identified (BT-1 provision, BT-2 generate backbone, BT-3 monitor progress,
  BT-4 review backbone, BT-5 design+validate sequence, BT-6 review best, BT-7 export).
- Core reusable asset: `run_diffusion()` (~120 lines) plus the contig mode-inference block.
  Everything else is provisioning, Colab glue, or notebook-bound presentation.
- Hard blockers for the port: `google.colab.files` (upload/download), `apt-get install aria2` (root),
  `dist-packages` symlink, cross-cell global state (`path`, `contigs`, `copies`, `num_designs`).
- Zero tests, zero linting, zero type hints, no dependency manifest or lockfile.
- Shared-cluster risks not present on Colab: shell injection via unsanitised parameters (TD-7),
  fixed `/dev/shm/{n}.pdb` paths colliding between concurrent users (TD-13).
- ~8 GB of model weights re-downloaded every Colab session; on Grex these become one-time staged
  assets that must live on `/project`, not `/home` (100 GB quota).

### INCEPTION PHASE
- [x] Workspace Detection - COMPLETED 2026-07-30T22:57:31Z
- [x] Reverse Engineering - COMPLETED and APPROVED 2026-07-30T23:10:00Z
- [x] Requirements Analysis - COMPLETED 2026-07-30T23:55:00Z (awaiting approval)
  - Artifacts: requirements.md, requirement-verification-questions.md,
    requirements-clarification-questions.md, requirements-clarification-questions-2.md
  - 24 functional requirements, 18 non-functional requirements, 12 constraints, 7 risks
- [x] Requirements Analysis - **APPROVED** 2026-07-31T00:25:00Z
- [x] User Stories - **SKIPPED** (offered at the Requirements approval gate; not requested)
- [x] Workflow Planning - COMPLETED 2026-07-31T00:25:00Z (awaiting approval)
  - Artifact: aidlc-docs/inception/plans/execution-plan.md
- [x] Application Design - **APPROVED** 2026-07-31T01:00:00Z
  - Artifacts: components.md, component-methods.md, services.md, component-dependency.md,
    application-design.md — 29 components, 4 services, 3 packages
  - Approval was conditional on notebook parameter parity; parity verified parameter-by-parameter,
    `visual` restored as `live_preview` (DD-7), condition met
- [x] Units Generation - COMPLETED 2026-07-31T01:10:00Z (awaiting approval)
  - Artifacts: unit-of-work.md, unit-of-work-dependency.md, unit-of-work-story-map.md
  - Plan: unit-of-work-plan.md (all checkboxes [x])

### CONSTRUCTION PHASE (per-unit loop over U1, U2a, U2b, U3, U4)
- [x] U1 Runtime and Container: Infrastructure Design **DONE** → Code Generation **DONE** 2026-07-31
      (Functional Design SKIP, NFR Requirements SKIP, NFR Design SKIP)
      - Artifacts: `containers/rfdiffusion.def`, `scripts/{preflight-grex,build-image,stage-weights,verify-image}.sh`,
        `env.example`, `docs/setup.md`, `reference/`, `.gitignore`
      - **Preflight verified on `yak`**: 16 PASS / 0 WARN / 0 FAIL
      - **Image built and weights staged on Grex** ✅
      - **Verified on CPU node `n339` 2026-08-06, first execution** ✅ — check 3 (the
        approach-invalidating one) PASSED; jaxlib CUDA pin intact; two defects found in
        `verify-image.sh` and fixed
      - **Re-verified same node, second execution** — both script fixes confirmed; found and fixed
        **Defect 3, in the image itself**: `icecream` and `pyrsistent` missing (see §8.1f)
      - **Rebuilt and re-verified same node, third execution** ✅ — **PASS 9 / FAIL 3**, check 6 now
        fully passing. U1's entire CPU-verifiable surface is clean; the 3 FAILs are exactly the
        predicted GPU-gated set (checks 1, 2, JAX device test)
      - **First real GPU allocation, 2026-08-06** ⚠️ — the §3 risk **materialized**: `jaxlib 0.4.25`
        requires CUDA ≥ 11.8, this base runs CUDA 11.6.2. Re-pinned to `jaxlib 0.4.7` + `chex 0.1.82`.
      - **First build attempt with that re-pin FAILED at the resolution step** ⚠️ — `optax==0.2.2`'s
        full dependency list (not just its `jax` bound, which is all that was checked) declares
        `chex>=0.1.86`, conflicting with `chex==0.1.82`. Caught immediately by `uv`, before staging —
        the "one resolution pass" design working as intended. Re-pinned `optax==0.1.7`; also checked
        `dm-haiku`'s unconditional `flax>=0.7.1` dependency this time (missed in the first pass) and
        confirmed it's compatible.
      - **Rebuilt and re-verified on GPU, 2026-08-07** ✅ — **PASS 13 / FAIL 0** on a real GPU
        allocation (NVIDIA A30, `agpu` partition, sm_80). Both approach-invalidating checks passed:
        check 3 (fork, `dump_pdb` present) and check 4 (JAX reports `StreamExecutorGpuDevice`, a
        real CUDA GPU, not a CPU fallback). Only non-`OK` line is the pre-known, non-fatal `ananas`
        warning. **U1 verification is complete — the §3 risk is closed.**
- [x] U2a Core Domain: Functional Design **DONE** → Code Generation **DONE** 2026-08-01
      (NFR Requirements SKIP, NFR Design SKIP, Infrastructure Design SKIP)
      - 157 tests, 100% coverage, verified on real Python 3.9.25 locally
- [x] U2b Runner: Functional Design **DONE** → Code Generation **DONE** 2026-08-13
      (NFR Requirements SKIP, NFR Design SKIP, Infrastructure Design SKIP)
      - **74 tests, 97% overall coverage — 100% on every module except `_colabdesign.py`** (36%,
        structurally by design: those are the bridge's own `from colabdesign...` import lines,
        which only execute inside the real container)
      - Verified on real Python 3.9.25 locally; `import rfd_runner` succeeds with **zero
        ColabDesign/torch/JAX/RFdiffusion-fork installed**, direct proof the `_colabdesign.py`
        bridge-module isolation holds
      - Testability fix made during generation: `OrchestratorDeps.dump_dir` (defaults to
        `/scratch`, the container's fixed `$TMPDIR` bind target) — promoted from a bare module
        constant so the mandatory pre-inference `mkdir schedules` step is testable against
        `tmp_path` rather than the real filesystem root
      - Artifacts: `packages/rfd-runner/` (15 source modules, 542 statements), `env.example`
        (`RFD_STEP_TIMEOUT_SECONDS`, `RFD_POLL_INTERVAL_MS` added), documentation at
        `aidlc-docs/construction/u2b-runner/code/u2b-code-summary.md`
      - **Code Generation APPROVED 2026-08-13** ("Approve code generation and continue with AI-DLC
        until the codebase is at a gate that requires verification on grex")
- [x] **Milestone M1** — working CLI pipeline, verified by hand-written `sbatch` on a Grex GPU node.
      **✅ PASSED 2026-08-27 (job 7556085, node `g325`, real Tesla V100-SXM2-32GB, elapsed
      00:01:27).** All 5 exit criteria from unit-of-work.md met on real hardware: (1) the container
      ran `run_inference.py` on a Grex GPU node — `backbone_state: "completed"`, `m1smoke_0.pdb`
      and `traj/` written; (2) a real design completed via plain `sbatch` with a hand-written
      script — `sacct` reports `COMPLETED` / `0:0`; (3) the job script conforms to G-1…G-18 (see
      the table in `docs/m1-verification.md`, with the G-15/G-17 rows corrected in round 7);
      (4) `run.json`, `progress.json` and `current_frame.pdb` were all written as specified;
      (5) `rfd-core`'s suite passes independently (231 tests across rfd-core + rfd-runner).
      Final `run.json`: `backbone_state: "completed"`, `validate_state: "completed"`,
      `error: null`, outputs `m1smoke/best.pdb`, `m1smoke/best_design.pdb`,
      `m1smoke.result.zip`. **Seven real executions, seven distinct root causes** — see the
      Current Stage entry below and `aidlc-docs/audit.md` for the full chain. **U3 is now
      unblocked.**

      Two non-blocking observations recorded at the pass, neither affecting the M1 criteria:
      - `progress.json` freezes once BACKBONE ends (final read: `stage: "backbone"`, step 49/50).
        By design — `ProgressReporter` is only wired into `_run_backbone`; `_run_validate`
        (`orchestrator.py:222-263`) never touches it. **U4 prerequisite**: the web UI will need a
        progress signal during VALIDATE, which does not currently exist.
      - `progress.json`'s `frame_path` stays `null` for the whole run: `ProgressReporter.set_frame()`
        is never called by the orchestrator (only `update_step()` is). `current_frame.pdb` is
        published correctly regardless, so FR-17 works — but **U4 prerequisite**: anything reading
        the preview path off `progress.json` will get `null` until `set_frame()` is wired in.

      Verification artifacts prepared 2026-08-13:
      - `scripts/m1-prepare-run.sh` — builds a run directory + minimal `run.json` (an 80-residue
        de novo `DesignMode.FREE` smoke test, `--stage all`), validated locally against the real
        `rfd_core.RunRecord` model (Python 3.9.25) before being written to disk
      - `scripts/m1-submit.sh` — hand-written `sbatch` script, the concrete instance of
        deployment-architecture.md section 3's template; `bash -n` clean; checked line-by-line
        against G-1…G-18 in `docs/m1-verification.md`
      - `docs/m1-verification.md` — step-by-step instructions, exit-criteria checklist (per
        unit-of-work.md's 5 M1 exit criteria), and an explicit scope-limits section (this smoke
        test exercises `DesignMode.FREE` only — template resolution and AnAnaS/`symmetry=auto`
        are not exercised and remain open for a later spot-check)
      - ⚠️ **First real execution, 2026-08-13 13:34 CDT (job 7441234, node `g325`, real V100)
        FAILED, 1-second runtime.** Everything upstream of the crash worked: GPU visible via
        `--nv`, `module load singularity`, `apptainer exec`, all bind mounts (traceback paths
        confirm `/opt/rfdgui` resolved correctly), `PYTHONPATH` found `rfd_runner`/`rfd_core` as
        bind-mounted source. **Root cause: `ModuleNotFoundError: No module named 'pydantic'`** —
        `rfd_core/models.py` imports `pydantic` (its one declared dependency,
        `packages/rfd-core/pyproject.toml`), but `containers/rfdiffusion.def` predates rfd-core's
        existence (written during U1, before U2a/U2b), so it was never added. Same class of gap as
        the U1 icecream/pyrsistent miss (§8.1f) — a package needed by an import chain that didn't
        exist when the image's dependency list was written. **Fixed**: added
        `uv pip install --python "$VPY" --no-cache "pydantic>=2.0,<3"` to `rfdiffusion.def`,
        pinned to match rfd-core's own constraint exactly.
      - ✅ **Rebuild (job 7441239, CPU, 17m28s) COMPLETED.** ⚠️ **Second real execution, 2026-08-13
        14:02 CDT (job 7441266, node `g325`, real V100) FAILED, 3-second runtime** — confirms the
        `pydantic` fix: the traceback now gets much further, past `rfd_core`'s import entirely and
        into real business logic (`_run_backbone` → `ContigNormaliser` → the `_colabdesign.py`
        bridge → ColabDesign's real `fix_contigs` → its AlphaFold submodule → `haiku`), proving
        DD-2's bind-mount design and the bridge module's lazy-import seam both work against the
        real container. **New root cause: `ModuleNotFoundError: No module named 'jax.extend'`**,
        from `haiku/_src/dot.py` (`dm-haiku==0.0.12`), imported unconditionally by bare
        `import haiku`. Traced via GitHub commit history (jax-ml/jax, path=jax/extend): commit
        `ca39457ea9` ("move jax.linear_util to jax.extend.linear_util") landed 2023-08-30, just
        after jax 0.4.15's release the same day — so `jax.extend` first exists in jax 0.4.16
        (2023-09-19). **No jax version is both new enough to have `jax.extend` and old enough for
        the CUDA-11.6 ceiling this project already established** (cuda11 jaxlib builds stop at
        0.4.7; 0.4.8+ needs CUDA≥11.8) — the fix has to go the other way. Checked dm-haiku's own
        release history: `0.0.10` (2023-07-14) predates the `jax.extend` commit itself, so it
        cannot reference it — **confirmed by reading `haiku/_src/dot.py`'s actual source at the
        `v0.0.10` tag**: plain `jax.linear_util`/`jax.core`/`jax.experimental.pjit`, no
        `jax.extend` anywhere; `jax==0.4.7` still exposes `jax.linear_util` at the top level (only
        moved, not removed, until much later). ColabDesign's `setup.py` pins no `dm-haiku` version
        at all (re-confirmed), so no cascading conflict. **Fixed**: `dm-haiku==0.0.12` →
        `dm-haiku==0.0.10` in `rfdiffusion.def`, comment block rewritten with the full research
        trail.
      - ⚠️ **Third real execution (job 7442555, node `g325`) FAILED** — confirms the `dm-haiku`
        fix: traceback advances one more frame, past `haiku` entirely, into
        `colabdesign/af/alphafold/model/config.py`. **Root cause:
        `ModuleNotFoundError: No module named 'ml_collections'`** — ColabDesign is installed
        `--no-deps` (deliberately, so it cannot perturb the jax/chex/optax/dm-haiku resolution),
        so none of its own `setup.py install_requires` were ever pulled in automatically.
        Diffed the full list against what's already installed rather than fixing one import at a
        time: genuine gap is `ml-collections`, `biopython`, `dm-tree`, `pandas`, `scipy`,
        `matplotlib` (six packages — `absl-py`/`numpy` already come in transitively via
        `dm-haiku`/`chex`/`optax`). **Caught a second risk before it caused a fourth failure**: a
        local dry-run resolve of these six alongside the existing jax/jaxlib pins picked
        `numpy==2.0.2` — a NumPy 2.0 ABI break against the March-2023 `jaxlib==0.4.7` wheel. The
        already-verified PASS-13 GPU run proves the base image's real numpy is safely `<2`, so this
        was working by installation-order accident, not an enforced constraint. Checked
        scipy/pandas/matplotlib's actual PyPI `requires_dist` for a safe floor and re-pinned
        `numpy>=1.23,<2` — dry-run resolves cleanly to `numpy==1.26.4`. **Fixed**: all six packages
        plus the `numpy` pin added to the *same* one-resolution-pass `uv pip install` command (per
        that section's own stated principle). **Not yet rebuilt or re-verified** — and explicitly
        flagged that the local dry-run tests dependency resolution only, not real container import
        success; a fourth gap is possible if ColabDesign's own `setup.py` is itself incomplete.
      - ✅ **Rebuild confirmed** (implicit — the fourth execution's traceback advances past every
        prior failure point). ⚠️ **Fourth real execution (job 7443066, node `g325`) FAILED** —
        confirms the six-package ColabDesign-dependency fix: the traceback advances well past
        `ml_collections`/`config.py` this time, through ColabDesign's own `__init__` → `af.model` →
        `shared.model` → a real `import optax` → optax's own internal `contrib` module →
        `jax.scipy.stats.norm` — a chain that never executed before. **New root cause, not a
        missing package this time**: `AttributeError: module 'scipy.linalg' has no attribute
        'tril'`. `jax==0.4.7`'s `jax/_src/scipy/linalg.py` applies `@_wraps(scipy.linalg.tril)` /
        `@_wraps(scipy.linalg.triu)` as decorators at **module import time**, so both names must
        exist as attributes of `scipy.linalg` regardless of whether jax's own wrappers are ever
        called. The previously-unbound `"scipy"` entry let `uv` resolve to `1.13.1` (confirmed by
        the third-round dry-run note). **Root-caused by fetching `scipy/linalg/__init__.py` at the
        v1.10.1, v1.11.4, and v1.12.0 tags** (all three still document `tril`/`triu`) **and at
        v1.13.0** (zero occurrences of either name) — the removal lands exactly at scipy 1.13.0
        (April 2024), a year after `jax==0.4.7` (March 2023) was written against the old API. Same
        shape as the `dm-haiku`/`jax.extend` incompatibility: `jax==0.4.7` is fixed in place by the
        CUDA-11.6 ceiling, so the fix pins scipy backward. Chose `1.12.0` — the newest release that
        still has `tril`/`triu`, minimizing drift from the rest of the pinned set. Verified via
        PyPI `requires_dist`: `scipy==1.12.0` needs `numpy>=1.22.4,<1.29.0` (compatible with the
        existing `numpy>=1.23,<2` pin); `ml-collections`/`biopython`/`dm-tree` declare no scipy
        dependency at all, and `pandas`'s only scipy reference is behind its unused
        `computation`/`all` extras — no cascading conflict. **Fixed**: `"scipy"` →
        `"scipy==1.12.0"` in `rfdiffusion.def`'s same one-resolution-pass install command. **Not
        yet rebuilt or re-verified.**
      - ✅ **Rebuild confirmed** (implicit — the fifth execution advanced past every prior failure
        point with no import error at all). ⚠️ **Fifth real execution (job 7443486, node `g325`)
        FAILED** — but differently from every prior round: `sbatch` reported `exit code 1`, yet
        `rfd-m1-smoke-7443486.err` was **completely empty**. This is not a mystery — it is
        `orchestrator.py`'s designed error-handling contract. `_run_backbone`/`_run_validate`
        (`packages/rfd-runner/src/rfd_runner/orchestrator.py:112-134,183-199`) catch every
        anticipated failure (template resolution, symmetry detection, and — most likely here, a
        FREE-mode smoke test with no template/symmetry — a non-zero exit from the
        `run_inference.py` subprocess) and write the failure into `RunRecord.error`
        (`inference_executor.py`'s `InferenceResult.stderr_tail`, the last ~4KB of the crashing
        subprocess's own stderr) via `record.save(run_dir)`, then `return 1` — **deliberately
        without printing anything to the job's own stdout/stderr**, so U3/U4 can later surface
        errors through the queryable `RunRecord` rather than by scraping Slurm logs. The real
        error text is sitting in `run.json` inside the run directory
        (`/home/vuqh1/rfd-runs/m1-smoke-20260813T224637Z/run.json` for this run), in the `error`,
        `exit_code`, `backbone_state`, and `validate_state` fields — not in the `.err` file. Ruled
        out an import-time crash (would have printed Python's default traceback to stderr
        regardless, as all four prior rounds did) and a `RunRecord.load` failure (same reasoning,
        and the `.out` log shows the script reached `nvidia-smi` and the `apptainer exec` line
        cleanly). **Confirmed via `run.json`**: `backbone_state: "failed"`, `exit_code: 1`, `error`
        holds the real traceback (from `run_inference.py`'s own subprocess, captured by
        `InferenceResult.stderr_tail`) — **`TypeError: 'weights_only' is an invalid keyword
        argument for Unpickler()`**, raised inside `torch.load()` at
        `/opt/RFdiffusion/inference/model_runners.py:171` (`load_checkpoint`). **Root-caused via
        source, not guessed**: fetched `inference/model_runners.py` at the pinned `RFD_SHA`
        (`597d37f2a686e23941440fddf6daa4cb778e7bc7`) directly via `gh api` — the fork's own
        `load_checkpoint()` calls `torch.load(self.ckpt_path, weights_only=False,
        map_location=self.device)`. `weights_only` only became a real `torch.load()` parameter in
        **torch 1.13** (Oct 2022); this project is pinned to **`torch==1.12.1+cu116`**, forced by
        the same CUDA-11.6 ceiling (base image) that drove every jax/jaxlib/dm-haiku/scipy pin
        above — torch cannot be bumped to fix this without breaking that ceiling. On 1.12.1,
        `torch.load()`'s `**pickle_load_args` catch-all silently absorbs the unrecognised
        `weights_only` kwarg and forwards it straight to `pickle_module.Unpickler(data_file,
        **pickle_load_args)`, which rejects it — exactly the observed `TypeError`. **Fixed**:
        patched `containers/rfdiffusion.def` to `sed` the fork's source immediately after
        clone+checkout (before any other build step touches it), dropping `weights_only=False,`
        from the `torch.load()` call so it falls back to the plain `torch.load(path,
        map_location=...)` signature 1.12.1 actually supports — behaviourally equivalent on
        1.12.1, which has no `weights_only`-restricted unpickler to opt out of in the first place.
        Added a build-time `grep`/`ast.parse` guard so the build fails loudly if the patch ever
        stops matching (same "fail the BUILD, not a job three hours from now" pattern already used
        for the `dump_pdb` keys check immediately above it). Verified the extracted `%post` block
        is still syntactically valid bash (`bash -n`) after the edit. **Not yet rebuilt or
        re-verified.**
      - ✅ **Rebuild confirmed** — **Sixth real execution (job on `g325`) BACKBONE STAGE PASSED**,
        the first time any stage has completed on real Grex hardware (`backbone_state: "completed"`,
        real `.pdb`/trajectory outputs written). ⚠️ **VALIDATE stage FAILED** (`validate_state:
        "failed"`) — a new failure mode again confirmed via `run.json`'s `error` field (not the
        `.err` file, per the 5th-round finding): `jaxlib.xla_extension.XlaRuntimeError:
        FAILED_PRECONDITION: Couldn't get ptxas/nvlink version string: INTERNAL: Couldn't invoke
        ptxas --version`, raised from ColabDesign's AlphaFold model
        (`colabdesign/af/alphafold/model/utils.py`'s `flat_params_to_haiku`) — the first code path
        in this whole pipeline that makes jax actually **compile and execute** an XLA op on GPU
        (BACKBONE is pure torch/RFdiffusion; jax is otherwise only imported, never compiled
        against). **Root-caused via source, not guessed**: fetched `jax/_src/lib/__init__.py` at
        the pinned `jax-v0.4.7` tag — its `_cuda_path()` looks first for a sibling
        `nvidia/cuda_nvcc` site-packages directory (the pip package `nvidia-cuda-nvcc-cu11`,
        which ships `bin/ptxas` + `nvvm/libdevice`), and otherwise "hope[s] the user has ptxas in
        their PATH" (its own comment) — this project never installed that package, and the base
        image (a torch/RFdiffusion runtime image, not a CUDA devel toolchain) has no system
        `ptxas` either. **Fixed**: added `nvidia-cuda-nvcc-cu11==11.7.99` to the same
        one-resolution-pass `uv pip install` command in `containers/rfdiffusion.def` (no exact
        11.6.x build exists on PyPI — checked, only 11.7.99/11.8.89 published for cu11; 11.7.99 is
        safe via CUDA's PTX forward-compatibility guarantee within the 11.x line, and the
        installed driver, 580.173.02/CUDA 13.0, is far newer than ptxas 11.7's ~515.x minimum).
        Verified via PyPI `requires_dist` that the package declares no runtime dependencies of its
        own — no cascading conflict. Added a build-time `test -x .../nvidia/cuda_nvcc/bin/ptxas`
        guard (same "fail the BUILD" pattern used throughout this file). **Also closed the
        verification gap that let this reach a real GPU job undetected**: `scripts/verify-image.sh`
        check 4 only ever called `jax.devices()`, which reports a CUDA device without invoking
        XLA's compiler — it could never have caught a missing-`ptxas` failure. Strengthened it to
        actually compile and run a real `jnp` op (`.block_until_ready()`) and assert success, so
        this class of gap fails at `verify-image.sh` time going forward, not deep into a real M1
        job. **Not yet rebuilt or re-verified.**
      - **Next action is the user's**: `bash scripts/build-image.sh --force` (inside a CPU
        `salloc`) to rebuild with the `nvidia-cuda-nvcc-cu11` fix, then
        `bash scripts/verify-image.sh` (GPU allocation) to confirm check 4 now passes its new
        real-compile assertion, then re-run `sbatch scripts/m1-submit.sh <run_dir>` (a fresh
        `run_dir`, or the existing one — `RunRecord` is idempotent, and `backbone_state` is already
        `completed` so a re-run should proceed straight to VALIDATE) and report back — checking
        `run.json` first if `.err` is empty again, per the 5th-round finding.
- [x] U3 Slurm Integration and Persistence: Functional Design **DONE** → Code Generation **DONE**
      and **APPROVED 2026-08-27** ("Approve and Park")
      (NFR Requirements SKIP, NFR Design SKIP, Infrastructure Design SKIP)
      - **✅ VERIFIED ON REAL GREX HARDWARE 2026-08-27** via `scripts/u3-verify.py`
        (+ `docs/u3-verification.md`), in three phases:
        **Phase 1 read-only, 34 PASS / 1 WARN / 0 FAIL** — real `sinfo` parsed (nine GPU
        partitions: `gpu`, `agpu`, `lgpu`, `livi`, `livi-b`, `mcordgpu`, `mcordgpu-b`,
        `stamps`, `stamps-b`; `gpu` correctly default, `lgpu` correctly annotated
        image-incompatible — and **more partitions than `env.example` documents**, which is
        exactly why FR-6a forbids a hard-coded list); real `squeue`→`sacct` fallback parsed
        job 7556085 as `COMPLETED exit_code=0 signal=0`; an unknown job id returned
        `UNKNOWN(known=False)` rather than raising, so BR-4 holds against the real client;
        `log_tail` surfaced the actual causes of the failed M1 rounds (FR-19 real, not
        theoretical); 11 existing run directories reconciled with none skipped or
        mis-flagged.
        **Phase 2 real submission, 6 PASS / 0 FAIL — the gate**: job **7556197** was
        submitted from a job script this code **generated**, not one written by hand, and
        completed. Queued 15 s, elapsed ~1m45s; tracked `PENDING → RUNNING → COMPLETED`
        with live step progress (0 → 42 → 49 of 50) and `current_frame.pdb` published
        during the run, so FR-16 and FR-17 are confirmed at the data level; outputs
        included both trajectories, `best.pdb`, `best_design.pdb` and the result zip;
        BR-2 held (reported `completed` because Slurm said `COMPLETED` **and** `run.json`
        was finalised) and BR-3 held (re-reading issued zero further Slurm calls).
        **Phase 3 cancellation, 5 PASS / 0 FAIL**: job 7556200 cancelled and reported as
        **cancelled**, attributed *"cancelled from this app"*, with the runner's misleading
        *"likely walltime exceeded"* sentence suppressed (BR-8); a second `cancel()` was
        not an error (BR-11).
      - **Three defects found by reading the real phase-1 output rather than stopping at
        "0 FAIL"**, all fixed with regression tests (suite 225 → 228): `log_tail` could
        return a partial first line after a truncated read; runs recovered by startup
        reconciliation displayed `slurm=UNKNOWN` when no query had been made at all (now
        `None` — absence of knowledge is not a state word); and the verification script's
        own `sacct` cross-check silently did nothing, reporting PASS while proving
        nothing, because no M1 run directory carries a `slurm_job_id` (only S-1 writes
        one) — it now WARNs loudly. **Correction recorded**: the partial-first-line fix
        was prompted by a `nt call last):` fragment that persisted after the fix, so that
        particular fragment is not the byte seek and appears to be in the file on disk;
        the fix remains correct for the case it names.
      - **Still not exercised by a real run**: BR-5's frozen-progress path (validation
        finished inside the 120 s staleness window, so *"validating (no step-level progress
        available)"* never appeared — covered by unit tests only); `resubmit()` /
        `--stage validate` (FR-11); and M1's standing scope limits (`DesignMode.FIXED`/
        `PARTIAL`, AnAnaS / `symmetry=auto`).
      - **U4 note**: eight M1 run directories report as permanently `queued` — their
        hand-made `run.json` has `backbone_state: pending` and no job id, which the
        reconciliation rules render correctly but which will sit in U4's run list forever.
        Not a U3 defect (every run U3 submits records its job id before indexing). Options
        recorded in `docs/u3-verification.md`.
      - **Code Generation COMPLETE 2026-08-27** — `packages/rfd-web`, the third and final workspace
        package. **225 tests, 96% coverage, real Python 3.9.25**; `rfd-core` (157) and `rfd-runner`
        (74) re-run unchanged, **456 total**. Everything is verified locally, as
        `unit-of-work.md` promised for this unit ("testable without cluster: with fake Slurm"):
        real SQLite files in `tmp_path`, real directories, real `bash`, real subprocesses against
        stub Slurm binaries on `PATH`. **The generated job script is EXECUTED under bash against a
        stub engine** across the same four scenarios M1's round-7 fix was verified against (only
        `singularity`; only `apptainer`; neither → exit 127 with the G-15 message; missing
        `run.json` → exit 2 with the engine provably never invoked) — the M1 lesson that a
        hardcoded binary name is invisible to any test that merely reads the script. G-1…G-18 are
        asserted rule by rule, and every row of the S-2 reconciliation table has its own test,
        including BR-2 (Slurm `COMPLETED` + non-finalised `run.json` ⇒ **FAILED**, never a false
        success) and BR-3 (a terminal run issues **zero** further Slurm calls, proven by call
        counting). Artifacts: `packages/rfd-web/` (18 source modules, 1023 statements, 14 test
        files), `env.example` (+6 variables), summary at
        `aidlc-docs/construction/u3-slurm-persistence/code/u3-code-summary.md`.
      - **⚠ One correction made during generation (Step 1): `rfd-web` cannot target Python ≥ 3.11.**
        The plan, `domain-entities.md` §8, and the root `pyproject.toml`'s own comment (written in
        U2a) all said it did; `uv lock` refused outright. The deeper reason is not a uv quirk —
        `rfd-web` depends on `rfd-core`, which is capped below 3.10 so it can import inside the U1
        container, so **any** environment able to import `rfd-core` is a 3.9 environment, the login
        node included. A 3.11 `rfd-web` was never installable. Keeping it would have required
        making `rfd-web` a standalone project with its own lockfile, breaking DD-1's approved "uv
        workspace, three packages". Corrected in all four places; the package targets
        `>=3.9,<3.10` and carries the same `UP045`/`UP007` ruff ignore as its siblings.
      - **Not proven, and stated plainly**: no real Slurm was contacted (stub binaries emitting real
        Slurm output formats prove the parsing and the argument lists, not that Grex emits those
        exact strings); no generated job has been submitted; `sinfo`'s real column content on Grex
        is unverified (a mismatch degrades discovery to a free-text partition field, not an outage);
        `squeue`/`sacct`/`scancel` error-string matching is based on documented Slurm messages.
      - **Functional Design APPROVED 2026-08-27.** Part 1 (plan + 8
        questions) and Part 2 (artifact generation) both done in one session; the user answered
        **A to all 8 questions** — no ambiguity, no follow-ups. Artifacts at
        `aidlc-docs/construction/u3-slurm-persistence/functional-design/`:
        `business-logic-model.md`, `business-rules.md` (BR-1 … BR-23), `domain-entities.md`.
        Settled by those answers: S-1 `SubmissionService` is built **in U3** minus the browser
        upload (Q1=A), so U3's definition of done is actually reachable; `JobScriptGenerator`
        emits the **M1-proven** script shape rather than the broken section-3 template (Q2=A);
        partitions are discovered and **annotated**, never filtered, with incompatibility driven by
        `RFD_INCOMPATIBLE_PARTITIONS` config rather than code (Q3=A); run ids are sanitised names
        with a random suffix on collision, using `mkdir(exist_ok=False)` as the race-free collision
        test (Q4=A); SQLite is rebuilt from run directories at startup (Q5=A); `CANCELLED` from
        Slurm suppresses the runner's misleading walltime message and `cancel_requested_at` is
        recorded (Q6=A); `log_tail` reads `.err` first, falling back to `.out` (Q7=A);
        `resubmit(run_id, stage)` exists and writes `job-validate.sh` alongside `job.sh`, giving
        FR-11 its first caller (Q8=A).
      - **`deployment-architecture.md` section 3 corrected as part of this stage** — its template's
        runner invocation could never have worked (`--run-dir`/`--scratch` do not exist; the
        interpreter is `/app/RFdiffusion/.venv/bin/python`), and its bind map bound the whole
        output root. Both now match the M1-proven script, plus run-directory log placement so
        `RunDirectoryReader` can satisfy FR-19. Section 2's bind-map row and the G-11/G-15
        conformance rows were updated to match.
      - **Two M1 findings previously recorded as U4 prerequisites are resolved here rather than
        deferred**: `progress.json` freezing during VALIDATE is handled by BR-5 (reported as
        "validating (no step-level progress available)", never as a stall), and
        `ProgressState.frame_path` always being `null` is handled by BR-6 (live-preview
        availability is decided by `current_frame.pdb` existing on disk, not by that field).
      - Part 1 planning record — four discrepancies between the design docs and the code that
        actually ran on Grex were found during the pre-plan research and are recorded there as
        findings F-1…F-4 rather than resolved silently: (F-1) `deployment-architecture.md`
        section 3's template invokes `python3.9 -m rfd_runner --run-dir … --scratch …`, but the
        shipped runner CLI takes a **positional** run_dir, has no `--scratch`, and the container's
        interpreter is `/app/RFdiffusion/.venv/bin/python`; (F-2) that template binds
        `$RFD_OUTPUT_ROOT` while the M1-proven script binds only the single run directory;
        (F-3) `scancel` makes the runner's SIGTERM handler write `FAILED` / "likely walltime
        exceeded" while Slurm reports `CANCELLED`, so S-2 must reconcile a real contradiction;
        (F-4) runtime partition discovery (FR-6a) will surface `lgpu`, which the Phase 1 CUDA 11.6
        image cannot run on. Six decisions were taken without asking (D-1…D-6 in the plan).
- [ ] U4 Web Application: Code Generation **EXECUTE**
      (Functional Design SKIP, NFR Requirements SKIP, NFR Design SKIP, Infrastructure Design SKIP)
- [ ] Build and Test - **EXECUTE**

## Current Status
*(Corrected 2026-08-13 — U2b Runner code generation approved; Milestone M1 verification artifacts
prepared and awaiting execution on real Grex hardware.)*
- **Lifecycle Phase**: **CONSTRUCTION** (INCEPTION complete and fully approved)
- **Current Stage**: **Milestone M1 — ✅ PASSED 2026-08-27 (job 7556085, real V100, 00:01:27).**
  U1 + U2a + U2b are code-complete, approved, and now proven to work together on real Grex
  hardware. The gate is cleared and **U3 is unblocked.** It took **seven real executions and seven
  distinct root causes**, every one found from primary sources (pinned upstream source, PyPI
  metadata, JAX's own changelog and `_cuda_path()` implementation) rather than guessed: (1, job
  7441234) `pydantic` missing — fixed, rebuild (job 7441239) confirmed it; (2, job 7441266)
  `dm-haiku==0.0.12` imports `jax.extend`, incompatible with the CUDA-11.6-mandated `jax==0.4.7`
  ceiling — fixed by downgrading to `dm-haiku==0.0.10`, rebuild confirmed it; (3, job 7442555)
  ColabDesign's `--no-deps` install never pulled its own dependencies —
  `ml-collections`/`biopython`/`dm-tree`/`pandas`/`scipy`/`matplotlib` added, plus a `numpy<2` pin
  after a local dry-run surfaced a real NumPy-2.0 ABI-break risk — rebuild confirmed it; (4, job
  7443066) unbound `scipy` resolved to `1.13.1`, which removed `scipy.linalg.tril`/`triu` that
  `jax==0.4.7` references at module-import time — fixed by pinning `scipy==1.12.0`, the newest
  release that still has both names; (5, job 7443486) the fork's own
  `model_runners.py` calls `torch.load(..., weights_only=False)`, a kwarg that only exists from
  torch 1.13 — fixed by a build-time `sed` patch in `containers/rfdiffusion.def` rather than a
  torch bump (torch is pinned by the same CUDA-11.6 ceiling), rebuild confirmed it; (6, job of
  2026-08-13T23:22Z) **BACKBONE completed for the first time**, VALIDATE failed with
  `XlaRuntimeError: Couldn't invoke ptxas --version` — `nvidia-cuda-nvcc-cu11` was never installed,
  so both of JAX's own ptxas lookup paths came up empty; fixed by adding
  `nvidia-cuda-nvcc-cu11==11.7.99` to the same one-resolution-pass install, and `verify-image.sh`
  check 4 was strengthened to force a real XLA compile (it previously only called `jax.devices()`,
  so it structurally could not have caught this); (7, job 7556080) **exit 127 before the container
  ever started** — `scripts/m1-submit.sh:63` hardcoded the CCEnv binary name `apptainer`, but
  Grex's `singularity` module provides a `singularity` binary; `module load` had succeeded silently,
  which is why `.err` held only that one line. Fixed by adopting the engine detection that
  `build-image.sh`/`verify-image.sh`/`preflight-grex.sh` already used, and fixed at source in
  `deployment-architecture.md` section 3's template so U3's JobScriptGenerator does not regenerate
  the same bug into every future job script. **Round 8 (job 7556085) then passed end to end**,
  which also gave round 6's ptxas fix its first real test — VALIDATE completed, confirming
  `nvidia-cuda-nvcc-cu11==11.7.99` closed the XLA/ptxas failure.

  **Pattern worth carrying into U3/U4**: six of the seven root causes were version-ceiling
  collisions forced by the CUDA 11.6.2 base image (`torch==1.12.1+cu116` → `jax==0.4.7` →
  everything downstream). The seventh was different in kind — a hardcoded assumption in a script
  that no test covered — and it was the only one that cost a GPU allocation to discover something
  not GPU-dependent at all. U3's JobScriptGenerator should be unit-testable against a fake engine
  for exactly this reason.
- **Completed**: U1 Code Generation and verification (2026-08-06/07, six rounds — three CPU, one
  GPU risk-materialization, one build-time resolver failure, one final GPU confirmation), U2a Core
  Domain (157 tests, 100% coverage, real Python 3.9.25), U2b Runner Functional Design and Code
  Generation (74 tests, real Python 3.9.25, zero ColabDesign/torch/JAX installed) — **APPROVED
  2026-08-13**
- **Next Stage**: **U3 — ENTERED 2026-08-27. Functional Design is COMPLETE and awaiting approval;
  U3 Code Generation follows.** The milestone that gated it (M1)
  passed on 2026-08-27. Per
  unit-of-work.md, U3 is the Slurm/job-orchestration unit whose `JobScriptGenerator` (C-23) emits
  the job script `scripts/m1-submit.sh` is the hand-written instance of. Entering U3 starts with
  its CONSTRUCTION stages (Functional Design onward) and requires user approval at each, per the
  workflow. **Carry into U3 from M1**: (a) the engine-name detection fix is already in
  `deployment-architecture.md` section 3's template, so the generator must emit detection rather
  than a hardcoded binary name; (b) `JobScriptGenerator` should be unit-testable against a fake
  engine — round 7's bug was invisible to every existing test and cost a GPU allocation to find.
- **Status**: **U1, U2a, U2b are all done and proven together on real hardware (M1 passed
  2026-08-27, job 7556085).** FR-16/FR-17 confirmed achievable and now confirmed working
  (sokrypton fork on PYTHONPATH, `dump_pdb` present, `current_frame.pdb` published during a real
  run); the §3 risk this project carried since infrastructure design (`jaxlib 0.4.25` needing
  CUDA ≥ 11.8 against an 11.6.2 base) materialized, was root-caused via JAX's changelog, and is
  closed — `jax==0.4.7` / `jaxlib==0.4.7+cuda11.cudnn86` / `chex==0.1.82` / `optax==0.1.7` /
  `nvidia-cuda-nvcc-cu11==11.7.99` verified on a real A30 and now a real V100 end to end. Tier 2
  (§3, two images) was never needed.
- **Next milestone**: **M2** (post-U3) — never formally defined in `unit-of-work.md`, which
  names only M1. What M2 would have covered for U3 is now done: U3's definition of done is
  met on real hardware (jobs 7556197 submitted-and-completed from a generated script, 7556200
  cancelled). The remaining pre-U4 gaps are listed under the U3 entry above. M1 is passed. Note M1's scope limits still stand and are
  NOT yet covered by any real run: `DesignMode.FIXED`/`PARTIAL` template resolution, AnAnaS /
  `symmetry=auto`, and `--stage backbone`/`--stage validate` used independently. Worth a manual
  spot-check before U4 exposes them through the web form (`docs/m1-verification.md`, "Known scope
  limits").

### OPERATIONS PHASE
- [ ] Operations - PLACEHOLDER
