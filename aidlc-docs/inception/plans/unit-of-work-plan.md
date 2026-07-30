# Unit of Work Plan

**Stage**: INCEPTION — Units Generation, Part 1 (Planning)
**Depth**: Lean
**Date**: 2026-07-31

---

## Context

Most of this decomposition is **already settled** by two approved stages:

- **Execution plan** approved four units — U1 Runtime and Container, U2 Core Domain and Runner,
  U3 Slurm Integration and Persistence, U4 Web Application — with the critical path U1 → U2 → U3 → U4
  and U1's *validation* deliberately overlapped onto U2's development window.
- **Application design** fixed the package layout (`rfd-core`, `rfd-runner`, `rfd-web`), all 29
  components, 4 services, and the directory structure.

So this stage mostly **records** the decomposition rather than deciding it. Three questions below are
genuinely open, and one affects the critical path.

**Note on the story map**: User Stories was skipped, so there are no stories to map. The
`unit-of-work-story-map.md` artifact will instead map **requirements** (FR / NFR / G-rules) to units —
same purpose, same traceability, using the artifacts that actually exist. Question 3 confirms this.

---

## Plan Steps

### Part 1 — Planning
- [x] Load requirements, execution plan, and application design artifacts
- [x] Identify genuinely open decomposition questions
- [x] User answers the 3 questions below — **Q1 = A, Q2 = A, Q3 = A** (2026-07-31)
- [x] Analyze answers for vagueness, contradiction, or missing detail — all unambiguous letter
      choices, mutually consistent, no follow-up required
- [x] Raise follow-up questions if any ambiguity remains — none needed
- [x] Obtain approval to proceed to generation — answers constitute approval of the plan as written

### Part 2 — Generation
- [x] Generate `unit-of-work.md` — unit definitions, responsibilities, scope, deliverables, code
      organization strategy
- [x] Generate `unit-of-work-dependency.md` — dependency matrix, build order, parallelisation,
      coordination points
- [x] Generate `unit-of-work-story-map.md` — requirement-to-unit traceability (per Q3)
- [x] Validate unit boundaries and dependencies
- [x] Verify every FR, NFR, and G-rule is assigned to an owning unit

## Resolved Decisions
- **Q1 = A** — U2 split into **U2a `rfd-core`** (pure domain) and **U2b `rfd-runner`** (in-job
  pipeline). **Five units total.** U2a has no dependency on U1 and completes in parallel with the
  container build.
- **Q2 = A** — explicit **milestone M1 "working CLI pipeline"** after U1 + U2a + U2b, verified by
  submitting one real `sbatch` job by hand before any web code is written.
- **Q3 = A** — `unit-of-work-story-map.md` carries **requirement-to-unit traceability** (FR / NFR /
  G-rules), since User Stories was skipped.

---

## Decomposition Questions

### Question 1 — Should U2 be split into two units?

This is the one question that affects the critical path.

**U2 as currently approved bundles two things with very different testing needs:**

| | `rfd-core` | `rfd-runner` |
|---|---|---|
| Dependencies | pure Python | torch, CUDA, ColabDesign, RFdiffusion |
| Testable | **immediately, on any machine** | only inside the working container |
| Blocked by U1? | **no** | yes |

Bundled, U2 cannot be declared *done* until the container works — which couples the project's most
testable code to its riskiest dependency. Split, `rfd-core` can be fully built and property-tested
while the image is still building, and it is exactly the code that most benefits from early tests
(mode inference, Hydra flag assembly).

A) **Split into U2a `rfd-core` (pure domain) and U2b `rfd-runner` (in-job pipeline).** U2a has zero dependency on U1 and can complete entirely in parallel with the container build. Five units total. *(Recommended — this is the sharpest available version of the overlap strategy the execution plan already committed to, and it makes the highest-value logic completable on day one.)*

B) **Keep U2 as one unit.** Fewer moving parts and one less handoff, but U2's completion is gated on the container even though most of its code does not need it.

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

### Question 2 — Should there be an explicit CLI milestone before the web UI?

After U1 and U2, you would have a container plus a runner that can execute the full pipeline from a
job script — a working command-line tool, with no web interface. The execution plan already notes
this as a rollback property; the question is whether to make it a **deliberate checkpoint**.

A) **Yes — treat "working CLI pipeline" as an explicit milestone**, verified by submitting one real `sbatch` job by hand before any web code is written. Proves the container, the runner, the Grex job script, and the scientific pipeline all work while the surface area is still small. If something is wrong with the GPU stack or the job script, you find out here rather than through a web form. Costs one extra verification step. *(Recommended — it front-loads the failure modes that are hardest to diagnose later, and it produces something immediately useful even if the web work stalls.)*

B) **No — go straight through to the web UI** and do the first real end-to-end test through the browser. Fewer checkpoints, but a failure then has four candidate causes instead of one.

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

### Question 3 — Traceability artifact in place of a story map

User Stories was skipped, so `unit-of-work-story-map.md` has no stories to map. What should it
contain?

A) **Requirement-to-unit traceability** — map every FR, NFR, and G-rule to its owning unit, so each unit has an explicit, checkable scope and no requirement is orphaned. *(Recommended — preserves the artifact's actual purpose using what we have.)*

B) **Business-transaction-to-unit mapping** — map the 7 business transactions (BT-1 … BT-7) from reverse engineering to units. Coarser, but closer in spirit to a story map.

C) **Both** — requirements for completeness, business transactions for readability.

X) Other (please describe after [Answer]: tag below)

[Answer]:

---

## Anything else?

If any unit boundary, ownership question, or sequencing preference matters that I have not asked
about, describe it here.

[Answer]:
