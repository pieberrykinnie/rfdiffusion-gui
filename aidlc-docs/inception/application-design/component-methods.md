# Component Methods

Method signatures and input/output types. **Detailed business rules are deferred to Functional
Design** (U2 for `rfd-core`/`rfd-runner` logic, U3 for persistence and Slurm contracts).

Signatures are indicative Python; exact naming is settled during code generation.

---

## `rfd-core`

### C-1 `ContigSpec`

```python
@dataclass(frozen=True)
class Segment:
    raw: str
    is_fixed: bool          # leading alphabetic, e.g. "A163-181"
    chain: str | None       # "A" when fixed
    length_min: int | None  # numeric or range lower bound
    length_max: int | None

class ContigSpec:
    @classmethod
    def parse(cls, raw: str) -> "ContigSpec": ...
    @property
    def chains(self) -> list[list[Segment]]: ...
    @property
    def fixed_chains(self) -> list[str]: ...
    @property
    def has_free(self) -> bool: ...
    @property
    def has_fixed(self) -> bool: ...
    @property
    def is_empty(self) -> bool: ...
    def to_list(self) -> list[str]: ...
```

*Purpose*: purely syntactic parse — no PDB access, no heavy imports.

### C-2 `DesignModeInferrer`

```python
class DesignMode(StrEnum):
    FREE = "free"; FIXED = "fixed"; PARTIAL = "partial"

def infer_mode(spec: ContigSpec) -> DesignMode: ...
```

*Purpose*: the notebook's protocol rule (FR-12). Primary property-test target (NFR-17).

### C-3 `SymmetryResolver`

```python
class SymmetryKind(StrEnum):
    NONE = "none"; AUTO = "auto"; CYCLIC = "cyclic"; DIHEDRAL = "dihedral"

@dataclass(frozen=True)
class SymmetryPlan:
    group: str | None       # "c3", "d2", or None
    copies: int
    deferred: bool          # True when kind is AUTO (runner resolves via AnAnaS)
    add_potential: bool

def resolve_symmetry(kind: SymmetryKind, order: int, add_potential: bool) -> SymmetryPlan: ...
def apply_detected_group(plan: SymmetryPlan, detected: str) -> SymmetryPlan: ...
```

### C-4 `IterationPlanner`

```python
@dataclass(frozen=True)
class IterationPlan:
    steps: int
    hydra_key: str          # "diffuser.T" or "diffuser.partial_T"

def plan_iterations(mode: DesignMode, iterations: int, partial_T: str | int) -> IterationPlan: ...
```

*Raises* `ValueError` on non-numeric `partial_T` (fixes TD-11).

### C-5 `InferenceArgvBuilder`

```python
def build_inference_argv(
    request: DesignRequest,
    normalised_contigs: list[str],
    mode: DesignMode,
    symmetry: SymmetryPlan,
    iterations: IterationPlan,
    output_prefix: Path,
    dump_path: Path,          # $TMPDIR-derived
    input_pdb: Path | None,
    ckpt_override: Path | None,
) -> list[str]: ...
```

*Returns* an argument list, never a shell string (NFR-11). Ordering matters: symmetry config options
are prepended, matching the notebook.

### C-6 `DesignRequest`

```python
class DesignRequest(BaseModel):
    name: str
    contigs: str
    pdb: str | None
    iterations: int                 # bounded
    hotspot: str | None
    num_designs: int
    symmetry: SymmetryKind
    order: int                      # 1..12
    chains: str | None
    add_potential: bool
    partial_T: str
    use_beta_model: bool
    live_preview: bool              # notebook `visual`: publish frames during the run
    # validation stage
    num_seqs: int
    mpnn_sampling_temp: float
    rm_aa: str
    use_soluble_mpnn: bool
    initial_guess: bool
    num_recycles: int
    use_multimer: bool
    # slurm
    partition: str
    account: str | None
    walltime: str                   # DD-HH:MM:SS
    gpus: int
    cpus_per_task: int
    mem_per_cpu: str
```

### C-7 `RunRecord`

```python
class StageState(StrEnum):
    PENDING = "pending"; RUNNING = "running"; COMPLETED = "completed"
    FAILED = "failed"; CANCELLED = "cancelled"; SKIPPED = "skipped"

class RunRecord(BaseModel):
    run_id: str
    name: str
    run_dir: Path
    request: DesignRequest
    mode: DesignMode | None
    normalised_contigs: list[str] | None
    copies: int | None
    slurm_job_id: str | None
    backbone_state: StageState
    validate_state: StageState
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    exit_code: int | None
    error: str | None
    outputs: RunOutputs | None

    @classmethod
    def load(cls, run_dir: Path) -> "RunRecord": ...
    def save(self, run_dir: Path) -> None: ...
```

### C-8 `ProgressState`

```python
class ProgressState(BaseModel):
    stage: str                  # "backbone" | "validate"
    design_index: int
    total_designs: int
    step: int
    total_steps: int
    frame_path: Path | None     # current_frame.pdb, when published
    updated_at: datetime

    @classmethod
    def load(cls, run_dir: Path) -> "ProgressState | None": ...
    def save(self, run_dir: Path) -> None: ...
```

### C-9 `AtomicJsonStore`

```python
def write_atomic(path: Path, data: bytes) -> None: ...          # temp + os.replace
def write_json_atomic(path: Path, model: BaseModel) -> None: ...
def read_json(path: Path, model_cls: type[T]) -> T | None: ...  # None if absent/partial
```

### C-10 `PathLayout`

```python
class PathLayout:
    @classmethod
    def from_env(cls) -> "PathLayout": ...
    @property
    def weights_root(self) -> Path: ...
    @property
    def image_path(self) -> Path: ...
    @property
    def output_root(self) -> Path: ...
    @property
    def database_path(self) -> Path: ...
    def run_dir(self, run_id: str) -> Path: ...
```

---

## `rfd-runner`

### C-11 `TemplateResolver`

```python
def resolve_template(pdb: str | None, run_dir: Path) -> Path | None: ...
```
Local path · 4-char code → RCSB · otherwise → AlphaFold DB · uploaded file already in `run_dir`.

### C-12 `SymmetryDetector`

```python
@dataclass
class SymmetryDetection:
    group: str            # "c3", "d2"
    rmsd: float
    asymmetric_unit_pdb: str

def detect_symmetry(pdb_str: str, run_dir: Path, hint: str | None = None) -> SymmetryDetection | None: ...
```
Returns `None` for *no symmetry detected*; raises for *detector failed* (NFR-12).

### C-13 `ContigNormaliser`

```python
def normalise_contigs(
    spec: ContigSpec, mode: DesignMode, parsed_pdb: object | None, copies: int
) -> list[str]: ...
```
The only contig-path component importing ColabDesign.

### C-14 `InferenceExecutor`

```python
@dataclass
class InferenceResult:
    exit_code: int
    stderr_tail: str

def run_inference(
    argv: list[str], total_steps: int, num_designs: int,
    dump_dir: Path, on_step: Callable[[int, int, Path], None],
) -> InferenceResult: ...
```
`on_step(design_index, step, frame_path)` is the hook driving C-15 and C-16.

### C-15 `FramePublisher`

```python
class FramePublisher:
    def __init__(self, run_dir: Path, every_n: int = 5, enabled: bool = True) -> None: ...
    def maybe_publish(self, step: int, frame: Path) -> Path | None: ...
```
Publishes `<run_dir>/current_frame.pdb` atomically every `every_n` steps (Q3 = B).
`enabled=False` (from `DesignRequest.live_preview`) skips publishing entirely — the notebook's
`visual="none"`. Step counting continues regardless, so the progress bar still advances.

### C-16 `ProgressReporter`

```python
class ProgressReporter:
    def update_step(self, stage: str, design_index: int, step: int, total: int) -> None: ...
    def set_frame(self, frame_path: Path) -> None: ...
    def set_stage(self, stage: str) -> None: ...
```

### C-17 `PdbPostProcessor`

```python
def fix_outputs(run_dir: Path, name: str, num_designs: int, contigs: list[str]) -> None: ...
```

### C-18 `ValidationExecutor`

```python
def run_validation(
    run_dir: Path, name: str, normalised_contigs: list[str],
    copies: int, request: DesignRequest,
) -> InferenceResult: ...
```
Receives contigs and copies **as arguments held in memory** — no file handoff (AD-5).

### C-19 `ResultPackager`

```python
def stage_out(tmpdir: Path, run_dir: Path) -> None: ...
def package_results(run_dir: Path, name: str) -> Path: ...
```

### C-20 `PipelineOrchestrator`

```python
class Stage(StrEnum):
    ALL = "all"; BACKBONE = "backbone"; VALIDATE = "validate"

def main(run_dir: Path, stage: Stage = Stage.ALL) -> int: ...
```
Entry point. Keeps `normalised_contigs` and `copies` in memory across stages; guarantees a terminal
`RunRecord` state even on failure.

---

## `rfd-web`

### C-21 `SlurmAdapter`

```python
class SlurmState(StrEnum):
    PENDING = "PENDING"; RUNNING = "RUNNING"; COMPLETED = "COMPLETED"
    FAILED = "FAILED"; CANCELLED = "CANCELLED"; TIMEOUT = "TIMEOUT"; UNKNOWN = "UNKNOWN"

class SlurmAdapter(Protocol):
    def submit(self, script: Path, cwd: Path) -> str: ...        # returns job id
    def state(self, job_id: str) -> SlurmState: ...              # squeue, then sacct
    def cancel(self, job_id: str) -> None: ...
    def partitions(self) -> list[PartitionInfo]: ...
```
A `Protocol` so tests can substitute a fake (NFR-18).

### C-22 `PartitionDiscovery`

```python
@dataclass
class PartitionInfo:
    name: str
    has_gpu: bool
    max_walltime: str | None

def discover_partitions(adapter: SlurmAdapter) -> list[PartitionInfo]: ...
```

### C-23 `JobScriptGenerator`

```python
def generate_job_script(record: RunRecord, layout: PathLayout) -> str: ...
def write_job_script(record: RunRecord, layout: PathLayout) -> Path: ...
```
Emits a Grex-conformant `#SBATCH` script (G-1 … G-12), retained in the run directory (G-2).

### C-24 `RunRepository`

```python
class RunRepository:
    def create(self, record: RunRecord) -> None: ...
    def update_state(self, run_id: str, **fields) -> None: ...
    def get(self, run_id: str) -> RunRecord | None: ...
    def list(self, limit: int = 100) -> list[RunSummary]: ...
```

### C-25 `RunDirectoryReader`

```python
def read_record(run_dir: Path) -> RunRecord | None: ...
def read_progress(run_dir: Path) -> ProgressState | None: ...
def current_frame(run_dir: Path) -> Path | None: ...
def list_designs(run_dir: Path, name: str) -> list[DesignOutputs]: ...
def best_design_index(run_dir: Path) -> int | None: ...   # parses REMARK 001 of best.pdb
def log_tail(run_dir: Path, lines: int = 50) -> str: ...
```

### C-26 `RequestValidator`

```python
@dataclass
class ValidationOutcome:
    ok: bool
    mode: DesignMode | None
    errors: list[str]
    warnings: list[str]

def validate(request: DesignRequest) -> ValidationOutcome: ...
def preview_mode(contigs: str) -> DesignMode | None: ...   # drives FR-4, no cluster needed
```

### C-27 `TemplateUploadHandler`

```python
async def save_upload(upload: UploadFile, run_dir: Path) -> Path: ...
```

### C-28 `Routes`

| Method | Path | Purpose | Req |
|---|---|---|---|
| `GET` | `/` | Run list | FR-27 |
| `GET` | `/new` | Submission form | FR-1, FR-2 |
| `POST` | `/api/preview-mode` | Live inferred-mode preview (HTMX) | FR-4 |
| `POST` | `/runs` | Validate, create run, submit job | FR-8 |
| `GET` | `/runs/{id}` | Run detail | FR-15, FR-18 |
| `GET` | `/runs/{id}/status` | HTMX status fragment | FR-15, FR-16, FR-20 |
| `GET` | `/runs/{id}/frame` | Current live frame PDB | FR-17 |
| `GET` | `/runs/{id}/structure/{n}` | Final backbone PDB | FR-21 |
| `GET` | `/runs/{id}/trajectory/{n}` | Trajectory PDB | FR-23 |
| `GET` | `/runs/{id}/best` | Best-design overlay data | FR-24 |
| `GET` | `/runs/{id}/download` | Result zip | FR-31 |
| `GET` | `/runs/{id}/file/{path}` | Individual file | FR-32 |
| `POST` | `/runs/{id}/cancel` | Cancel job | FR-14 |
| `POST` | `/runs/{id}/clone` | Reload params into form | FR-30 |
| `GET` | `/help/contigs` | In-app contig syntax help | FR-34 |
