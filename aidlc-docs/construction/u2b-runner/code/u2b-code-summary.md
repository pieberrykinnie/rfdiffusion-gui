# U2b Runner — Code Summary

**Date**: 2026-08-13 · **Status**: complete, fully tested and verified locally on Python 3.9,
zero ColabDesign/torch/JAX installed

---

## Files Created

| Path | Purpose |
|---|---|
| `packages/rfd-runner/pyproject.toml` | Package manifest, `requires-python=">=3.9,<3.10"`, depends on `rfd-core` only (no torch/JAX/ColabDesign — container-provided per DD-2) |
| `packages/rfd-runner/README.md` | Package-level orientation |
| `packages/rfd-runner/src/rfd_runner/config.py` | `RunnerConfig.from_env()` — timeouts, poll interval, frame cadence, container paths |
| `packages/rfd-runner/src/rfd_runner/errors.py` | `RunnerError`, `AnanasUnavailableError`, `NoCompletedBackboneError`, `SymmetryDetectionError` |
| `packages/rfd-runner/src/rfd_runner/_colabdesign.py` | The ColabDesign/fork import bridge — every lazy-imported call site, monkeypatched wholesale in tests |
| `packages/rfd-runner/src/rfd_runner/template.py` | `TemplateResolver` (C-11) — local/RCSB/AlphaFold DB template resolution |
| `packages/rfd-runner/src/rfd_runner/symmetry_detector.py` | `SymmetryDetector`, `SymmetryDetection` (C-12) — AnAnaS invocation and result parsing |
| `packages/rfd-runner/src/rfd_runner/contig_normaliser.py` | `ContigNormaliser` (C-13) — `fix_contigs`/`fix_partial_contigs` routing + copies replication |
| `packages/rfd-runner/src/rfd_runner/inference_executor.py` | `InferenceExecutor`, `InferenceResult` (C-14) — subprocess execution, per-step polling, stall detection |
| `packages/rfd-runner/src/rfd_runner/frame_publisher.py` | `FramePublisher` (C-15) — atomic `current_frame.pdb` publishing |
| `packages/rfd-runner/src/rfd_runner/progress_reporter.py` | `ProgressReporter` (C-16) — `progress.json` writer |
| `packages/rfd-runner/src/rfd_runner/pdb_postprocessor.py` | `PdbPostProcessor` (C-17) — `fix_pdb` pass over final outputs and trajectories |
| `packages/rfd-runner/src/rfd_runner/validation_executor.py` | `ValidationExecutor` (C-18) — `designability_test.py` invocation, mandatory `cwd` |
| `packages/rfd-runner/src/rfd_runner/result_packager.py` | `ResultPackager` (C-19) — G-13 invariant check + `zipfile`-based packaging |
| `packages/rfd-runner/src/rfd_runner/orchestrator.py` | `PipelineOrchestrator` (C-20) — `Stage`, `OrchestratorDeps`, `main()`, SIGTERM handling |
| `packages/rfd-runner/src/rfd_runner/__main__.py` | CLI entry point (`python -m rfd_runner`), matches `containers/rfdiffusion.def`'s `%runscript` |
| `packages/rfd-runner/src/rfd_runner/__init__.py` | Public API surface |
| `packages/rfd-runner/src/rfd_runner/py.typed` | PEP 561 marker |
| `packages/rfd-runner/tests/test_*.py` (12 files) | 74 tests, zero real subprocess, zero ColabDesign anywhere |
| `env.example` | `RFD_STEP_TIMEOUT_SECONDS`, `RFD_POLL_INTERVAL_MS` added |

**15 source modules, 542 statements, 12 test files, 74 tests, 97% overall coverage — 100% on
every module except `_colabdesign.py` (see below).**

---

## Verified, Not Just Written

- **Full suite passes on real Python 3.9.25** (`uv python install 3.9`), the exact interpreter
  the U1 container uses.
- **`import rfd_runner` succeeds with zero ColabDesign/torch/JAX/RFdiffusion-fork installed** in
  this environment — direct proof, not an assumption, that the `_colabdesign.py` bridge-module
  isolation (lazy imports inside function bodies, never at module load) actually holds.
- **100% statement coverage on every module except `_colabdesign.py` (36%)** — and that gap is
  structural, not a shortfall: the 14 uncovered lines are the bridge's own `from colabdesign...` /
  `from inference.utils...` import statements, which by design can only execute inside the real
  container. Every call *site* that uses the bridge (`SymmetryDetector`, `ContigNormaliser`,
  `PdbPostProcessor`, `PipelineOrchestrator`) is itself 100% covered via monkeypatching the bridge
  module wholesale, which is the actual seam the design exists to provide.
- **The SIGTERM handler is tested against a real, tracked subprocess-shaped object**, not only
  against a fake `InferenceExecutor` that bypasses the tracking wiring — `orchestrator.subprocess.Popen`
  is monkeypatched and `time.sleep` is made to raise the signal mid-poll, exercising the actual
  `tracker.factory(subprocess.Popen)` → `SIGTERM` → `proc.terminate()` path end-to-end.
- **`ruff check` (unused imports, import sorting, unused-unpacked-variable) is clean.** Remaining
  default-ruff findings (`UP006`, `UP035`, `C408`, `SIM102`) were checked against `rfd-core` and are
  present there too under an unconfigured `ruff check` — pre-existing noise from this ruff
  version's evolved defaults, not a regression introduced here, and not something the shipped
  U2a package addressed either.

---

## Design Decision Confirmed During Generation: `OrchestratorDeps.dump_dir`

The plan's pseudocode (business-logic-model.md section 2) hardcodes `/scratch` as the dump
directory — correct for production, since that is the container's fixed bind target for
`$TMPDIR`. Implementing it as a bare module constant, though, would make `_run_backbone`'s
`mkdir -p /scratch/schedules` step try to create a directory under the real filesystem root
during every test run. Promoted to a field on `OrchestratorDeps` (`dump_dir: Path`, defaulting to
`Path("/scratch")`) instead — production behaviour is identical (nothing overrides it outside
tests), and the full control-flow, including the mandatory pre-inference `mkdir`, becomes
testable against `tmp_path`. Not put to the user: this is an internal testability fix with no
behavioural or interface change, reversible by deleting the field.

---

## Requirements Satisfied

| Req | Evidence |
|---|---|
| FR-3 (resolution half) | `TemplateResolver.resolve_template` — local/RCSB/AlphaFold DB, tested for all three plus idempotent short-circuiting |
| FR-9, FR-13 | `InferenceExecutor` step-polling algorithm, transcribed from `run()` (notebook lines 144-225) |
| FR-11 | `--stage validate` resumes from the saved `RunRecord`, tested (`test_stage_validate_resumes_from_saved_record`) |
| FR-12 (with U2a) | `PipelineOrchestrator.main` implements business-logic-model.md section 2 verbatim, cross-checked step by step |
| FR-16, FR-17 | `ProgressReporter`/`FramePublisher`, wired via `InferenceExecutor`'s `on_step` hook |
| FR-18 | `ValidationExecutor` — ProteinMPNN/AlphaFold subprocess |
| FR-31 | `ResultPackager.package_results` — stdlib `zipfile`, no shell-out |
| FR-33 (writes) | `RunRecord`/`ProgressState` mutated and saved at every stage transition |
| NFR-9 (with U2a) | `errors.py` docstrings and business-rules.md rows tested individually (ananas absent, no-backbone retry, etc.) |
| NFR-10 | Every failure row in business-rules.md section 1's taxonomy has a corresponding test asserting the exact `StageState`/error content |
| NFR-11 | Every subprocess call (`ananas`, `wget`/`gunzip`, `run_inference.py`, `designability_test.py`) built as an argv list; `zip` replaced entirely by stdlib `zipfile` |
| NFR-12 | `SymmetryDetector` distinguishes "found nothing" (`None`) from a genuine parse failure (`SymmetryDetectionError`) — both paths tested, explicitly asserted not to be conflated |
| NFR-13 | `RunnerConfig.from_env` — all new env vars configurable, tested with overrides |
| G-9 | GPU-only workload boundaries respected — no CPU-only work is a job of its own |
| G-11 | Per-step churn stays on `deps.dump_dir` (`$TMPDIR`/`/scratch`), never on shared storage |
| G-12 | `run_inference.py` invoked via bind-mounted source + container venv Python, no shell |
| G-13 | Satisfied by construction (`output_prefix` points at the persistent run dir); `ResultPackager.stage_out` makes the invariant checkable, tested for both the pass and fail case |
| G-14 | AnAnaS input/output files written into the run directory, not shared scratch |

---

## Explicitly Out of Scope (confirmed unchanged from the plan)

- Real execution of `run_inference.py`, `designability_test.py`, or `ananas` — needs Milestone M1
  on a real Grex GPU node.
- `SlurmAdapter`, job script generation/submission, SQLite persistence — U3.
- Web routes, HTMX polling, 3Dmol rendering, template upload handling — U4.

---

## Next

- **Milestone M1** — a real design via hand-written `sbatch` on a Grex GPU node, exercising U1 +
  U2a + U2b together for the first time end-to-end.
- **U3 Slurm Integration and Persistence** — next unit in the execution plan.
