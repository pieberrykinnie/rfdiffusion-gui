# U2b Runner — Business Rules

---

## 1. Failure Taxonomy

Every failure gets a distinct `StageState` and a human-readable `error` string in `RunRecord` —
never a bare traceback, never a silent partial result (NFR-10).

| Failure | `backbone_state` / `validate_state` | `error` content |
|---|---|---|
| RFdiffusion subprocess exits non-zero | `FAILED` | last 4KB of stderr |
| RFdiffusion subprocess stalls past per-step timeout | `FAILED` | "step {n} exceeded {timeout}s" |
| `symmetry=auto` requested, `ananas` binary absent | `FAILED`, before any subprocess starts | see §3 |
| `symmetry=auto` requested, AnAnaS runs but detects nothing | *(not a failure)* | logged; `symmetry_plan` reverts to `none`, run continues — matches notebook |
| AnAnaS detects an unsupported group (not `c*`/`d*`) | `FAILED` | `SymmetryError` message from `rfd-core`, verbatim |
| Template fetch fails (bad PDB code, network error) | `FAILED`, before any subprocess starts | fetch error, verbatim |
| ProteinMPNN/AlphaFold subprocess exits non-zero | `validate_state = FAILED` (backbone stays `COMPLETED`) | last 4KB of stderr |
| `--stage validate` run against a `RunRecord` with no completed backbone | rejected immediately, process exits 1 before touching Slurm state | "no completed backbone stage in {run_id}" |
| Runner process receives SIGTERM (e.g. Slurm walltime hit mid-run) | whichever stage was `RUNNING` → `FAILED` (best-effort; see §4) | "terminated (SIGTERM) — likely walltime exceeded" |

**Principle carried from `rfd-core`**: every failure is written as a value into `RunRecord`, not just
raised and left for Slurm's exit code to (ambiguously) describe. `RunQueryService` (U3) depends on
this — see the reconciliation rule in `services.md`: a terminal Slurm state with a non-finalised
`RunRecord` is reported as failure, but a *properly finalised* `FAILED` record with a real error
message is strictly more informative than that fallback.

---

## 2. Per-Step Timeout — Decision Made, Not Asked

**Decision**: each denoising step gets a configurable timeout (`RFD_STEP_TIMEOUT_SECONDS`, default
**1800** — 30 minutes) measured from the moment the previous step's dump was consumed. If exceeded,
the subprocess is terminated and the run marked `FAILED` with a specific "stalled" message.

**Why this wasn't put to the user**: Slurm's own `--time` limit is already a hard backstop regardless
of this setting — the downside of picking a value here is bounded and fully reversible (it's one
environment variable). The value matters only for *how fast the user finds out something is wrong*:
without it, a hung RFdiffusion process would silently consume the entire Slurm walltime (hours) before
Slurm kills the job and the user sees a bare `TIMEOUT` with no indication of *which* step or *why*.
With it, a stall is caught and reported with a specific step number, typically within the timeout
window rather than at the walltime boundary.

**30 minutes is deliberately generous** — individual RFdiffusion steps normally take seconds; this
threshold exists to catch genuine hangs (e.g. a GPU driver issue), not to second-guess normal
variance. Recorded here as reversible via one config value if it proves wrong in practice.

---

## 3. `ananas` Unavailable — Fail Fast, Explain Clearly

Carried forward from the U1 finding (recorded in `aidlc-state.md`): the notebook's own AnAnaS source
is gone (404), so staging is best-effort and `ananas` may legitimately be absent.

**Rule**: if `request.symmetry == AUTO` and the `ananas` binary is not present or not executable,
`SymmetryDetector` raises before any subprocess is spawned, with a message covering:
1. What was requested (`symmetry=auto`) and why it can't proceed
2. That `none`/`cyclic`/`dihedral` with an explicit order all work fine
3. How to enable `auto` later (`RFD_ANANAS_URL` / manual placement, per `stage-weights.sh`)

**Explicitly not done**: silently falling back to `symmetry=none` and continuing. The notebook did
something close to this for the *"AnAnaS ran but found nothing"* case (§1, "not a failure" row) —
that's a different situation (the detector *worked* and *found nothing*) from *the detector isn't
even present*, and the two must not be conflated. Requesting `auto` and silently getting an
unsymmetric design would be a materially different result than what was asked for, delivered without
any signal.

---

## 4. Signal Handling and Partial Progress

**Rule**: `PipelineOrchestrator` installs a handler for `SIGTERM` (Slurm's walltime-exceeded signal,
and `scancel`'s default signal) that:
1. Forwards `SIGTERM` to the RFdiffusion/validation child process if one is running
   (`proc.terminate()`, matching notebook line 223's `KeyboardInterrupt` handling, generalised).
2. Writes whatever `RunRecord` state is current — `FAILED` for the in-progress stage, with
   `error="terminated (SIGTERM) — likely walltime exceeded"`.
3. Re-raises / exits non-zero, so Slurm's own accounting (`sacct`) also reflects a non-zero exit.

**Best-effort, not guaranteed**: if the runner itself is killed with `SIGKILL` (Slurm sometimes
escalates after a grace period), no handler runs and `RunRecord` is left in whatever state it was
last saved in — `RUNNING`, never updated to `FAILED`. This is precisely the situation `RunQueryService`
(U3)'s reconciliation rule exists for: Slurm reports a terminal state, `RunRecord` doesn't, and the
gap is resolved by trusting Slurm and reporting failure rather than leaving a run stuck showing
`RUNNING` forever.

---

## 5. Subprocess Invocation — No Shell, Anywhere

Every external process this unit launches — `run_inference.py`, `designability_test.py`, `ananas`,
`wget`/`curl` for template fetching — is invoked via `subprocess` with an **argument list**, matching
`rfd-core`'s `build_inference_argv` output directly (NFR-11). No f-string command assembly, no
`shell=True`, anywhere in this unit. This is not a per-call decision; it is a unit-wide constraint
carried from requirements and enforced by code review / the fact that `build_inference_argv` already
returns exactly the shape `subprocess.Popen(argv, ...)` expects.

---

## 6. Validation Subprocess Working Directory — Mandatory, Not a Default

Restated as a rule because it is easy to accidentally regress: **`ValidationExecutor` MUST launch
`designability_test.py` with `cwd=/opt/weights/alphafold`.** This is not a convenience default — it
is the only way ColabDesign's vendored AlphaFold parameter loader (`data_dir="."`) can find the
staged parameters at all, since `designability_test.py` exposes no flag to override it (verified
against source, `business-logic-model.md` §1.2). Getting this wrong doesn't produce a clear error —
it produces a `FileNotFoundError` deep inside JAX/AlphaFold's own loading code, which is exactly the
kind of opaque failure this rule exists to prevent by construction.
