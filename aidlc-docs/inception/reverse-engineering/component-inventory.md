# Component Inventory

## Application Packages

| Package | Purpose |
|---|---|
| `diffusion.py` | The entire application. A six-cell Colab notebook export combining provisioning, domain logic, process orchestration, visualization, and export in one flat file. Not packaged, not importable, not executable as-is. |

## Infrastructure Packages

**None.** No CDK, Terraform, CloudFormation, Dockerfile, Apptainer definition, Slurm script, or deployment automation of any kind. Provisioning is 35 lines of `os.system()` calls inside Cell 1.

## Shared Packages

**None internal.** All shared utilities are consumed from external third-party packages (`colabdesign`, `inference.utils` from the RFdiffusion checkout).

## Test Packages

**None.** Zero test files, zero test framework configuration, zero CI.

## Logical Components Within `diffusion.py`

Although there is one physical file, these are the separable logical components — and they are the natural seams for the port:

| # | Logical component | Lines | Portability |
|---|---|---|---|
| 1 | Environment provisioning | 21–69 | **Replace** — becomes `uv` project + module loads / container |
| 2 | Template resolution (`get_pdb`) | 85–100 | **Port with changes** — drop Colab upload, add HTTP upload |
| 3 | Symmetry detection (`run_ananas`) | 102–142 | **Port nearly as-is** — replace `os.system` with `subprocess` |
| 4 | Process runner + progress (`run`) | 144–225 | **Rewrite** — ipywidgets has no web equivalent; becomes job polling + SSE/websocket |
| 5 | Design orchestration (`run_diffusion`) | 227–354 | **Port as-is (core value)** — pure-ish logic, must be preserved faithfully |
| 6 | Parameter form + path derivation | 356–407 | **Rewrite** — `#@param` becomes an HTML form + validated request model |
| 7 | Backbone visualization | 409–476 | **Rewrite** — py3Dmol/ipywidgets becomes browser-side 3Dmol.js |
| 8 | Designability harness invocation | 478–517 | **Port with changes** — `!python` becomes a subprocess/Slurm step |
| 9 | Best-result visualization | 519–556 | **Rewrite** — same reason as #7 |
| 10 | Packaging and export | 558–566 | **Rewrite** — `files.download` becomes an HTTP download endpoint |
| 11 | User documentation (contig syntax) | 568–596 | **Port as-is** — becomes in-app help text |

## Total Count

- **Total Packages**: 1 (a single unpackaged script)
- **Application**: 1
- **Infrastructure**: 0
- **Shared**: 0
- **Test**: 0

## Assets Required at Runtime (not in repo)

| Asset | Size (approx.) | Source |
|---|---|---|
| `Base_ckpt.pt` | ~1.3 GB | files.ipd.uw.edu |
| `Complex_base_ckpt.pt` | ~1.3 GB | files.ipd.uw.edu |
| `Complex_beta_ckpt.pt` | ~1.3 GB | files.ipd.uw.edu |
| `schedules.zip` | small | files.ipd.uw.edu |
| `alphafold_params_2022-12-06.tar` | ~4 GB | storage.googleapis.com |
| `ananas` binary | small | files.ipd.uw.edu |
| RFdiffusion source | — | github.com/sokrypton/RFdiffusion |
| ColabDesign source | — | github.com/sokrypton/ColabDesign |

**Total**: roughly 8 GB of model weights that are re-downloaded every Colab session. On a persistent HPC filesystem these become a one-time install — a significant improvement, but one that must be planned against the /home 100 GB quota (they belong in `/project`).
