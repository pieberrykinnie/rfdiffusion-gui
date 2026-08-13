# U1 Runtime and Container — Code Summary

**Date**: 2026-07-31 · **Status**: generated, awaiting user execution on Grex

---

## Files

| Path | Status | Purpose |
|---|---|---|
| `containers/rfdiffusion.def` | created | Apptainer definition — Phase 1 image |
| `scripts/preflight-grex.sh` | created (earlier), **fixed** | Cluster assumption checks; quota parsing corrected to read `quota` rather than `df` |
| `scripts/build-image.sh` | created | Image build with login-node refusal and fallback chain |
| `scripts/stage-weights.sh` | created | ~8 GB weight staging, idempotent and resumable |
| `scripts/verify-image.sh` | created | 7-check GPU-node verification |
| `env.example` | created | Every configurable path and Slurm default |
| `docs/setup.md` | created | End-to-end setup (FR-35) |
| `reference/diffusion.py` | **moved** via `git mv`, unmodified | Original notebook (DD-5) |
| `reference/README.md` | created | Provenance, why not to edit, port mapping |
| `.gitignore` | created | Images, weights, runs, caches |

No Python package — U1 produces container definitions, shell scripts, and documentation.

---

## Verified Pins

Every version below was checked against a live source, not assumed.

| Item | Pin | Verified how |
|---|---|---|
| Base image | `rosettacommons/rfdiffusion` | Docker Hub + Dockerfile read |
| CUDA / cuDNN / Python | 11.6.2 / 8 / 3.9 | base Dockerfile |
| torch / DGL / e3nn / hydra | `1.12.1+cu116` / `1.0.2+cu116` / `0.3.3` / `1.3.2` | base Dockerfile |
| `sokrypton/RFdiffusion` | `597d37f2a686e23941440fddf6daa4cb778e7bc7` | GitHub API |
| `sokrypton/ColabDesign` | `e31a56fe1d9b4de25c8697f3a28b75892941cc72` | GitHub API |
| jax / jaxlib | `0.4.25` / `0.4.25+cuda11.cudnn86` | enumerated `jax_cuda_releases.html` — newest CUDA-11 build with cp39 wheels |
| cuDNN supply | `nvidia-cudnn-cu11==8.6.0.163` | PyPI |

The notebook pinned only `e3nn==0.5.5`; everything else floated, including two git installs and
torch/CUDA/JAX entirely (TD-19, TD-21). This closes that gap.

**On e3nn `0.3.3` vs the notebook's `0.5.5`**: the notebook needed 0.5.5 only because Colab's newer
torch required it. On torch 1.12 the inherited `0.3.3` is the *correct* pin, not merely an older one.

---

## Decisions Made During Generation

### cuDNN supplied by pip

jaxlib `cuda11.cudnn86` needs cuDNN ≥ 8.6; the base image carries the 8.4-era runtime. Rather than
wait to hit that at runtime, `nvidia-cudnn-cu11==8.6.0.163` is installed and `LD_LIBRARY_PATH`
prepends it. This removes the most likely cause of the anticipated JAX risk up front.

### ColabDesign installed `--no-deps` with explicit runtime dependencies

Installing ColabDesign normally would let pip resolve its own `jax`, silently undoing the pin. It is
installed `--no-deps` and its real runtime needs (`chex`, `optax`, `dm-haiku`, `immutabledict`,
`joblib`, `py3Dmol`) are installed explicitly.

### Build-time assertion on the fork

`%post` runs `grep -q 'dump_pdb:'` against the fork's config. If the fork ever loses those keys, the
**build** fails rather than a job three hours later. Cheap insurance on the single upstream fact the
live-progress feature depends on.

### Structural validation instead of fabricated checksums

`stage-weights.sh` does **not** ship hardcoded hashes — publishing checksums we had not verified
would be worse than useless. Instead each format validates itself: torch checkpoints are checked for
ZIP magic and a plausible size, `schedules.zip` via `unzip -t`, AlphaFold params via `tar -tf`. That
reliably catches the failure that actually occurs — a truncated download — and a manifest records
what completed so reruns skip it.

### `build-image.sh` refuses to run on a login node

Checks the hostname against `yak`/`bison`/`grex` and requires `SLURM_JOB_ID`. Grex asks users not to
run heavy work on login nodes, and a killed build leaves a corrupt SIF.

### `XLA_PYTHON_CLIENT_PREALLOCATE=false`

JAX preallocates ~75% of GPU memory by default. Torch runs as a sibling subprocess in the same job;
disabling preallocation avoids the two fighting over the card.

---

## Preflight Findings Folded Into the Design

`scripts/preflight-grex.sh` ran clean on `yak` (16 PASS, 0 WARN, 0 FAIL) and returned four results
that changed the design:

1. **Phase 1 is not V100-only.** A30 partitions (`agpu`, `mcordgpu-b`) exist and are **sm_80**, which
   CUDA 11.6 supports. The image reaches **36 V100s + 12 A30s** across five partition families; only
   `lgpu` (L40s, sm_89) is excluded. This narrows Phase 2's value to L40s access alone.
2. **`lgpu` walltime is 3 days, not 7** — contradicting the batch-jobs page. Walltime validation must
   be per-partition from `sinfo` (reinforces FR-6a).
3. **Login-node `python3` is 3.6.8** — `rfd-web` must use a uv-managed standalone Python. Does not
   relax the 3.9 constraint on `rfd-core`, which comes from the container.
4. **Quota is the binding limit, not `df`** — 100 GB soft / 105 GB hard. The preflight script's own
   reporting was corrected to read `quota` instead of `df`, which had overstated headroom as 4.2 TB.

---

## Requirements Satisfied

| Req | Where |
|---|---|
| FR-10 Apptainer `--nv` | `rfdiffusion.def`, `verify-image.sh` |
| FR-35 setup docs | `docs/setup.md` |
| NFR-4 pinned GPU stack + upstream SHAs | `rfdiffusion.def` |
| NFR-5 weights staged once, never at job start | `stage-weights.sh` |
| NFR-6 configurable paths | `env.example` |
| NFR-7 no Colab code paths | no `apt-get`/`aria2c`/`google.colab` anywhere |
| G-15 `module load singularity` | `build-image.sh`, `verify-image.sh` |
| G-16 image pre-built, never pulled at job start | `build-image.sh` |
| G-17 `--nv` | `.def`, `verify-image.sh` |
| G-18 explicit `APPTAINER_CACHEDIR` | `build-image.sh`, `env.example` |
| G-19 `ControlMaster` documented | `docs/setup.md` §7 |
| G-20 no MFA workaround | `docs/setup.md` §7, stated explicitly |

---

## Build Failures Encountered and Fixed

Two failures on the real cluster, both diagnosed to root cause and fixed in the artifacts rather
than worked around.

### 1. `--fakeroot` cannot read inputs on root_squashed network storage

`permission denied` opening the definition file, before any build step. `--fakeroot` remaps the
invoking UID to root inside a user namespace; `root_squash` on `/project` (Lustre) and `/home` (NFS)
maps that back to `nobody`, which cannot traverse a `0700` home directory.

**Fixed** by staging the build onto node-local `$TMPDIR` in `build-image.sh` — which is the correct
approach anyway, since a container build is a many-small-files workload that Grex's docs say to keep
off the shared filesystem. Also keeps the transient build cache off the 100 GB quota.

### 2. `apt-get` cannot run inside a `--fakeroot` `%post`

`Couldn't create temporary file /tmp/apt.conf.XXXXXX for passing config to apt-key`, so every
repository was rejected as unsigned. `apt` drops privileges to its sandbox user `_apt` (uid 100),
which is unmapped on the host under fakeroot and therefore cannot write to the bind-mounted `/tmp`.

**Fixed** by removing `apt-get` from `%post` entirely — it was speculative. `git` ships in the base
image, `ca-certificates` is already present, and `wget`/`unzip` are only ever used on the host by
`stage-weights.sh`. `%post` now uses only `git`, `pip`, `grep`, `mkdir`.

**Both fixes made the design better, not just unblocked.** The first moved build I/O to where it
belonged; the second removed an unnecessary dependency and a whole class of privilege-drop failures.

---

## Verification Status

All shell scripts pass `bash -n`. The quota parser was unit-tested against both real Grex `quota -s`
output (→ 99 GB headroom) and the plain-kilobyte format (→ 95 GB).

**Image built and weights staged.** First real execution of `verify-image.sh` completed
**2026-08-06 on `n339`** (a `skylake` CPU node — see §Splitting Verification below).

---

## Verification Results — first real execution (2026-08-06)

Reported **PASS 9 / FAIL 3**. What that actually established:

| Check | Result | Reading |
|---|---|---|
| 1 GPU visible | FAIL | Expected — CPU node, no `nvidia-smi` |
| 2 torch/CUDA | FAIL | Expected — CPU node. `torch 1.12.1+cu116` present, pin correct |
| **3 sokrypton fork** | **PASS** | `dump_pdb` ×2; sha `597d37f2…` matches the pin in `rfdiffusion.def` |
| 4 jaxlib is CUDA build | PASS | `jaxlib 0.4.25+cuda11.cudnn86` — **the pin survived resolution** |
| 4 JAX sees GPU | *false pass* | Defect 1 — reported OK against `[CpuDevice(id=0)]` |
| 5 dgl / e3nn | PASS | `dgl 1.0.2+cu116`, `e3nn 0.3.3` |
| 6 RFdiffusion entry point | FAIL | Defect 2 — script's own precondition, **not** an image fault |
| 7 model assets | PASS ×5, WARN ×1 | Checkpoints, schedules symlink, AlphaFold params. `ananas` absent |

### The result that mattered

**Check 3 passed.** The fork is on `PYTHONPATH` at the pinned commit with both `dump_pdb` keys, so
**FR-16 (step progress) and FR-17 (live 3D preview) are achievable**. This was ordered first
precisely because it could invalidate the approach, and it is now retired — at the cost of a
20-minute CPU allocation, with no GPU involved.

The jaxlib half of check 4 also passed, meaning the §8.1e clobbering fix held in the shipped image.
**The GPU half of check 4 remains genuinely unverified** — see Defect 1.

### Splitting verification across CPU and GPU

The `gpu` partition estimated a **five-day** queue wait for the documented
`--gpus=1 --cpus-per-task=6 --mem-per-cpu=6000M --time=0-00:30:00` allocation. Rather than block,
verification was split: checks 3, 5, 6, 7 and the jaxlib half of 4 are pure filesystem and import
tests requiring **no GPU at all**, and were run immediately on a `skylake` CPU node.

This is a reusable property of the check ordering, not a workaround — the two approach-invalidating
checks were placed first, and one of them turns out to need no GPU. Only checks 1, 2 and the JAX
device test are genuinely GPU-gated. Queue-reduction guidance (multi-partition requests, the
preemptible `-b` pool, short-walltime backfill) is in `docs/setup.md`.

---

## Verification Script Defects Found and Fixed

Both defects were in `verify-image.sh` itself. Neither is reachable by `bash -n`, which is why both
survived generation — the script had never been executed against a real image before this run.

### Defect 1 — check 4 could not fail (the dangerous one)

The GPU-device assertion grepped the **whole** captured output for `cuda\|gpu`. The jaxlib version
string is `0.4.25+cuda11.cudnn86`, so the match landed on the version line and the check reported
`[ OK ] JAX imports and reports a GPU device` while `jax.devices()` returned `[CpuDevice(id=0)]`.

It passed **whenever the jaxlib pin held** — exactly the situation it exists to test. Run as-is in a
GPU allocation, it would have certified the known CUDA-11 risk as cleared without testing it.

**Fixed** by scoping the grep to the `^devices` line; jax 0.4.25 reports `CudaDevice` on GPU and
`CpuDevice` on CPU. Verified against both real output shapes: `CpuDevice` → fail, `CudaDevice` → pass.

This is §8.1e's lesson recurring one layer out. There, a silent CPU-only jaxlib would have produced
an image that *looked* correct; here, a check that cannot fail would have produced a verification
that *looked* clean. The build-time guard caught the first. Nothing was guarding the guard.

### Defect 2 — check 6 violated a precondition the design had already written down

The fork calls `os.mkdir({SCRIPT_DIR}/../schedules)` **at import**, and that path is a symlink onto
`/scratch`. `os.mkdir()` on a dangling symlink raises `FileExistsError`. `verify-image.sh` created
its scratch bind but never `schedules/` inside it, so every attempt to import the fork failed —
while check 7 passed, because it only asserts the symlink *points* at `/scratch/schedules`, never
that anything created it.

`rfdiffusion.def` §schedules documents this exact precondition as a U2b requirement. U1's own
verification script became its first consumer and violated it.

**Fixed** by `mkdir -p "$SCRATCH/schedules"`. Diagnosed from the definition file's documented
mechanism; **confirmation pending the next run** (the failure should change from
`cannot run or import` to a clean pass, and Defect 2b now makes any residual error legible).

### Defect 2b — the failure was unreadable

Check 6 discarded stderr on both branches (`2>/dev/null`), so a one-line `FileExistsError` surfaced
only as `cannot run or import RFdiffusion from the fork`. **Fixed**: stderr is captured and printed
on failure.

### Open item — `ananas` unavailable (WARN, not a gate)

`stage-weights.sh` could not fetch `ananas`; `files.ipd.uw.edu/krypton/` is 404 upstream, the same
bit-rot that killed `schedules.zip`. Correctly a WARN — it costs `symmetry="auto"` only. Supply it
manually via `RFD_ANANAS_URL` or drop the binary at `$RFD_WEIGHTS/bin/ananas`. **Carries into U3**
(symmetry UI must degrade gracefully) and **U2b** (the ananas-unavailable fail-fast rule in
`business-rules.md` is now a live path, not a hypothetical).

---

## Verification Results — second execution (2026-08-06, same CPU node `n339`)

Confirmed both fixes, then found a **third defect — this one in the image itself, not the script**.
Reported **PASS 8 / FAIL 4**, which is *better* than the prior PASS 9 / FAIL 3 despite the lower
count: one FAIL is check 4 correctly flipping from a false pass to a true one (Defect 1's fix
working exactly as intended), and the new FAIL is a real, previously-hidden problem the stderr fix
(Defect 2b) made visible instead of swallowing.

| Check | Result | Reading |
|---|---|---|
| 1, 2 | FAIL | Expected — CPU node |
| 3 | PASS | Fork sha `597d37f2…` confirmed again |
| 4 jaxlib CUDA build | PASS | Pin still intact |
| **4 JAX sees GPU** | **FAIL** | **Correct now** — was a false PASS before Defect 1's fix; on this CPU node it should fail, and it does |
| 5 | PASS | dgl / e3nn import |
| **6** | **FAIL** | **New defect** — see below. Defect 2 (schedules `mkdir`) is confirmed fixed: no `FileExistsError`, a *different* error, further into the import chain |
| 7 | PASS ×5, WARN ×1 | Unchanged |

### Defect 2 confirmation

The predicted `FileExistsError` did **not** recur. Import now proceeds past the schedules symlink
and fails later, on a genuinely different line — direct evidence the Step 9 fix works.

### Defect 3 — two pip packages missing from the image (found via Defect 2b's stderr fix)

```
ModuleNotFoundError: No module named 'icecream'
  at /opt/RFdiffusion/diff_util.py:6, imported by inference/utils.py:8
```

This traceback was only visible **because** Defect 2b (stderr capture) had just been fixed — under
the old script this would again have reported the uninformative `cannot run or import RFdiffusion
from the fork`.

**Root cause**: `reference/diffusion.py`'s commented-out cell 2 (Colab-only, never executed by the
exported script) ran `pip install jedi omegaconf hydra-core icecream pyrsistent pynvml decorator` —
a convenience cell for everything the fork might touch. `rfdiffusion.def` inherits the
**RosettaCommons** base image's install list, which was built for a codebase that imports none of
these six packages, so none of them shipped.

**Investigated by downloading the fork source at the pinned commit and reading every import**,
rather than installing the whole Colab cell defensively or fixing one `ModuleNotFoundError` at a
time across repeated cluster round-trips:

| Package | Needed? | Evidence |
|---|---|---|
| `icecream` | **Yes** | Imported unconditionally by `run_inference.py` (entry point), `diff_util.py`, `contigs.py`, `potentials/manager.py`, `RoseTTAFoldModel.py`, `Embeddings.py` |
| `pyrsistent` | **Yes** | `inference/symmetry.py`: `from pyrsistent import v` — this project's symmetry feature depends on it directly |
| `jedi` | No | Zero references anywhere in the fork; Colab tab-completion only |
| `pynvml`, `decorator` | No | Real entries in `env/SE3Transformer/requirements.txt`, but that file is **decorative** — SE3Transformer's `setup.py` declares no `install_requires`. Both are imported only by `se3_transformer.runtime.{training,inference}`, NVIDIA's own training/benchmark harness. RFdiffusion imports only `se3_transformer.model` (`SE3_network.py`), never `.runtime` — confirmed by grepping the full fork tree at the pinned commit |
| `omegaconf`, `hydra-core` | Already present | Pinned by the base image |

**Both required packages are on the same eager import chain**, which matters operationally:
`run_inference.py` → `inference.utils` → `inference.model_runners` → `inference.symmetry` →
`pyrsistent`, all top-level imports. Fixing only `icecream` would have meant discovering
`pyrsistent` missing on a *fourth* rebuild/restage/reverify cycle. Caught here at zero cluster cost,
and confirms **check 6 needs no modification** — it will exercise both packages on the next run
without any script change.

**Fixed**: `containers/rfdiffusion.def` now runs
`uv pip install --python "$VPY" --no-cache "icecream" "pyrsistent"` immediately after the fork's
`dump_pdb` build-time assertion, with the full per-package audit recorded inline.

**Rebuilt and re-verified, same CPU node, third execution (2026-08-06): PASS 9 / FAIL 3.** Defect 3
confirmed fixed — check 6 now passes in full (`icecream` and `pyrsistent` resolved the fork's real
missing dependencies, and no further hidden import gap surfaced). The 3 FAILs are exactly the
predicted set: checks 1, 2, and the JAX device test — all genuinely GPU-gated, nothing else.

**U1's CPU-verifiable surface is now completely clean.** Three rounds, three real defects found and
fixed (2 in the verification script, 1 in the image), zero remaining CPU-checkable unknowns.

---

## Verification Results — first GPU execution (2026-08-06, same node, real allocation)

The §3 risk this project has carried since the infrastructure design — "ColabDesign may require a
newer JAX than is available for CUDA 11.6" — **materialized**, though inverted from its anticipated
shape: not ColabDesign needing newer JAX, but **JAX itself needing newer CUDA**.

```
CUDA backend failed to initialize: Found CUDA version 11060, but JAX was built against
version 11080, which is newer.
```

`jaxlib 0.4.25+cuda11.cudnn86` — the pin verified as intact through all three CPU rounds — was
compiled against CUDA 11.8; this base image runs CUDA 11.6.2. CUDA's compatibility model only runs
one direction (newer runtime, older build), so this genuinely cannot work as pinned.

**Root-caused from JAX's `CHANGELOG.md`**: `jax 0.4.8` (2023-03-29) is the release where "CUDA 11.4
support has been dropped. JAX GPU wheels only support CUDA 11.8 and CUDA 12." Every cuda11 jaxlib
from 0.4.8 onward needs CUDA ≥ 11.8. **`jaxlib 0.4.7` is the newest cuda11 build predating that
requirement** — confirmed by enumerating the complete wheel index, not assumed from the pre-existing
fallback-ladder text (which named 0.4.7 but paired it with `cudnn82`, not the `cudnn86` this fix
actually uses — see below).

**Downgrading jax alone would have failed the next resolution pass**: `chex==0.1.86` requires
`jax>=0.4.16`; `jax==0.4.7` violates that. Checked chex's PyPI history for exactly where the floor
moved (bumped in `0.1.83`, 2023-09-20) and picked **`chex==0.1.82`** — the newest release still
accepting `jax>=0.4.6`. `optax==0.2.2` and `dm-haiku==0.0.12` needed no change: verified each
package's actual `requires_dist` rather than assuming the whole extras set needed re-pinning.

**Fixed in `containers/rfdiffusion.def`**: `jax==0.4.7`, `jaxlib==0.4.7+cuda11.cudnn86` (kept on
`cudnn86`, not `cudnn82` — the pip-supplied cuDNN 8.6 already works and switching it would have been
an unrelated second variable), `chex==0.1.82`. `%labels` and the build-time guard's comments updated
to match; the guard's comment now states plainly what it can and cannot catch — it asserts jaxlib
*is* a CUDA build, never that the CUDA build is *new enough* for this runtime.

**Not yet rebuilt or re-verified on GPU.**

---

## Next

- **User**: **rebuild the image** (`scripts/build-image.sh`) to pick up the `jax`/`jaxlib`/`chex`
  re-pin, then a short multi-partition GPU allocation to re-verify:
  ```bash
  salloc --partition=agpu,stamps-b,mcordgpu-b,gpu,livi-b --gpus=1 --cpus-per-task=2 --mem-per-cpu=4000M --time=0-00:15:00
  ```
  then `bash scripts/verify-image.sh`. Expect **PASS 12 / FAIL 0** if `jaxlib 0.4.7` resolves the
  CUDA mismatch and ColabDesign has no other incompatibility at this older jax version.
- **If the JAX device check still fails**, the CUDA-11 ceiling is now firmly established at 0.4.7 —
  there is no Tier 1.5 to try. Go straight to the pre-planned Tier 2 fallback (§3 of
  `infrastructure-design.md`, Q3 = B): two images, `colabdesign.sif` on a CUDA 12 base.
- **On a full pass**: U1 is fully verified and done. That closes the last open item before
  **milestone M1** (a real design via hand-written `sbatch`).
- **In parallel, not blocked by the above**: U2b Runner — Functional Design is complete and awaiting
  Code Generation.
