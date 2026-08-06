# U2a Core Domain — Business Logic Model

Every algorithm below is transcribed from `reference/diffusion.py` (behaviour-preserving, FR-12,
NFR-9), with the exact source lines cited, and cross-checked against the pinned ColabDesign commit
(`e31a56fe1d9b4de25c8697f3a28b75892941cc72`) where the notebook calls into it. Deliberate deviations
are called out explicitly.

---

## 1. Contig Grammar (`ContigSpec`)

**Source**: `reference/diffusion.py` lines 251, 255–262 (splitting) and the `fix_contig`/
`fix_partial_contigs` free/fixed segment grammar in ColabDesign (which `rfd-core` must parse
identically, even though normalisation itself runs in U2b).

### 1.1 Tokenisation

```
raw contigs string
  → replace "," and ":" with " "
  → split on whitespace
  → list of "chain tokens"
```

Each **chain token** becomes one element of the final `contigmap.contigs=[...]` list — i.e. one
output chain. A chain token is further split on `"/"` into **segments**, which are concatenated
within that one output chain (e.g. `"40/A163-181/40"` is a *single* chain: 40 free residues, then a
fixed motif from template chain A, then 40 more free residues).

### 1.2 Segment classification

For a segment `x`, take `a = x.split("-")[0]`:

| Condition | Classification | Example |
|---|---|---|
| `a` is non-empty and `a[0]` is alphabetic | **Fixed** — references template chain `a[0]` | `A163-181`, `A-181`, `A33-`, `A` |
| `a` is non-empty and `a.isnumeric()` | **Free** — a length or the start of a length range | `40`, `50-100` |
| `a` is empty (segment is `""` or starts with `"-"`) | **Invalid** | `""`, `-40` |

A chain token is:
- **all-fixed** if every segment is fixed
- **all-free** if every segment is free
- **mixed** if it contains both (this is normal — it's how motif scaffolding expresses "free / fixed
  motif / free" in one chain)

### 1.3 Fixed-segment sub-grammar (needed for `fixed_chains` extraction only — full range parsing is
U2b's job via `fix_contigs`)

| Form | Meaning |
|---|---|
| `C` | Chain `C`, entire range (open both ends) |
| `C-N` | Chain `C`, residues up to `N` (open start) |
| `CN-` | Chain `C`, residues from `N` onward (open end) |
| `CN1-N2` | Chain `C`, residues `N1..N2` |
| `CN` | Chain `C`, single residue `N` |

`ContigSpec` extracts the **chain letter only** (`a[0]`) for each fixed segment — full range
resolution against a real template requires `parsed_pdb` and is U2b's `ContigNormaliser` (C-13).

### 1.4 Free-segment sub-grammar

| Form | Meaning |
|---|---|
| `N` | Exact length `N` |
| `N1-N2` | Sample a length uniformly from `N1..N2` inclusive (resolved in U2b, at normalisation time — the *value itself* is randomised then, not in `rfd-core`) |

**Deliberate deviation (documented, NFR-9)**: the notebook's ColabDesign `fix_contig` silently
**drops** a free segment that is the literal string `"0"` (the condition `x.isnumeric() and x != "0"`
excludes it). `rfd-core` instead **rejects** `"0"` — and, by the same reasoning, any free-range whose
lower bound is `0` (e.g. `"0-10"`) — as invalid input with a clear message, rather than reproducing a
silent no-op segment that could confuse RFdiffusion downstream. The set of inputs a user would
*intend* to submit is unchanged; only the failure mode moves from "silently wrong" to "clearly
rejected before submission" (G-9).

---

## 2. Design Mode Inference (`DesignModeInferrer`)

**Source**: `reference/diffusion.py` lines 252–268. **The single highest-value function carried over
from the notebook** — it lets the user never have to pick a protocol explicitly.

```
is_fixed = False; is_free = False; fixed_chains = []
for each chain token:
    for each segment:
        classify (§1.2)
        if fixed: is_fixed = True; record chain letter (deduplicated, order of first appearance)
        if free:  is_free = True

if len(chain tokens) == 0 or not is_free:
    mode = PARTIAL
elif is_fixed:
    mode = FIXED
else:
    mode = FREE
```

**Behaviour table** (matches the notebook's documented examples exactly):

| Input | Tokens | is_fixed | is_free | Mode |
|---|---|---|---|---|
| `""` | none | — | — | `partial` |
| `"100"` | 1 | No | Yes | `free` |
| `"50:100"` | 2 | No | Yes | `free` |
| `"50"` + `symmetry=cyclic` | 1 | No | Yes | `free` (symmetry replication happens later, §3) |
| `"A:50"` | 2 | Yes | Yes | `fixed` |
| `"40/A163-181/40"` | 1 | Yes | Yes | `fixed` |
| `"A1-10"` | 1 | Yes | No | `partial` |
| `"A"` | 1 | Yes | No | `partial` |

Note the last two rows: a token containing **only** fixed segments (no free segment anywhere in the
*entire* input) still yields `partial`, even though `is_fixed` is `True` — this is exactly what makes
partial diffusion ("keep this fixed, noise the rest") distinct from motif scaffolding ("keep this
fixed, diffuse *this much new sequence* around it"). The rule is `not is_free`, checked globally
across all tokens, not per-token.

---

## 3. Symmetry Resolution (`SymmetryResolver`)

**Source**: `reference/diffusion.py` lines 240–248, 280–289, 319–327.

```
resolve(kind, order, add_potential):
    match kind:
        NONE:     → group=None,      copies=1,        deferred=False
        CYCLIC:   → group=f"c{order}", copies=order,     deferred=False
        DIHEDRAL: → group=f"d{order}", copies=2*order,    deferred=False
        AUTO:     → group=None,      copies=1,        deferred=True   # resolved by U2b via AnAnaS
```

**Deferred resolution** (U2b, after AnAnaS runs — logic specified here so both sides implement the
same rule): AnAnaS returns a detected group string like `"c3"` or `"d2"`.

```
apply_detected_group(plan, detected):
    if detected[0] == "c":  group=detected, copies=int(detected[1:])
    elif detected[0] == "d": group=detected, copies=2*int(detected[1:])
    else: FAIL — "detected symmetry not supported" (notebook: prints error, disables symmetry;
                 rfd-core: returns a structured error instead — U2b decides mode-continuation policy)
    if AnAnaS unavailable or detects nothing: plan reverts to group=None, copies=1
      (matches notebook's "ERROR: no symmetry detected" → symmetry disabled, run continues unsymmetric)
```

**`add_potential`** only has an effect when `group is not None`. It appends four fixed Hydra
overrides (guiding potentials) — a static list, not computed logic; specified in §5.

**Copy replication**: once `copies > 1`, the *entire normalised contig list* (all chain tokens,
produced by U2b) is replicated `copies` times (`contigs = sum([contigs] * copies, [])`, line 327).
This is a U2b-time operation on normalised contigs, but the **copy count itself** is `rfd-core`'s
output (`SymmetryPlan.copies`).

---

## 4. Iteration Planning (`IterationPlanner`)

**Source**: `reference/diffusion.py` lines 300–309.

```
plan_iterations(mode, iterations, partial_T):
    if mode == PARTIAL:
        if partial_T == "auto":
            steps = int(80 * (iterations / 200))
        else:
            steps = int(partial_T)   # raises ValueError if non-numeric — VALIDATED, not silently caught
        hydra_key = "diffuser.partial_T"
    else:  # FREE or FIXED
        steps = iterations
        hydra_key = "diffuser.T"
    return IterationPlan(steps, hydra_key)
```

**Deliberate deviation (documented, NFR-9, fixes TD-11)**: the notebook lets `int(partial_T)` raise an
unhandled `ValueError` deep inside `run_diffusion`. `rfd-core` validates `partial_T` **before**
constructing the plan (via `DesignRequest` — §6 in `business-rules.md`), so a non-numeric value is
rejected at the web form, not mid-job.

**Worked example** (from the notebook's own default): `iterations=200`, `partial_T="auto"` →
`steps = int(80 * (200/200)) = 80`. At `iterations=50` (the UI default) → `int(80 * 0.25) = 20`.

---

## 5. Inference Argument-List Assembly (`InferenceArgvBuilder`)

**Source**: `reference/diffusion.py` lines 234–235, 299, 305/308/311, 315–330, 331–332.
**Deliberate deviation (NFR-11, fixes TD-7)**: the notebook builds a single shell string
(`opts_str = " ".join(opts)`) and interpolates it into `os.system(cmd)`. `rfd-core` builds a **list**
of argv tokens, one override per element, for direct `subprocess` execution with no shell.

### 5.1 Fixed/always-present overrides

```
inference.output_prefix={output_prefix}
inference.num_designs={num_designs}
```

### 5.2 Conditional overrides, in the notebook's exact order

| Condition | Overrides appended | Source line |
|---|---|---|
| mode is `fixed` or `partial` | `inference.input_pdb={input_pdb}` | 299 |
| mode is `partial` | `diffuser.partial_T={steps}` | 305 |
| mode is `free` or `fixed` | `diffuser.T={steps}` | 308, 311 |
| `hotspot` non-empty | `ppi.hotspot_res='[{csv}]'` — see §5.3 for hotspot formatting | 315–317 |
| `inference.dump_pdb=True` | always | 330 |
| `inference.dump_pdb_path={dump_path}` | always — **U2b passes `$TMPDIR`-derived path, not `/dev/shm`** (G-11) | 330 |
| `use_beta_model` | `inference.ckpt_override_path={beta_ckpt_path}` | 332 |

### 5.3 Hotspot formatting

**Source**: line 316: `hotspot = ",".join(hotspot.replace(","," ").split())`.

Normalises any mix of comma/space-separated residues to a single comma-joined string:
`"E64, E88  E96"` → `"E64,E88,E96"`. Empty or whitespace-only input is treated as absent (matches
`hotspot != ""` guard at line 315).

### 5.4 Symmetry prefix (prepended, not appended)

**Source**: lines 320–326. When `SymmetryPlan.group is not None`:

```
prepend: --config-name symmetry
prepend: inference.symmetry={group}
if add_potential:
    prepend (in this order):
        potentials.guiding_potentials=["type:olig_contacts,weight_intra:1,weight_inter:0.1"]
        potentials.olig_intra_all=True
        potentials.olig_inter_all=True
        potentials.guide_scale=2
        potentials.guide_decay=quadratic
```

These are **static strings** — no computed values — copied verbatim from the notebook. As argv
elements (not shell tokens), the nested quoting the notebook needed
(`'potentials.guiding_potentials=["...]'`) is **not needed**: each override is one argv element,
passed to `subprocess` unquoted-but-whole. This is a direct, positive consequence of NFR-11 — an
entire category of quoting bugs disappears.

### 5.5 Final ordering

`[symmetry prefix (if any)] + [output_prefix, num_designs] + [input_pdb?] + [T or partial_T] +
[hotspot?] + [dump_pdb, dump_pdb_path] + [ckpt_override?] + [contigmap.contigs]`

`contigmap.contigs` itself is appended last by the caller (U2b), since its value is the
**normalised** contig list, which only exists after `ContigNormaliser` (U2b) runs.

---

## 6. Chain-Length Extraction (`get_Ls`) — added to `rfd-core` scope

**Source**: ColabDesign `colabdesign/rf/utils.py::get_Ls`, pinned commit `e31a56fe`.

```
get_Ls(normalised_contigs) -> list[int]:
    for each contig (already normalised — every segment is "X-Y" form):
        L = sum over "/"-separated sub-segments of:
            (Y - int(X[1:]) + 1)  if X[0] is alphabetic (fixed range)
            else Y                 (free range, already resolved to an exact "N-N")
        append L
    return list of per-chain lengths
```

Pure arithmetic over **already-normalised** contigs (produced by U2b). Needed by U4 (FR-22, chain
colouring) and requires no PDB access — hence its addition to `rfd-core` rather than `rfd-runner`.

---

## 7. Traceability

| `rfd-core` component | Notebook source | ColabDesign function referenced (not called) |
|---|---|---|
| `ContigSpec` (§1) | lines 251, 255–262 | `fix_contig`, `fix_partial_contigs` grammar |
| `DesignModeInferrer` (§2) | lines 252–268 | — |
| `SymmetryResolver` (§3) | lines 240–248, 280–289, 319–327 | — |
| `IterationPlanner` (§4) | lines 300–309 | — |
| `InferenceArgvBuilder` (§5) | lines 234–332 | — |
| `get_Ls` (§6) | line 448 (`Ls = get_Ls(contigs)`) | `get_Ls` (behaviour reproduced exactly) |
