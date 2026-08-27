# rfd-web

The login-node half of rfdiffusion-gui. It submits Slurm jobs, tracks them, cancels them,
indexes them, and answers the one question the UI keeps asking: **what is the state of
this run?**

This package currently contains **U3 only** — the Slurm client, the SQLite run index, and
the reconciliation service. U4 adds the HTTP layer (FastAPI routes, Jinja2 templates, HTMX
polling, vendored 3Dmol.js) on top of the services exported here.

## What it deliberately does not contain

| Not here | Where it lives |
|---|---|
| PyTorch, JAX, CUDA, ColabDesign | The U1 container image; this environment must stay GPU-free (NFR-2) |
| Any dependency on `rfd-runner` | Never. The boundary is resolver-enforced and asserted in `tests/test_boundaries.py` |
| FastAPI, uvicorn, Jinja2 | U4. Declaring an unused web framework would put unused packages in `uv.lock` |
| Contig parsing, mode inference, request validation | `rfd-core` — `validate()` and `preview_mode()` already are C-26 |

## Layout

```
src/rfd_web/
├── config.py       WebConfig.from_env()
├── errors.py
├── status.py       RunStatus -- the reconciled outcome vocabulary
├── slurm/
│   ├── states.py   SlurmState, JobStatus, the total Slurm state map
│   ├── adapter.py  SlurmAdapter (Protocol) + CliSlurmAdapter -- the ONLY subprocess site
│   ├── fake.py     FakeSlurmAdapter
│   ├── partitions.py
│   └── script.py   JobScriptGenerator
├── persistence/    schema.py, repository.py, reader.py, reconcile.py
└── services/       submission.py (S-1), query.py (S-2)
```

## Running the tests

No cluster required — that is the point of `FakeSlurmAdapter` (NFR-18):

```bash
uv run --package rfd-web pytest packages/rfd-web/tests -q
```

The suite uses **real** SQLite files, **real** directories, and **real** `bash`. The only
thing faked is Slurm. In particular `tests/test_script_execution.py` *executes* the
generated job script against a stub container engine on `PATH`, because the bug that cost
Milestone M1 a GPU allocation (a hardcoded `apptainer` where Grex provides `singularity`)
was syntactically perfect and invisible to every test that only read the script.

## Configuration

Six variables are new in this unit — `RFD_STATUS_POLL_SECONDS`,
`RFD_SLURM_TIMEOUT_SECONDS`, `RFD_PARTITION_CACHE_SECONDS`, `RFD_PROGRESS_STALE_SECONDS`,
`RFD_INCOMPATIBLE_PARTITIONS`, `RFD_LOG_TAIL_LINES`. All are documented with their
reasoning in the repository's `env.example`.

## Python version

`>=3.9,<3.10`, matching the rest of the workspace. `rfd-web` depends on `rfd-core`, which
is capped below 3.10 so it can import inside the U1 container — so any environment that
can import `rfd-core` is a 3.9 environment, the login node included. The login node's
*system* `python3` (3.6.8) is unusable; `uv` supplies the interpreter (see
`docs/setup.md`).
