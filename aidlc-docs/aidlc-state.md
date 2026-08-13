# AI-DLC State Tracking

## Project Information
- **Project Name**: rfdiffusion-gui
- **Project Type**: Brownfield
- **Start Date**: 2026-07-30T22:57:31Z
- **Current Phase**: **CONSTRUCTION** (INCEPTION complete and fully approved)
- **Current Stage**: **U1 image built, staged, and partially verified on Grex (2026-08-06)** — the
  approach-invalidating check PASSED; only GPU-gated checks remain. **U2a Core Domain COMPLETE and
  APPROVED**; **U2b Runner Functional Design complete**, awaiting approval

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
        confirmed it's compatible. Image not yet rebuilt with this corrected set.
      - [ ] **Remaining**: rebuild the image with `jax==0.4.7` / `jaxlib==0.4.7+cuda11.cudnn86` /
        `chex==0.1.82` / `optax==0.1.7`, then the same short multi-partition GPU allocation to
        re-verify —
        `salloc --partition=agpu,stamps-b,mcordgpu-b,gpu,livi-b --gpus=1 --cpus-per-task=2 --mem-per-cpu=4000M --time=0-00:15:00`
        then `bash scripts/verify-image.sh`. Expect PASS 12/FAIL 0. **If the build fails again at
        resolution**, check every pinned package's full `requires_dist`, not just the constraint
        under suspicion. **If it builds but the device check still fails on GPU, the CUDA-11 ceiling
        is exhausted** — go straight to Tier 2 (§3: two images, Q3=B).
- [x] U2a Core Domain: Functional Design **DONE** → Code Generation **DONE** 2026-08-01
      (NFR Requirements SKIP, NFR Design SKIP, Infrastructure Design SKIP)
      - 157 tests, 100% coverage, verified on real Python 3.9.25 locally
- [ ] U2b Runner: Functional Design **EXECUTE** → Code Generation **EXECUTE**
      (NFR Requirements SKIP, NFR Design SKIP, Infrastructure Design SKIP)
- [ ] **Milestone M1** — working CLI pipeline, verified by hand-written `sbatch` on a Grex GPU node
- [ ] U3 Slurm Integration and Persistence: Functional Design **EXECUTE** → Code Generation **EXECUTE**
      (NFR Requirements SKIP, NFR Design SKIP, Infrastructure Design SKIP)
- [ ] U4 Web Application: Code Generation **EXECUTE**
      (Functional Design SKIP, NFR Requirements SKIP, NFR Design SKIP, Infrastructure Design SKIP)
- [ ] Build and Test - **EXECUTE**

## Current Status
*(Corrected 2026-08-06 — this block had gone stale at Units Generation while CONSTRUCTION advanced.)*
- **Lifecycle Phase**: **CONSTRUCTION** (INCEPTION complete and fully approved)
- **Current Stage**: U1 verification — CPU surface fully clean; §3 JAX/CUDA-11 risk materialized on
  first GPU allocation; first re-pin attempt (`jaxlib 0.4.7`) hit a second, transitive conflict
  (`optax`/`chex`) caught at build time; corrected set (`jax==0.4.7`, `jaxlib==0.4.7+cuda11.cudnn86`,
  `chex==0.1.82`, `optax==0.1.7`) not yet rebuilt. U2b Runner Functional Design awaiting approval
- **Completed**: U1 Code Generation (+ 2026-08-06 verification corrections, five rounds — three CPU,
  one GPU, one build-time resolver failure), U2a Core Domain (157 tests, 100% coverage, real
  Python 3.9.25)
- **Next Stage**: U2b Runner — Code Generation (not blocked by U1's remaining GPU re-verification)
- **Status**: U1 nearly verified — **FR-16/FR-17 confirmed achievable**; CPU surface fully clean; the
  §3 risk this project has carried since infrastructure design **has now actually happened**
  (`jaxlib 0.4.25` needs CUDA ≥ 11.8, base is 11.6.2); the first fix attempt was itself incomplete
  (`optax==0.2.2` requires `chex>=0.1.86`, conflicting with the `chex==0.1.82` downgrade) but was
  caught by `uv`'s resolver before any cluster time was spent; corrected pin set awaits a rebuild and
  one more short GPU allocation to confirm. Not blocking U2b.
- **Next milestone**: **M1** — a real design via hand-written `sbatch` on a Grex GPU node

### OPERATIONS PHASE
- [ ] Operations - PLACEHOLDER
