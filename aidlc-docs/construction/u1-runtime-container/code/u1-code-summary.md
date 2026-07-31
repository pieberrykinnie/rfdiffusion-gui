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

## Verification Status

All shell scripts pass `bash -n`. The quota parser was unit-tested against both real Grex `quota -s`
output (→ 99 GB headroom) and the plain-kilobyte format (→ 95 GB).

**Not yet executed**: image build, weight staging, and GPU verification are user-run on Grex. These
are precisely the long-running, queue-bound steps the execution plan overlaps with U2a development.

---

## Next

- **User**: run steps 4–6 of `docs/setup.md` on Grex (build, stage, verify)
- **In parallel**: U2a `rfd-core` — pure Python, no cluster needed, **Python 3.9-compatible**
- **Then**: U2b, then milestone M1 (a real design via hand-written `sbatch`)
