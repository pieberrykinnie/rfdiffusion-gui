# U2a Core Domain — Code Generation Plan

**Unit**: U2a Core Domain (`rfd-core`)
**Stage**: CONSTRUCTION — Code Generation
**Date**: 2026-08-01
**Workspace root**: `/home/pieberrykinnie/rfdiffusion-gui`

> Single source of truth for this generation pass.

**Local capability check performed before writing this plan**: `uv 0.10.11` is installed locally and
can provision Python 3.9.25 on demand (`uv python install 3.9`). This means the real test suite can
be run **locally, against the exact Python version the container uses**, right now — not merely
written and left unverified until Grex is reachable. That will be done at the end of this plan.

---

## Unit Context

**Requirements owned**: FR-4, FR-5, FR-12, NFR-1, NFR-2, NFR-6, NFR-9, NFR-11, NFR-17.
**Source of truth for behaviour**: `business-logic-model.md`, `business-rules.md`,
`domain-entities.md` (U2a Functional Design, approved).
**Dependencies**: none. **Consumed by**: U2b, U3, U4 (all via `import rfd_core`).

---

## Steps

### Step 1: Project Structure Setup
- [x] Root `pyproject.toml` — virtual `uv` workspace, `members = ["packages/*"]` (DD-1)
- [x] `packages/rfd-core/pyproject.toml` — `requires-python = ">=3.9,<3.10"` pinned tight (not just a
      floor), since the one thing that must never silently drift is compatibility with the container's
      exact interpreter
- [x] `packages/rfd-core/src/rfd_core/` package skeleton + `py.typed` marker
- [x] `packages/rfd-core/tests/` directory

### Step 2: Business Logic Generation (per business-logic-model.md)
- [x] `contigs.py` — `Segment`, `ContigSpec`, `ContigParseError`, `get_Ls`
- [x] `modes.py` — `DesignMode`, `infer_mode`
- [x] `symmetry.py` — `SymmetryKind`, `SymmetryPlan`, `resolve_symmetry`, `apply_detected_group`
- [x] `iterations.py` — `IterationPlan`, `plan_iterations`
- [x] `argv.py` — `build_inference_argv`, `format_hotspot`

### Step 3: Business Logic Unit Testing
- [x] `tests/test_contigs.py` — grammar cases from business-logic-model.md §1 + business-rules.md §2,
      including every row of the notebook's own worked examples
- [x] `tests/test_modes.py` — the full mode-inference behaviour table (business-logic-model.md §2),
      row for row
- [x] `tests/test_symmetry.py` — resolution + deferred/AnAnaS reapplication (§3)
- [x] `tests/test_iterations.py` — including the notebook's own worked example (200→80, 50→20) and
      the TD-11 fix (non-numeric `partial_T` rejected, not an unhandled crash)
- [x] `tests/test_argv.py` — override ordering matches §5 exactly, including the "no nested quoting
      needed" property (NFR-11)
- [x] `tests/test_properties.py` — **Hypothesis property tests** (NFR-17's targeted PBT, per the
      requirements-analysis 11a=B decision — not a blocking rule set, but genuinely warranted here):
  - `infer_mode` never raises for any string `ContigSpec.parse` accepts
  - re-parsing `ContigSpec.to_list()`'s output is idempotent
  - `plan_iterations` output is always a positive integer for any valid `(mode, iterations, partial_T)`
  - `build_inference_argv` never contains a raw shell metacharacter unescaped in a way that would
    matter if accidentally shelled out (defence in depth for NFR-11, even though the real protection
    is "never use a shell" in U2b/U3)

### Step 4: Business Logic Summary
- [x] Confirm every notebook behaviour row in business-logic-model.md has a corresponding test

### Step 5: Data Layer Generation (models + persistence — this unit's equivalent of "repository layer")
- [x] `models.py` — `DesignRequest`, `StageState`, `RunOutputs`, `RunRecord`, `ProgressState`
- [x] `storage.py` — `write_json_atomic`, `read_json`
- [x] `paths.py` — `PathLayout`
- [x] `validation.py` — `ValidationOutcome`, `validate(request)`, `preview_mode(contigs)`

### Step 6: Data Layer Unit Testing
- [x] `tests/test_models.py` — round-trip serialisation, `schema_version` present, Python
      3.9-compatible enum behaviour (`StageState.PENDING == "pending"` etc.)
- [x] `tests/test_storage.py` — atomic write survives a simulated interrupted write (kill between temp
      write and replace leaves either the old or new file, never a partial one); `read_json` returns
      `None` rather than raising on a missing/corrupt file
- [x] `tests/test_paths.py` — env var resolution and `/home` defaults (NFR-6)
- [x] `tests/test_validation.py` — every rule in business-rules.md §1/§2/§3, including the warning-vs-
      error distinction

### Step 7: Data Layer Summary
- [x] Confirm every field in `domain-entities.md` has a corresponding model field and test

### Step 8: Documentation Generation
- [x] `aidlc-docs/construction/u2a-core-domain/code/u2a-code-summary.md`

### Step 9: Local Verification (not a template step — specific to what's actually possible here)
- [x] `uv python install 3.9` — provision the exact interpreter the container uses
- [x] `uv sync` at the workspace root
- [x] `uv run --package rfd-core pytest -v` — full suite, run for real, locally, now
- [x] `uv run --package rfd-core python -c "import rfd_core"` on 3.9 specifically — proves NFR-1/NFR-2
      (no heavy deps, works standalone) without needing Grex at all

---

## Explicitly Out of Scope for U2a

- Anything importing ColabDesign, RFdiffusion, or PyTorch (U2b)
- `RequestValidator`'s web-form integration (C-26 is *used* by U4; its logic lives here as
  `validation.py`, but the HTTP route/template wiring is U4)
- `SlurmAdapter`, SQLite (U3)
- Actual GPU execution of anything (that needs the U1 image, still pending Grex availability)
