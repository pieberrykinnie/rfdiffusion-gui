# rfd-runner

In-container pipeline orchestrator. Runs inside the U1 Apptainer image on a Grex GPU node, driving
RFdiffusion backbone generation and ProteinMPNN/AlphaFold validation as a single Slurm job, and
publishing live progress via `rfd-core`'s `run.json`/`progress.json` contracts.

Depends on `rfd-core` (pure domain logic). Has no dependency on ColabDesign, RFdiffusion's fork, or
PyTorch/JAX declared here -- those are provided by the container image
(`containers/rfdiffusion.def`) at fixed pinned versions. Every call into ColabDesign or the fork is
routed through `src/rfd_runner/_colabdesign.py`, a thin bridge module that imports lazily so this
package **imports and its non-GPU logic runs correctly with zero ColabDesign/torch/JAX installed**
-- which is what makes it possible to test locally.

See `aidlc-docs/construction/u2b-runner/functional-design/` for the design this implements, and
`reference/diffusion.py` for the notebook cells (`run()`, `run_diffusion()`, `run_ananas()`,
`get_pdb()`, and the ProteinMPNN/AlphaFold validation cell) it is ported from.
