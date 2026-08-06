# U2a Core Domain — Code Summary

**Date**: 2026-08-01 · **Status**: complete, fully tested and verified locally on Python 3.9

---

## Files Created

| Path | Purpose |
|---|---|
| `pyproject.toml` (root) | Virtual `uv` workspace, `members = ["packages/*"]` (DD-1) |
| `packages/rfd-core/pyproject.toml` | Package manifest, `requires-python=">=3.9,<3.10"`, ruff config |
| `packages/rfd-core/README.md` | Package-level orientation |
| `packages/rfd-core/src/rfd_core/contigs.py` | `Segment`, `ContigSpec`, `ContigParseError`, `get_Ls` |
| `packages/rfd-core/src/rfd_core/modes.py` | `DesignMode`, `infer_mode` |
| `packages/rfd-core/src/rfd_core/symmetry.py` | `SymmetryKind`, `SymmetryPlan`, `resolve_symmetry`, `apply_detected_group` |
| `packages/rfd-core/src/rfd_core/iterations.py` | `IterationPlan`, `plan_iterations` |
| `packages/rfd-core/src/rfd_core/argv.py` | `build_inference_argv`, `format_hotspot` |
| `packages/rfd-core/src/rfd_core/models.py` | `DesignRequest`, `RunRecord`, `ProgressState`, `StageState`, `RunOutputs` |
| `packages/rfd-core/src/rfd_core/storage.py` | `write_json_atomic`, `read_json` |
| `packages/rfd-core/src/rfd_core/paths.py` | `PathLayout` |
| `packages/rfd-core/src/rfd_core/validation.py` | `ValidationOutcome`, `validate`, `preview_mode` |
| `packages/rfd-core/src/rfd_core/__init__.py` | Public API surface |
| `packages/rfd-core/src/rfd_core/py.typed` | PEP 561 marker |
| `packages/rfd-core/tests/test_*.py` (10 files) | 157 tests, including a dedicated Hypothesis property suite |

**10 source modules, 405 statements, 10 test files, 157 tests, 100% coverage.**

---

## Verified, Not Just Written

Every claim below was checked by actually running code, not inferred:

- **Full suite passes on real Python 3.9.25** (`uv python install 3.9`), matching the container's
  interpreter exactly — not a newer local Python standing in for it.
- **100% statement coverage**, including two branches that initially looked covered but weren't:
  a cleanup-on-write-failure path (the mock had been failing *before* the temp file even existed)
  and a defense-in-depth "don't let cleanup's own failure mask the original error" branch.
- **Dependency tree confirmed pydantic-only** (`uv pip tree`) — no accidental import of torch, JAX,
  or ColabDesign anywhere in `rfd-core`, satisfying NFR-2 by proof rather than by promise.
- **156/157 tests also pass on Python 3.13** — the one that doesn't is `rfd-core` correctly *refusing*
  to resolve on 3.13 at all, because `requires-python=">=3.9,<3.10"` is intentionally exact.

---

## An Incident, Caught and Fixed Before It Shipped

Running `ruff check --fix` (routine cleanup: import sorting, minor style) silently rewrote every
`Optional[X]` in the source to `X | None` — pyupgrade "modernizing" the syntax. This is invalid at
**runtime** on Python 3.9 for anything pydantic resolves via `eval()`, even under
`from __future__ import annotations`: the `|` operator on types is a 3.10+ runtime feature: import
broke immediately with `TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'`.

This is precisely the constraint domain-entities.md had already documented as a hard rule
("no runtime PEP 604 unions") — the tooling violated a rule the design had explicitly anticipated.

**Caught immediately** because the workflow was "generate, then verify on real 3.9" rather than
"generate and trust." **Fixed properly, not just reverted**:
1. All six affected files restored to `typing.Optional`/`List` throughout.
2. Investigated *why* `target-version = "py39"` didn't prevent it: ruff's `UP045`/`UP007` aren't
   gated by target-version at all — ruff considers the new syntax always safe to *write* once
   `from __future__ import annotations` is active, with no way to know a library will later
   `eval()` that string on an interpreter where `type.__or__` doesn't exist.
3. `UP045`/`UP007` explicitly added to `ruff.lint.ignore` in `packages/rfd-core/pyproject.toml`,
   with a comment explaining why — so this cannot silently recur, and so a future contributor
   sees the reason before removing the ignore.
4. Full suite re-verified on real 3.9 afterward, twice (once after the manual revert, once after
   re-running `ruff check --fix` with the corrected config to confirm only cosmetic fixes applied).

---

## Design Decisions Made During Generation

- **`ContigSpec.parse` raises directly**; `DesignRequest`-level validation aggregates into
  `ValidationOutcome`. Matches the layering domain-entities.md specified: a single-responsibility
  parser raises on its one failure mode, while multi-field validation collects everything at once.
- **The `"0"`-segment rejection and `mpnn_sampling_temp==0` warning-not-error** are implemented
  exactly as business-rules.md specified, with tests asserting the distinction explicitly (not just
  that validation runs, but that a warning doesn't block while an error does).
- **`get_Ls` operates on already-normalised contigs only** — its docstring states this explicitly,
  since feeding it raw user input (pre-`ContigNormaliser`) would silently produce wrong numbers
  rather than erroring, given its simpler single-dash-per-segment assumption.

---

## Requirements Satisfied

| Req | Evidence |
|---|---|
| FR-4 (mode preview) | `preview_mode()`, tested to never raise |
| FR-5 (validation) | `validate()`, full rule-table coverage in `test_validation.py` |
| FR-12 (preserved logic) | Every function docstring cites the exact notebook line range it transcribes |
| NFR-1 (uv-managed) | Root workspace `pyproject.toml` |
| NFR-2 (no heavy deps) | `uv pip tree` output: pydantic only |
| NFR-6 (configurable paths) | `PathLayout.from_env`, tested with overrides |
| NFR-9 (documented deviations) | `"0"`-segment rejection and TD-11 fix both documented in code and tests |
| NFR-11 (argv, no shell) | `build_inference_argv` returns a list; property-tested for no quote-wrapping artifacts |
| NFR-17 (property-tested) | `test_properties.py`, 5 Hypothesis properties targeting the highest-value logic |

---

## Next

- **U2b Runner** — depends on U2a (this unit) and U1 (the container, awaiting Grex GPU availability)
- **Milestone M1** — needs both U1 verification (pending) and U2b
