# API Documentation

## REST APIs

**None.** The existing code exposes no HTTP surface of any kind. There is no server, no routing, no request handling. All interaction is through Colab's notebook form widgets and the global Python namespace.

This section exists to record that fact explicitly: the web API is entirely **new construction**, not a port.

## Internal APIs

These are the de facto interfaces of the notebook — the contracts that a ported application must preserve.

### `run_diffusion(...)` — primary domain entry point

```python
run_diffusion(contigs, path, pdb=None, iterations=50,
              symmetry="none", order=1, hotspot=None,
              chains=None, add_potential=False, partial_T="auto",
              num_designs=1, use_beta_model=False, visual="none")
      -> tuple[list[str], int]
```

| Parameter | Type | Default | Description | Validation in code |
|---|---|---|---|---|
| `contigs` | `str` | required | Chain/segment spec, e.g. `"100"`, `"A:50"`, `"40/A163-181/40"`. Split on `,` `:` whitespace, then `/`. | none |
| `path` | `str` | required | Output name under `outputs/`. | none |
| `pdb` | `str \| None` | `None` | PDB code, UniProt ID, local path, or `""` for upload. | none |
| `iterations` | `int` | `50` | Diffusion timesteps (T). Form offers 25/50/100/150/200. | none |
| `symmetry` | `str` | `"none"` | `none` \| `auto` \| `cyclic` \| `dihedral`. Anything unrecognised silently becomes `None`. | implicit |
| `order` | `int` | `1` | N for cyclic/dihedral. Form offers 1–12. | none |
| `hotspot` | `str \| None` | `None` | Comma/space separated residues, e.g. `"E64,E88,E96"`. | none |
| `chains` | `str \| None` | `None` | Chain filter for the template, e.g. `"A,B"`. `""` coerced to `None`. | line 237 |
| `add_potential` | `bool` | `False` | Add oligomer-contact guiding potentials (symmetry only). | none |
| `partial_T` | `str \| int` | `"auto"` | Noising steps for partial diffusion. `"auto"` ⇒ `int(80 * iterations/200)`. | none |
| `num_designs` | `int` | `1` | Designs to generate. Form offers 1/2/4/8/16/32. | none |
| `use_beta_model` | `bool` | `False` | Use `Complex_beta_ckpt.pt`. | none |
| `visual` | `str` | `"none"` | `none` \| `image` \| `interactive` — live rendering mode. | implicit |

**Returns**: `(contigs, copies)` where `contigs` is the *normalised, symmetry-replicated* list of contig strings and `copies` is the chain-copy count. **Both are required by downstream cells** (Cell 3 for `get_Ls`/chain colouring, Cell 4 for `--contig` and `--copies`).

**Side effects**: creates `outputs/{path}/`; writes `outputs/{path}/input.pdb`; runs inference; rewrites `outputs/{path}_{n}.pdb` and both trajectory files in place through `fix_pdb`; prints `mode`, `output`, `contigs`, and the full command to stdout.

**Derived value — design mode** (not a parameter; inferred):

| Condition | Mode |
|---|---|
| no contigs, or no free (numeric) segment | `partial` |
| has free segment AND has fixed (alphabetic) segment | `fixed` |
| has free segment only | `free` |

### `run(command, steps, num_designs=1, visual="none") -> None`

Launches `command` via `nohup`, polls `/dev/shm/{n}.pdb` for `n in range(steps)` once per design, drives an `ipywidgets.FloatProgress`, optionally renders each step, and blocks until the process exits. Sets the bar to `danger`/`"failed"` if the process dies mid-run, or `danger`/`"stopped"` on `KeyboardInterrupt` (after SIGTERM).

**Contract note**: the caller must pass a `steps` value that exactly matches the number of dumps RFdiffusion will produce, and `num_designs` must match `inference.num_designs`. Mismatch causes a silent hang or premature return.

### `get_pdb(pdb_code=None) -> str`

Resolution order: `None`/`""` ⇒ browser upload, written to `tmp.pdb`; existing file path ⇒ returned unchanged; length 4 ⇒ RCSB `{code}.pdb1`; otherwise ⇒ AlphaFold DB `AF-{id}-F1-model_v3.pdb`. Returns the local path. Caches by file existence (`wget -qnc`).

### `run_ananas(pdb_str, path, sym=None) -> tuple[dict | None, str]`

Writes `outputs/{path}/ananas_input.pdb`, runs `./ananas {in} -u -j {out} [sym]`, parses the JSON. On success returns `(results, asymmetric_unit_pdb_str)` where `results` carries `group`, `Average_RMSD`, and `transforms`. On **any** exception returns `(None, pdb_str)` unchanged.

### `plot_pdb(num=0)` — Cell 3 version

Renders `outputs/traj/{path}_{num}_pX0_traj.pdb` (or `_Xt-1_` when `denoise=False`). Reads globals `denoise`, `animate`, `color`, `dpi`, `path`, `contigs`. Modes: `animate="none"` ⇒ final structure; `"interactive"` ⇒ py3Dmol frame animation; `"movie"` ⇒ matplotlib GIF via `make_animation`.

### `plot_pdb(num="best")` — Cell 5 version (shadows the above)

Overlays `outputs/{path}_{num}.pdb` with `outputs/{path}/best_design{num}.pdb`. When `num == "best"`, the design index is read from field 3 of the `REMARK 001 design {m} N {n} RMSD {rmsd}` first line of `outputs/{path}/best.pdb`.

## External Command-Line Contracts

### `RFdiffusion/run_inference.py` (Hydra)

Overrides emitted by `run_diffusion`:

| Override | When |
|---|---|
| `inference.output_prefix=outputs/{path}` | always |
| `inference.num_designs={n}` | always |
| `inference.input_pdb={file}` | modes `fixed`, `partial` |
| `diffuser.T={iterations}` | modes `free`, `fixed` |
| `diffuser.partial_T={iterations}` | mode `partial` |
| `contigmap.contigs=[{space-separated}]` | always |
| `ppi.hotspot_res='[{csv}]'` | hotspot non-empty |
| `--config-name symmetry`, `inference.symmetry={cN\|dN}` | symmetry active (prepended) |
| `potentials.guiding_potentials=["type:olig_contacts,weight_intra:1,weight_inter:0.1"]`, `potentials.olig_intra_all=True`, `potentials.olig_inter_all=True`, `potentials.guide_scale=2`, `potentials.guide_decay=quadratic` | symmetry active AND `add_potential` |
| `inference.dump_pdb=True`, `inference.dump_pdb_path='/dev/shm'` | always |
| `inference.ckpt_override_path=./RFdiffusion/models/Complex_beta_ckpt.pt` | `use_beta_model` |

### `colabdesign/rf/designability_test.py` (Cell 4)

| Flag | Source |
|---|---|
| `--pdb=outputs/{path}_0.pdb` | first design |
| `--loc=outputs/{path}` | output location |
| `--contig={":".join(contigs)}` | from `run_diffusion` return |
| `--copies={copies}` | from `run_diffusion` return |
| `--num_seqs`, `--mpnn_sampling_temp`, `--rm_aa` | ProteinMPNN settings |
| `--num_recycles`, `--num_designs` | AlphaFold / batch settings |
| `--initial_guess`, `--use_multimer`, `--use_soluble` | boolean flags, appended when true |

### `./ananas`

`./ananas {input.pdb} -u -j {output.json} [{group}]` — `-u` requests the asymmetric unit, `-j` writes JSON.

## Data Models

There are **no declared data models** — no dataclasses, TypedDicts, Pydantic models, or schemas. The following are implicit structures the port will need to formalise.

### Design Request (implicit — the `flags` dict, Cell 2 lines 389–401)
- **Fields**: `contigs`, `pdb`, `order`, `iterations`, `symmetry`, `hotspot`, `path`, `chains`, `add_potential`, `num_designs`, `use_beta_model`, `visual`, `partial_T`.
- **Validation**: only quote-stripping on string fields (lines 403–405).

### Run Context (implicit — Python globals shared across cells)
- **Fields**: `path` (str), `contigs` (list[str], normalised), `copies` (int), `num_designs` (int).
- **Relationships**: produced by Cell 2 / `run_diffusion`; consumed by Cells 3, 4, 5, 6.
- **Note**: This is the state that a web application must persist per-run. It is the crux of the port.

### AnAnaS Result (implicit — parsed JSON)
- **Fields**: `group` (e.g. `"c3"`), `Average_RMSD` (float), `transforms[].CENTER` (3-vector), `transforms[].AXIS` (3-vector); plus `AU.group` and `AU["chain names"]` from the last element.

### Designability Result (implicit — file conventions)
- `outputs/{path}/best.pdb` — first line `REMARK 001 design {m} N {n} RMSD {rmsd}`.
- `outputs/{path}/best_design{num}.pdb` — AlphaFold prediction, pLDDT in B-factor column.
- `outputs/{path}_{n}.pdb` — RFdiffusion backbone, B-factor used for confidence colouring in range 0.5–0.9.

### Output File Layout
```
outputs/
  {path}_{n}.pdb              final backbone for design n
  {path}/
    input.pdb                 normalised template
    ananas_input.pdb          symmetry detector input
    ananas.json               symmetry detector output
    best.pdb                  best design pointer + score
    best_design{n}.pdb        AlphaFold prediction
  traj/
    {path}_{n}_pX0_traj.pdb   predicted-final-structure trajectory
    {path}_{n}_Xt-1_traj.pdb  noised-state trajectory
{path}.result.zip             export bundle
/dev/shm/{step}.pdb           transient per-step dump (consumed and deleted)
```
