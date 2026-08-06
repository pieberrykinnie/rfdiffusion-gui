# U2a Core Domain — Domain Entities

All models are **Python 3.9-compatible** (hard constraint from U1: the container's interpreter is
3.9). Concretely: `class X(str, Enum)` not `StrEnum`; `Optional[T]`/`Union[T, None]` not `T | None` at
runtime (fine in annotations under `from __future__ import annotations`, but constructors and
`isinstance` checks must not rely on PEP 604 at runtime); no `match` statements.

---

## 1. `Segment` and `ContigSpec`

```python
@dataclass(frozen=True)
class Segment:
    raw: str                    # original text, e.g. "A163-181"
    is_fixed: bool
    chain: Optional[str]        # single letter, set iff is_fixed
    # Free-segment detail (set iff not is_fixed):
    length_min: Optional[int]   # e.g. 40 for "40", 40 for "40-100"
    length_max: Optional[int]   # e.g. 40 for "40" (exact), 100 for "40-100" (range)

@dataclass(frozen=True)
class ContigSpec:
    tokens: List[List[Segment]]   # outer = chain tokens, inner = "/"-separated segments

    @classmethod
    def parse(cls, raw: str) -> "ContigSpec": ...   # raises ContigParseError (see below)

    @property
    def is_empty(self) -> bool: ...          # tokens == []
    @property
    def has_free(self) -> bool: ...          # any segment across all tokens is free
    @property
    def has_fixed(self) -> bool: ...         # any segment across all tokens is fixed
    @property
    def fixed_chains(self) -> List[str]: ... # unique chain letters, first-appearance order
    def to_list(self) -> List[str]: ...      # round-trips to the original per-token strings
```

**`ContigParseError`**: raised by `parse()` for the malformed cases in business-rules.md §2 (empty
segment, `"0"`-length free segment, `"0"` lower bound in a range, multi-character chain letter).
Carries the offending raw segment and a human-readable reason. `RequestValidator` (U4-adjacent, C-26)
catches this and turns it into a `ValidationOutcome` entry — `ContigSpec.parse` itself raises, since
it is a pure parser and raising is the right shape for a function with one obvious failure mode;
`ValidationOutcome` is used at the `DesignRequest` level, one layer up, where *multiple* fields are
checked together and partial failure needs to be reported as a collection.

---

## 2. Mode, Symmetry, Iteration Types

```python
class DesignMode(str, Enum):
    FREE = "free"
    FIXED = "fixed"
    PARTIAL = "partial"

class SymmetryKind(str, Enum):
    NONE = "none"
    AUTO = "auto"
    CYCLIC = "cyclic"
    DIHEDRAL = "dihedral"

@dataclass(frozen=True)
class SymmetryPlan:
    group: Optional[str]     # "c3", "d2", or None
    copies: int               # >= 1
    deferred: bool            # True only for AUTO, pre-AnAnaS
    add_potential: bool

@dataclass(frozen=True)
class IterationPlan:
    steps: int
    hydra_key: str            # "diffuser.T" | "diffuser.partial_T"
```

---

## 3. `DesignRequest`

```python
class DesignRequest(BaseModel):
    # identity
    name: str

    # RFdiffusion
    contigs: str
    pdb: Optional[str] = None
    iterations: int = 50
    hotspot: Optional[str] = None
    num_designs: int = 1
    symmetry: SymmetryKind = SymmetryKind.NONE
    order: int = 1
    chains: Optional[str] = None
    add_potential: bool = False
    partial_T: str = "auto"
    use_beta_model: bool = False
    live_preview: bool = True

    # ProteinMPNN / AlphaFold
    num_seqs: int = 8
    mpnn_sampling_temp: float = 0.1
    rm_aa: Optional[str] = "C"
    use_soluble_mpnn: bool = False
    initial_guess: bool = False
    num_recycles: int = 1
    use_multimer: bool = False

    # Slurm (validated in U3, not here -- present on the model because the web
    # form submits them together, but rfd-core places no constraints on them)
    partition: str
    account: Optional[str] = None
    walltime: str
    gpus: int = 1
    cpus_per_task: int = 6
    mem_per_cpu: str = "6000M"
```

Defaults mirror the notebook's own defaults (`contigs="100"` is the notebook's example, not encoded
as a default here — `contigs` has no sensible default and is required).

---

## 4. `RunRecord` — `run.json` contract

```python
class StageState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"

class RunOutputs(BaseModel):
    backbone_pdbs: List[str] = []       # relative paths within run_dir
    trajectory_pdbs: List[str] = []
    best_pdb: Optional[str] = None
    best_design_pdb: Optional[str] = None
    result_zip: Optional[str] = None

class RunRecord(BaseModel):
    schema_version: int = 1

    # identity
    run_id: str
    name: str
    run_dir: str                        # absolute path, string (not Path -- JSON-native)
    created_at: datetime

    # submitted request, preserved verbatim
    request: DesignRequest

    # produced by the runner during backbone_state == RUNNING/COMPLETED
    mode: Optional[DesignMode] = None
    normalised_contigs: Optional[List[str]] = None
    copies: Optional[int] = None

    # Slurm linkage
    slurm_job_id: Optional[str] = None

    # per-stage state
    backbone_state: StageState = StageState.PENDING
    validate_state: StageState = StageState.PENDING

    # timestamps
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    # failure detail
    exit_code: Optional[int] = None
    error: Optional[str] = None

    outputs: Optional[RunOutputs] = None

    @classmethod
    def load(cls, run_dir: Path) -> "RunRecord": ...   # via AtomicJsonStore
    def save(self, run_dir: Path) -> None: ...
```

**`schema_version`**: starts at `1`. No migration logic exists yet — this field exists purely so a
future format change can detect old records rather than fail confusingly. Decided without a question
(low-risk, purely additive, avoids a harder retrofit).

**Why `normalised_contigs`/`mode`/`copies` are `Optional`**: they don't exist until the backbone stage
has actually run `ContigNormaliser` (U2b) — before that, `RunRecord` only has the raw request.

---

## 5. `ProgressState` — `progress.json` contract

```python
class ProgressState(BaseModel):
    schema_version: int = 1

    stage: str                # "backbone" | "validate"
    design_index: int         # 0-based
    total_designs: int
    step: int                 # current denoising step (or ProteinMPNN/AF equivalent progress unit)
    total_steps: int
    frame_path: Optional[str] = None   # relative path to current_frame.pdb, set iff live_preview
    updated_at: datetime

    @classmethod
    def load(cls, run_dir: Path) -> Optional["ProgressState"]: ...  # None if absent or unreadable
    def save(self, run_dir: Path) -> None: ...
```

**Deliberately separate from `RunRecord`** (DD-4/Q4 from Application Design, restated here as the
concrete schema): a partial or stale `progress.json` can never corrupt the durable run record. `load`
returns `None` rather than raising on any read problem — progress is best-effort by nature.

---

## 6. `AtomicJsonStore`

```python
def write_json_atomic(path: Path, model: BaseModel) -> None:
    # 1. serialise `model` to JSON
    # 2. write to a sibling temp file (same directory, so os.replace is atomic
    #    even across the NFS mount used for /home)
    # 3. os.replace(temp, path)

def read_json(path: Path, model_cls: Type[T]) -> Optional[T]:
    # Returns None if the file is absent, empty, or fails to parse -- callers
    # decide whether that is an error (RunRecord) or expected (ProgressState
    # before the first update).
```

No dependency on any other domain type — this is the one component every other model in this file
depends on for persistence.

---

## 7. `PathLayout`

```python
class PathLayout:
    weights_root: Path
    image_path: Path
    output_root: Path
    database_path: Path

    @classmethod
    def from_env(cls) -> "PathLayout":
        # Reads RFD_WEIGHTS, RFD_IMAGE, RFD_OUTPUT_ROOT, RFD_DB (env.example),
        # defaulting under $HOME per NFR-6.
        ...

    def run_dir(self, run_id: str) -> Path:
        return self.output_root / run_id
```

Pure environment-variable resolution; no filesystem I/O beyond what callers do with the returned
paths (this class does not create directories — that is `SubmissionService`'s job, U3/U4).

---

## 8. Entity Relationship Summary

```
DesignRequest ──(embedded in)──> RunRecord ──(1:1 per run_dir)──> ProgressState
     ▲                                │
     │ validated by                  │ read/written via
     │ ContigSpec + rules             ▼
RequestValidator (C-26, U4)     AtomicJsonStore
```

`ContigSpec`, `DesignMode`, `SymmetryPlan`, `IterationPlan` are **not persisted** — they are computed
fresh from `DesignRequest.contigs` / `.symmetry` / `.order` / `.iterations` / `.partial_T` each time
they're needed (in the runner, and in the web form's live preview, FR-4). Only their *results*
(`mode`, `normalised_contigs`, `copies`) that depend on the actual template get persisted into
`RunRecord`, because those require a parsed PDB and cannot be cheaply recomputed from the record alone.
