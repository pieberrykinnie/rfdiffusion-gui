# Reference — original Colab notebook

`diffusion.py` is the **unmodified** Colab export this project was ported from:

<https://colab.research.google.com/github/sokrypton/ColabDesign/blob/main/rf/examples/diffusion.ipynb>

## Do not edit it

It is retained for two reasons:

1. **Rollback fallback.** If the port is blocked at any stage, this notebook still works in Colab.
   The execution plan depends on that property, so the file must stay byte-identical to what was
   exported.
2. **Behavioural reference.** `rfd-core` and `rfd-runner` are required to be behaviour-preserving
   (FR-12, NFR-9). When a question arises about what the port *should* do, this file is the answer.

## Reading it

Cells 1, 2 and 4 are commented out — Colab's exporter comments out `%%time` magic cells wholesale.
Those three cells contain the environment provisioning and **every helper function**, so they are the
most important content in the file despite not being live Python. The file is not executable as
shipped.

Full analysis: `aidlc-docs/inception/reverse-engineering/`.

## What was carried over

| Notebook | Port |
|---|---|
| `run_diffusion()` mode inference, symmetry, iteration planning | `rfd-core` (pure, tested) |
| `run_diffusion()` template + contig normalisation | `rfd-runner` |
| `run()` process monitoring | `rfd-runner`, writing `progress.json` |
| `get_pdb()` | `rfd-runner` `TemplateResolver` (Colab upload branch removed) |
| `run_ananas()` | `rfd-runner` `SymmetryDetector` |
| `plot_pdb()` (both definitions) | `rfd-web` viewer, client-side 3Dmol.js |
| Cell 1 provisioning | `containers/rfdiffusion.def` + `scripts/stage-weights.sh` |
| `files.download()` | `rfd-web` HTTP download endpoint |
| Instructions block | in-app contig help (FR-34) |
