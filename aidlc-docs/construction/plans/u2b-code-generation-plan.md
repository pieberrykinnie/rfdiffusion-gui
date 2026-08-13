# U2b Runner — Code Generation Plan

**Unit**: U2b Runner (`rfd-runner`)
**Stage**: CONSTRUCTION — Code Generation
**Date**: 2026-08-13
**Workspace root**: `/home/pieberrykinnie/rfdiffusion-gui`

> Single source of truth for this generation pass.

**Local capability check performed before writing this plan**: no GPU, no Apptainer image, and no
ColabDesign/RFdiffusion-fork/torch/JAX installation exist in this worktree — `rfd-runner` only ever
executes for real inside the U1 container on a Grex GPU node (Milestone M1). This plan does not
pretend otherwise. What it **does** prove locally, using the same `uv`-provisioned Python 3.9.25 as
U2a: every piece of control flow, file I/O, and subprocess orchestration that does not itself require
GPU hardware or the ColabDesign/fork packages to be installed. This is possible because every call
into ColabDesign or the fork is routed through one bridge module (`_colabdesign.py`, Step 2) that
tests replace with fakes — the package must **import and its non-GPU logic must run correctly with
zero ColabDesign/torch/JAX installed**, which is itself real evidence, not a placeholder.

**Confirmed against the actual shipped `containers/rfdiffusion.def`** (not the application-design
sketch, which used slightly different env var names) before writing this plan:
- Entry point: `exec /app/RFdiffusion/.venv/bin/python -m rfd_runner "$@"` (line 302)
- `PYTHONPATH=/opt/rfdgui/packages/rfd-core/src:/opt/rfdgui/packages/rfd-runner/src:/opt/RFdiffusion:...`
  (line 289) — both packages are bind-mounted and imported directly, never pip-installed into the venv
- `RFD_FORK=/opt/RFdiffusion`, `RFD_MODELS=/opt/RFdiffusion/models` (checkpoints are baked into the
  base image and symlinked into the fork — **not** staged under `RFD_WEIGHTS`, confirmed in
  infrastructure-design.md §8.1d), `RFD_AF_PARAMS=/opt/weights/alphafold`,
  `ANANAS_BIN=/opt/weights/bin/ananas` (lines 291–296)
- These four env vars are **already exported by the container's `%environment` block** — `rfd-runner`
  reads them rather than re-deriving or hardcoding the same paths a second time

---

## Unit Context

**Requirements owned**: FR-3 (resolution half — upload is U4), FR-9, FR-11, FR-12 (with U2a), FR-13,
FR-16, FR-17, FR-18, FR-31, FR-33 (writes), NFR-9 (with U2a), NFR-10, NFR-11 (with U2a/U3), NFR-12,
NFR-13, G-9, G-11, G-12, G-13, G-14.

**Source of truth for behaviour**: `business-logic-model.md`, `business-rules.md`,
`domain-entities.md` (U2b Functional Design, approved this session). Component contracts:
`components.md` C-11…C-20, `component-methods.md` C-11…C-20, `services.md` S-4.

**Dependencies**: `rfd-core` (U2a, approved — `ContigSpec`, `infer_mode`, `resolve_symmetry`,
`apply_detected_group`, `plan_iterations`, `build_inference_argv`, `get_Ls`, `RunRecord`,
`ProgressState`, `DesignRequest`, `StageState`, `PathLayout`, `write_json_atomic`/`read_json`) and the
U1 container's runtime contract (env vars above, Python interpreter path, fork location).
**Consumed by**: U3 (invokes this package's `%runscript` via `sbatch`; never imports it directly —
`rfd-web` must never depend on `rfd-runner`, per unit-of-work.md).

---

## Design Decision Made Without Asking: the ColabDesign/fork Bridge Module

**Decision**: every call into a ColabDesign function (`pdb_to_string`, `fix_contigs`,
`fix_partial_contigs`, `fix_pdb`, `sym_it`) or the fork's `inference.utils.parse_pdb` is routed
through one module, `_colabdesign.py`, as a thin function that does the import **inside the function
body** (not at module load) and can be monkeypatched wholesale in tests.

**Why this wasn't put to the user**: `components.md` already establishes the principle for
`ContigNormaliser` ("the only component that must import ColabDesign for contig work") — this plan
extends the same principle to the two other call sites that need it (`PdbPostProcessor`,
`SymmetryDetector`'s coordinate transform) rather than leaving them as three separate hard import-time
dependencies. It costs one small module and changes no documented behaviour or interface; it is what
makes the unit-of-work table's "partially testable without cluster" actually true in practice rather
than aspirational, by giving every test a single, obvious seam to patch. Reversible by deleting the
indirection if it ever proves unnecessary.

---

## Steps

### Step 1: Project Structure Setup
- [ ] `packages/rfd-runner/pyproject.toml` — `requires-python = ">=3.9,<3.10"` (matches the container
      interpreter, same reasoning as `rfd-core`); depends on `rfd-core` as a workspace member; declares
      **no** torch/JAX/ColabDesign dependency (those are provided by the container image per DD-2 —
      declaring them here would make `uv sync` fail or attempt a pointless local install)
- [ ] `packages/rfd-runner/src/rfd_runner/` package skeleton + `py.typed` marker
- [ ] `packages/rfd-runner/tests/` directory
- [ ] Confirm root `pyproject.toml`'s `members = ["packages/*"]` glob already picks this up (no edit
      needed — verified against U2a's identical setup)

### Step 2: Business Logic Generation (per business-logic-model.md / component-methods.md)
- [ ] `config.py` — `RunnerConfig` (env-var-driven, `from_env()` pattern matching `rfd_core.PathLayout`):
      `step_timeout_seconds` (`RFD_STEP_TIMEOUT_SECONDS`, default 1800), `poll_interval_ms`
      (`RFD_POLL_INTERVAL_MS`, default 100), `frame_every_n` (`RFD_FRAME_EVERY_N`, default 5),
      `fork_root` (`RFD_FORK`, default `/opt/RFdiffusion`), `models_dir` (`RFD_MODELS`, default
      `/opt/RFdiffusion/models`), `af_params_dir` (`RFD_AF_PARAMS`, default `/opt/weights/alphafold`),
      `ananas_bin` (`ANANAS_BIN`, default `/opt/weights/bin/ananas`), `python_bin` (default
      `/app/RFdiffusion/.venv/bin/python`, not currently overridden by any env var — matches the
      container's fixed venv path)
- [ ] `errors.py` — `RunnerError` base; `AnanasUnavailableError` (business-rules.md §3, carries the
      three required message elements); `NoCompletedBackboneError` (business-rules.md §1, the
      `--stage validate` retry-without-backbone case)
- [ ] `_colabdesign.py` — the bridge module (see Design Decision above): `pdb_to_string(path, chains)`,
      `parse_pdb(path)`, `fix_contigs(contigs, parsed_pdb)`, `fix_partial_contigs(contigs, parsed_pdb)`,
      `fix_pdb(pdb_str, contigs)`, `sym_it(x, center, axis1, axis2=None)` — each a one-line lazy import
      + call, with the exact source module documented in a comment
      (`colabdesign.shared.protein.pdb_to_string`, `inference.utils.parse_pdb`,
      `colabdesign.rf.utils.{fix_contigs,fix_partial_contigs,fix_pdb,sym_it}` — verified against
      `reference/diffusion.py` lines 79–82)
- [ ] `template.py` — `TemplateResolver.resolve_template(pdb, run_dir, *, fetch=None) -> Optional[Path]`
      (C-11): local path pass-through; 4-char code → `wget` RCSB `.pdb1.gz` + `gunzip` (argv list, no
      shell, NFR-11); otherwise → `wget` AlphaFold DB; pre-uploaded file already in `run_dir` (no
      `google.colab.files` branch, per unit-of-work.md). `fetch` is an injectable
      `Callable[[List[str]], None]` defaulting to `subprocess.run`, for testability without network
- [ ] `symmetry_detector.py` — `SymmetryDetector.detect_symmetry(pdb_str, run_dir, *, ananas_bin=None,
      run_cmd=None) -> Optional[SymmetryDetection]` (C-12): raises `AnanasUnavailableError` if the
      binary is missing/not executable (checked **before** any subprocess, business-rules.md §3);
      invokes `ananas` via argument list (`[ananas_bin, pdb_filename, "-u", "-j", out_filename]`,
      transcribed from `reference/diffusion.py` lines 102–110, no shell string); parses the JSON result
      distinguishing "ran, found nothing" (`None`, not an error — NFR-12) from a parse/JSON failure
      (raises `SymmetryDetectionError`, replacing the notebook's bare `except:`, TD-8); applies the
      bridge's `sym_it` per group type to rebuild ATOM records (lines 121–139)
- [ ] `contig_normaliser.py` — `ContigNormaliser.normalise_contigs(spec, mode, parsed_pdb, copies) ->
      List[str]` (C-13): calls the bridge's `fix_contigs`/`fix_partial_contigs` by mode, then
      replicates by `copies` (notebook line 327, `sum([contigs] * copies, [])`)
- [ ] `inference_executor.py` — `InferenceResult` dataclass (`exit_code`, `stderr_tail`);
      `InferenceExecutor.run_inference(argv, total_steps, num_designs, dump_dir, on_step, *,
      popen_factory=subprocess.Popen, timeout_seconds=None, poll_interval_ms=None) -> InferenceResult`
      (C-14): the exact algorithm in business-logic-model.md §3 — clear stale dumps, `Popen.poll()`
      liveness (replacing `os.kill(pid, 0)`), per-step deadline from `RunnerConfig`, `STALL_EXIT_CODE`
      on timeout with `proc.terminate()` then `proc.kill()` if still alive, last-4KB stderr capture.
      `popen_factory` is injectable so tests substitute a fake process — the only way this component's
      real behaviour is checkable without ever launching a real subprocess
- [ ] `frame_publisher.py` — `FramePublisher` class exactly as specified in `component-methods.md` C-15
      (constructor `run_dir, every_n=5, enabled=True`; `maybe_publish(step, frame) -> Optional[Path]`),
      using `rfd_core.storage`'s atomic-replace pattern for `current_frame.pdb`
- [ ] `progress_reporter.py` — `ProgressReporter` class per C-16 (`update_step`, `set_frame`,
      `set_stage`), writing `rfd_core.models.ProgressState` via `.save(run_dir)`
- [ ] `pdb_postprocessor.py` — `PdbPostProcessor.fix_outputs(run_dir, name, num_designs, contigs) ->
      None` (C-17): for each design `n`, rewrite `{run_dir}/{name}_{n}.pdb`,
      `{run_dir}/traj/{name}_{n}_pX0_traj.pdb`, `{run_dir}/traj/{name}_{n}_Xt-1_traj.pdb` through the
      bridge's `fix_pdb` (transcribed exactly from `reference/diffusion.py` lines 345–352, including
      the trajectory-file naming RFdiffusion itself imposes)
- [ ] `validation_executor.py` — `ValidationExecutor.run_validation(run_dir, name, normalised_contigs,
      copies, request, *, popen_factory=None, cwd=None) -> InferenceResult` (C-18): builds `val_argv`
      exactly per business-logic-model.md §2 steps 12–13 (`python -m
      colabdesign.rf.designability_test` plus every flag, optional flags only when set); `cwd` defaults
      to `RunnerConfig.af_params_dir` (business-rules.md §6, mandatory, not a convenience default) —
      reuses `InferenceExecutor`'s `popen_factory` seam rather than a second injection mechanism
- [ ] `result_packager.py` — `ResultPackager.stage_out(tmpdir, run_dir) -> None` (a no-op assertion:
      G-13 is satisfied by construction per business-logic-model.md §1.3, so this exists to make that
      invariant checkable, not to perform a copy); `ResultPackager.package_results(run_dir, name) ->
      Path` — zips `{name}*` and `traj/{name}*` using Python's stdlib `zipfile` (an improvement over
      the notebook's `!zip -r` shell-out at line 565: same file selection, zero subprocess, NFR-11 by
      construction rather than by argument-list discipline)
- [ ] `orchestrator.py` — `Stage(str, Enum)` (NOT `StrEnum` — Python 3.9, same fix as U2a's
      `ruff --fix` incident, `class X(str, Enum)` from the start this time); `OrchestratorDeps`
      dataclass bundling the ten collaborators above with real defaults, injectable as a single
      parameter so the full control flow is unit-testable (the seam the "partially testable" line in
      `unit-of-work.md`'s summary table depends on); `main(run_dir, stage=Stage.ALL, deps=None) -> int`
      implementing business-logic-model.md §2 verbatim: `--stage all`/`backbone`/`validate` selection,
      `RunRecord` load/mutate/save at every transition, `ananas`-absent fail-fast before any subprocess,
      SIGTERM handler (business-rules.md §4) installed for the duration of the run
- [ ] `__main__.py` — `argparse` CLI: positional `run_dir`, `--stage {all,backbone,validate}` (default
      `all`); calls `orchestrator.main()`; `sys.exit(result)` — the exact contract
      `containers/rfdiffusion.def`'s `%runscript` invokes (`python -m rfd_runner "$@"`)
- [ ] `__init__.py`

### Step 3: Business Logic Unit Testing
- [ ] `tests/test_config.py` — every `RunnerConfig` field's env-var override and documented default
- [ ] `tests/test_template.py` — local path pass-through (no `fetch` call); 4-char code builds the
      correct `wget`+`gunzip` argv against a fake `fetch`; non-4-char builds the AlphaFold DB argv;
      file already present in `run_dir` short-circuits fetch entirely
- [ ] `tests/test_symmetry_detector.py` — missing/non-executable `ananas_bin` raises
      `AnanasUnavailableError` with all three required message elements (business-rules.md §3) **before**
      `run_cmd` is ever called; a fake `run_cmd` writing a well-formed `ananas.json` is parsed into the
      correct `SymmetryDetection` (group, rmsd, transformed `asymmetric_unit_pdb_str`); a fake `run_cmd`
      producing no/malformed JSON returns `None` for "ran, found nothing" and raises
      `SymmetryDetectionError` for a genuine parse failure — the two must not be conflated (NFR-12)
- [ ] `tests/test_contig_normaliser.py` — fixed/partial/free modes route to the correct bridge function
      via a fake `fix_contigs`/`fix_partial_contigs`; `copies > 1` replication matches
      `sum([contigs] * copies, [])` exactly
- [ ] `tests/test_inference_executor.py` — against a fake `Popen`-shaped object and `tmp_path` dumps:
      normal per-step completion (dump appears with trailing `TER`, `on_step` fires, dump deleted);
      process exits with a fast final write still ending `TER` (treated as success, not failure); process
      exits non-zero with no valid dump (`InferenceResult.exit_code`/`stderr_tail` populated, last 4KB
      only); per-step timeout triggers `terminate()` then `kill()` and returns the stall exit code;
      pre-existing stale `{n}.pdb` files are cleared before the run starts
- [ ] `tests/test_frame_publisher.py` — publishes only every `every_n` steps; `enabled=False` never
      writes; target path and atomicity (via `rfd_core.storage`) verified in `tmp_path`
- [ ] `tests/test_progress_reporter.py` — `update_step`/`set_frame`/`set_stage` produce the correct
      `ProgressState` fields, real round-trip through `rfd_core` in `tmp_path`
- [ ] `tests/test_pdb_postprocessor.py` — for `num_designs > 1`, all three paths per design constructed
      correctly and passed through a fake `fix_pdb`; file contents rewritten, not appended
- [ ] `tests/test_validation_executor.py` — `val_argv` matches business-logic-model.md §2 field-for-field
      including optional-flag omission when unset; `cwd` defaults to `RunnerConfig.af_params_dir` and is
      overridable
- [ ] `tests/test_result_packager.py` — real `zipfile` I/O in `tmp_path`: archive contains exactly the
      `{name}*` and `traj/{name}*` members, nothing else; `stage_out` is a no-op that does not raise
      when the invariant holds
- [ ] `tests/test_orchestrator.py` — full control flow against `OrchestratorDeps` built entirely from
      fakes/spies (no real subprocess, no real ColabDesign): FREE-mode `--stage all` happy path;
      FIXED-mode with a template; PARTIAL-mode; `symmetry=auto` with `ananas` present (detection folded
      back via `rfd_core.apply_detected_group`) and absent (fail-fast, **assert the fake
      `InferenceExecutor` is never invoked**); `--stage backbone` leaves `validate_state=SKIPPED`;
      `--stage validate` against a `RunRecord` with no completed backbone rejects immediately
      (`NoCompletedBackboneError`) without touching Slurm/GPU state; a failing backbone step leaves
      `validate_state` at `PENDING`; SIGTERM during a run writes the exact `FAILED` /
      `"terminated (SIGTERM) — likely walltime exceeded"` state (business-rules.md §4)

### Step 4: Business Logic Summary
- [ ] Confirm every row of business-logic-model.md §2's numbered flow and every rule in
      business-rules.md §1–§6 has a corresponding test — cross-check explicitly, not by inspection alone

### Step 5: Documentation Generation
- [ ] `aidlc-docs/construction/u2b-runner/code/u2b-code-summary.md`

### Step 6: Configuration Artifact Update
- [ ] Add `RFD_STEP_TIMEOUT_SECONDS` and `RFD_POLL_INTERVAL_MS` to `env.example` (currently only
      `RFD_FRAME_EVERY_N` is documented there, from U1) — no `containers/rfdiffusion.def` change needed,
      already confirmed correct against this plan's requirements

### Step 7: Local Verification (not a template step — specific to what's actually possible here)
- [ ] `uv sync` at the workspace root (picks up `rfd-runner` via the existing `packages/*` glob)
- [ ] `uv run --package rfd-runner pytest -v` — full suite, real Python 3.9.25, locally, now
- [ ] `uv run --package rfd-runner python -c "import rfd_runner"` — proves the package imports cleanly
      with **zero ColabDesign/torch/JAX/fork installed** in this environment, which is direct evidence
      the bridge-module isolation (Design Decision above) actually holds and is not just asserted

---

## Explicitly Out of Scope for U2b

- Real execution of `run_inference.py`, `designability_test.py`, or `ananas` — needs the U1 image on a
  real Grex GPU node (Milestone M1); this pass proves the *code around* those subprocess calls, not the
  subprocesses themselves
- `SlurmAdapter`, job script generation/submission, SQLite persistence (U3)
- Web routes, HTMX polling, 3Dmol rendering, template upload handling (U4)
- Re-verifying U1's own container contract — read and confirmed against `containers/rfdiffusion.def` as
  it exists today, not re-derived
