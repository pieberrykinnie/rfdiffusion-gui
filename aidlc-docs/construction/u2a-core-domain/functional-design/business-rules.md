# U2a Core Domain — Business Rules

Resolved decisions from `u2a-functional-design-plan.md`:
**Q1 = no numeric ceiling** (positivity floor retained — see §0) · **Q2 = symmetry order capped at
12** · **Q3 = hotspot/chain cross-validation deferred**.

---

## 0. Interpretation of "no constraint" (Q1)

"No constraint" removes the **upper ceiling** the notebook's Colab dropdowns implied. It does not
remove the **positivity floor**: a value that is physically meaningless (`iterations=0`,
`num_designs=-1`) is rejected regardless, because G-9 requires that no job is ever queued only to
fail on input that could never have worked. This is stated explicitly because "no constraint" could
otherwise be read either way.

---

## 1. Validation Rules — `DesignRequest`

All ranges are **floors only** unless marked with a ceiling (order, per Q2).

| Field | Rule | Rationale |
|---|---|---|
| `name` | non-empty, printable, no path separators (`/`, `\`) | becomes part of a filesystem path (FR-7) |
| `contigs` | must parse per `ContigSpec` grammar; no `"0"`-length segments (§2 below) | correctness |
| `pdb` | non-empty when mode is `fixed` or `partial` (post-parse); otherwise optional | mode requires a template |
| `iterations` | integer, **≥ 1** | §0 |
| `hotspot` | optional; if present, non-empty after normalisation (§1.5.3 business-logic-model) | — |
| `num_designs` | integer, **≥ 1** | §0 |
| `symmetry` | one of `none` / `auto` / `cyclic` / `dihedral` | closed enum |
| `order` | integer, **1 ≤ order ≤ 12** | Q2 |
| `chains` | optional; if present, each token is a single uppercase letter | matches notebook's `fixed_chains` filter usage |
| `add_potential` | boolean | — |
| `partial_T` | `"auto"` or an integer string, **≥ 1** if numeric | fixes TD-11 |
| `use_beta_model` | boolean | — |
| `live_preview` | boolean | DD-7 |
| `num_seqs` | integer, **≥ 1** | §0 |
| `mpnn_sampling_temp` | float, **> 0** | a temperature of 0 is degenerate (deterministic argmax, not an error, but flagged as a warning — see §3) |
| `rm_aa` | optional string; if present, comma-separated single-letter amino acid codes | — |
| `use_soluble_mpnn` | boolean | — |
| `initial_guess` | boolean | — |
| `num_recycles` | integer, **≥ 0** (0 is valid — "no recycling", a real AlphaFold setting) | — |
| `use_multimer` | boolean | — |
| `partition`, `account`, `walltime`, `gpus`, `cpus_per_task`, `mem_per_cpu` | **out of scope for `rfd-core`** — Slurm submission parameters validated in U3 against runtime-discovered partition data (FR-6a) | this unit has no Slurm knowledge |

## 2. Contig-Specific Rules

| Rule | Detail |
|---|---|
| No empty segments | A `"/"`-separated segment must be non-empty (`""` between two slashes, e.g. `"40//40"`, is rejected — the notebook would raise an unhandled `IndexError` on `a[0]`; `rfd-core` rejects it with a clear message instead) |
| No `"0"`-length free segments | Deliberate deviation from silent-drop (business-logic-model.md §1.4) |
| No `"0"` lower bound in a free range | `"0-10"` rejected for the same reason — prevents RFdiffusion from ever receiving a sampled zero-length insert |
| Fixed-segment chain letter must be a single alphabetic character | `a[0]` per the grammar; multi-letter chain IDs are not supported by RFdiffusion's contig format and were never supported by the notebook either |
| At least one token, or the input is empty | Empty string is valid input (→ `partial` mode, "noise everything"); a non-empty string that parses to zero tokens is not reachable given the grammar, so no separate rule is needed |

## 3. Warnings vs. Errors

`ValidationOutcome` (C-26) distinguishes the two: **errors** block submission; **warnings** are shown
but do not block, matching the spirit of "validate what would definitely fail, without being more
restrictive than the notebook was."

| Condition | Severity | Reason |
|---|---|---|
| `mpnn_sampling_temp == 0` | Warning | Valid but unusual (fully deterministic sampling) |
| `symmetry != none` and `chains` set but doesn't include any fixed-segment chain letter | Warning | Likely a typo, but not provably wrong without the template |
| `use_multimer` true but `num_designs` very large | Warning | Multimer AlphaFold is slower; purely advisory |
| Anything in §1/§2 | Error | Provably invalid regardless of template contents |

## 4. Deferred Validation (Q3)

**Not implemented in `rfd-core`**, and not implemented anywhere in v1 per the Q3 answer:

- Hotspot residues existing in the template
- `chains` filter matching chains actually present in the template
- Fixed-segment ranges (e.g. `A163-181`) existing within the template's actual residue numbering

These require a parsed PDB. If wrong, the job fails inside RFdiffusion with its own error message,
surfaced to the user via FR-19 (log tail). This exactly matches notebook behaviour — no regression,
just no improvement here either, which is the point of deferring rather than silently degrading scope
elsewhere.

## 5. Symmetry Order Ceiling (Q2)

`order` is validated to **1–12 inclusive** for `cyclic` and `dihedral`. This is **stricter** than the
real chain-letter-exhaustion limit (26 dihedral / 52 cyclic, from `fix_pdb`'s 52-letter alphabet) —
deliberately: nothing scientific is gained above 12-fold symmetry, and capping here means the
chain-letter-exhaustion failure mode can never be reached in practice, so `rfd-runner` (U2b) does not
need to guard against it either.

## 6. `SymmetryPlan` / AnAnaS Availability (carried from U1 finding)

`SymmetryResolver.resolve(AUTO, ...)` always returns `deferred=True` — `rfd-core` has no way to know
at validation time whether the `ananas` binary is staged. **U4's responsibility**: query U3/deployment
config for AnAnaS availability and disable the `auto` option in the form when absent, with an
explanatory note (per the U1-finding requirement impact already recorded in `aidlc-state.md`).
**U2b's responsibility**: if `auto` is somehow still requested without the binary, fail with a clear,
actionable error — never a bare exception, never a silent fallback to `none`.

## 7. Error Taxonomy

| Error type | When raised | Consumer |
|---|---|---|
| `ValidationOutcome(ok=False, errors=[...])` | Any §1/§2 rule violated | Web form (FR-5) — rendered inline, submission blocked |
| `ValueError` from `plan_iterations` | Only reachable if called with a `DesignRequest` that skipped validation (programmer error) | Internal — should never surface to a user in practice |
| No exception path for "no symmetry detected" | Matches notebook: this is an expected outcome of `auto`, not a failure | `SymmetryPlan` with `group=None, copies=1` |

**Principle** (recorded in Application Design, restated here for this unit specifically): errors a
user needs to see and act on are **values** (`ValidationOutcome`); exceptions are reserved for states
that indicate a bug in the calling code, not bad user input.
