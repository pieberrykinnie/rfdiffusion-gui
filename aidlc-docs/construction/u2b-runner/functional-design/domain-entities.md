# U2b Runner — Domain Entities

`rfd-runner` introduces few new types of its own — it primarily **consumes** `rfd-core`'s models
(`RunRecord`, `ProgressState`, `DesignRequest`) and **produces** the values that flow into them
(`normalised_contigs`, `copies`, `mode`). What follows are the types genuinely local to this unit.

Unlike `rfd-core`, **`rfd-runner` targets Python 3.9 but has no constraint against PyTorch/JAX/
ColabDesign** — it runs inside the container where those are already installed. It still avoids
PEP 604 union syntax for consistency with `rfd-core` and to avoid a second class of the incident
documented in `u2a-code-summary.md`.

---

## 1. `InferenceResult`

```python
@dataclass(frozen=True)
class InferenceResult:
    exit_code: int
    stderr_tail: str        # last ~4KB of stderr, for FAILED error messages
```

Returned by both `InferenceExecutor.run()` (backbone) and `ValidationExecutor.run()` (validation) —
the same shape serves both, since both are "run a subprocess, report how it went."

---

## 2. `SymmetryDetection`

```python
@dataclass(frozen=True)
class SymmetryDetection:
    group: str              # "c3", "d2", etc. -- never constructed for "nothing found"
    rmsd: float
    asymmetric_unit_pdb_str: str
```

`SymmetryDetector.detect(...)` returns `Optional[SymmetryDetection]` — `None` for "AnAnaS ran, found
nothing" (business-rules.md §1, not a failure). A detector that cannot run at all (`ananas` missing)
is not represented by this type — that path raises before detection is attempted (business-rules.md
§3).

---

## 3. Step Callback Protocol

```python
OnStepCallback = Callable[[int, int, Path], None]
# (design_index, step, frame_path) -> None
```

The contract `InferenceExecutor.run()` calls on every consumed step dump. Two consumers are wired to
it in `PipelineOrchestrator` (business-logic-model.md §2 step 8): `ProgressReporter.update_step`
(always) and `FramePublisher.maybe_publish` (only if `live_preview`).

---

## 4. Configuration (environment variables, new in this unit)

| Variable | Default | Purpose |
|---|---|---|
| `RFD_STEP_TIMEOUT_SECONDS` | `1800` | Per-step stall timeout (business-rules.md §2) |
| `RFD_POLL_INTERVAL_MS` | `100` | Step-dump polling interval, matches the notebook's original cadence |

Both read via `os.environ`, following the same pattern as `rfd-core`'s `PathLayout.from_env` —
plain env vars, no new config file format introduced.

---

## 5. What This Unit Does NOT Define

- **`DesignRequest`, `RunRecord`, `ProgressState`, `StageState`, `RunOutputs`** — all from `rfd-core`,
  used as-is. `rfd-runner` is the sole *writer* of `RunRecord`/`ProgressState` during job execution,
  but does not redefine their shape.
- **Contig grammar, mode inference, symmetry resolution, iteration planning, argv assembly** — all
  `rfd-core`. This unit calls those functions; it does not reimplement their logic.
- **Job script contents, Slurm submission** — U3. This unit is invoked *by* the job script; it has no
  knowledge of how it was submitted.
