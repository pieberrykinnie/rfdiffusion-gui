# U2a Core Domain — Functional Design Plan

**Unit**: U2a Core Domain (`rfd-core`)
**Stage**: CONSTRUCTION — Functional Design
**Date**: 2026-08-01
**Runs in parallel with**: U1 build/verify on Grex (per execution-plan.md §2 — this is exactly the
overlap the sequencing was designed for)

---

## Unit Context

**Scope** (from `unit-of-work.md`): C-1…C-10 — `ContigSpec`, `DesignModeInferrer`,
`SymmetryResolver`, `IterationPlanner`, `InferenceArgvBuilder`, `DesignRequest`, `RunRecord`,
`ProgressState`, `AtomicJsonStore`, `PathLayout`. Pure Python, **Python 3.9-compatible** (constraint
from U1: the container's interpreter is 3.9, and `rfd-core` runs inside it).

**Requirements owned**: FR-4, FR-5, FR-12 (mode/symmetry/iteration logic), NFR-1, NFR-2, NFR-6,
NFR-9, NFR-11 (argv, not shell strings), NFR-17 (property-testable).

**Not in scope**: anything touching a parsed PDB, ColabDesign, or the filesystem beyond `run.json`/
`progress.json` I/O. That is U2b.

---

## Research Completed Before This Plan

Read the exact source of the four ColabDesign functions the notebook calls, at the pinned commit
(`e31a56fe`), to characterise behaviour precisely rather than from memory:

- **`fix_contigs`** / **`fix_partial_contigs`** (`colabdesign/rf/utils.py`) — both require
  `parsed_pdb`, confirming they belong in **U2b**, not U2a. `rfd-core` only prepares their *inputs*
  (parsed contig segments, inferred mode).
- **`get_Ls(contigs)`** — pure string arithmetic over **normalised** contigs, no PDB needed. Adding
  it to `rfd-core` (it was not explicitly listed in Application Design) since U4 needs it for
  chain-length colouring (FR-22) and it has zero heavy dependencies.
- **A genuine notebook bug found**: in `fix_contig`, a segment that is exactly `"0"` is silently
  **dropped** (`x.isnumeric() and x != "0"` excludes it from output). Decision made without asking:
  `rfd-core`'s validator will **reject a literal `"0"` length segment** as invalid input with a clear
  message, rather than reproducing a silent drop. This is a documented, deliberate behaviour change
  (NFR-9) — the "valid" input space is unchanged, only the failure mode improves.

---

## Plan Steps

- [ ] User answers the 3 questions below
- [ ] Analyze answers for ambiguity; raise follow-ups if needed
- [ ] Generate `business-logic-model.md` — contig parsing, mode inference, symmetry resolution,
      iteration planning, argv assembly, each traced to the exact notebook lines it preserves
- [ ] Generate `business-rules.md` — validation rules, error taxonomy, the "0"-segment decision,
      numeric ranges (pending Q1/Q2), boundary conditions
- [ ] Generate `domain-entities.md` — `DesignRequest`, `RunRecord`, `ProgressState` field-level
      detail, `run.json`/`progress.json` schema and versioning, `ContigSpec`/`Segment` structure

---

## Questions

### Question 1 — Numeric parameter validation: notebook parity or open ranges?

The notebook's Colab form used fixed dropdowns: `iterations` ∈ {25,50,100,150,200}, `num_designs` ∈
{1,2,4,8,16,32}, `num_recycles` ∈ {0,1,2,3,6,12}. That was a Colab UI constraint, not a scientific
one — RFdiffusion itself accepts any positive integer.

A) **Open ranges with sane bounds** (e.g. `iterations` 1–1000, `num_designs` 1–128), enforced as a number input in the web form rather than a dropdown. More flexible, and lets you run values the notebook's dropdown never offered. *(Recommended — you're the only user, and a web number input is not worse UX than a dropdown; no reason to inherit an arbitrary Colab constraint.)*

B) **Reproduce the exact enumerated choices** as dropdowns, matching the notebook precisely. Maximum parity, but a value like `iterations=75` becomes impossible even though RFdiffusion would accept it fine.

C) **Open ranges, but the web form defaults to and highlights the notebook's original choices** as quick-select buttons alongside a free-entry field. More UI work for marginal benefit.

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

### Question 2 — Symmetry order ceiling: keep the notebook's 12, or raise to the real limit?

The notebook's UI capped `order` at 12. The **actual** ceiling comes from chain-letter exhaustion:
`fix_pdb` assigns one letter per chain from a 52-character alphabet (`A-Za-z`), and dihedral symmetry
uses `2 × order` copies. So the true hard limit is `order ≤ 26` for dihedral (52 letters), and higher
still for cyclic (up to 52).

A) **Keep 12** as the validated maximum, matching the notebook exactly. Simple, and 12-fold symmetry already covers essentially all real oligomeric assemblies. *(Recommended — nothing is gained by allowing what nobody needs, and it keeps the "chain letters exhausted" failure mode entirely out of reach.)*

B) **Raise the ceiling to the real limit** (26 dihedral / 52 cyclic), with a validation error only when chain letters would actually run out. More permissive, more edge cases to get right for essentially no scientific benefit.

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

### Question 3 — Hotspot/chain cross-validation: v1 scope or defer?

The notebook never checks that `hotspot` residues or `chains` actually exist in the template or in
the fixed portion of `contigs` — a typo just produces a confusing RFdiffusion error later, inside the
job. `rfd-core` validates syntax (FR-5) but doing *semantic* cross-validation (residue exists in the
parsed PDB) would require the PDB — which means it belongs in U2b/U3, not this pure unit.

A) **Syntax-only validation in `rfd-core` for v1**; defer semantic cross-validation entirely. If a hotspot residue doesn't exist, the job fails with RFdiffusion's own error, surfaced via FR-19's log tail. Matches notebook behaviour, smallest scope. *(Recommended given the ASAP priority — this is exactly the kind of hardening that's easy to add later and costs nothing to defer.)*

B) **Design the validation rule now** (to be implemented in U2b/U3 once a parsed PDB is available), so the contract is specified even though `rfd-core` itself can't enforce it. Slightly more design work now for a smoother implementation later.

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

## Decisions Made Without Asking (documented for review, not blocking)

- **`get_Ls` added to `rfd-core`** — pure, needed by U4, zero new dependencies.
- **Literal `"0"`-length contig segments rejected** at validation, rather than silently dropped as
  the notebook does (a documented, deliberate behaviour change per NFR-9).
- **`run.json`/`progress.json` carry a `schema_version: int` field**, starting at `1`. No migration
  logic needed for v1; this only avoids a harder retrofit later.
- **Errors from `rfd-core` are values, not exceptions**, for anything the web form needs to render
  (`ValidationOutcome`, already sketched in Application Design as C-26's return type). Exceptions are
  reserved for programmer errors (e.g. calling `plan_iterations` with an already-invalid mode).

---

## Anything else?

[Answer]:
