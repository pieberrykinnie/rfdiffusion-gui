# rfd-core

Pure, dependency-free domain logic shared between `rfd-web` (login node) and `rfd-runner`
(container). No PyTorch, no ColabDesign, no filesystem access beyond `run.json`/`progress.json`.
**Must remain importable on Python 3.9** — that is the container's interpreter (U1).

See `aidlc-docs/construction/u2a-core-domain/functional-design/` for the design this implements,
and `reference/diffusion.py` for the notebook it is ported from.
