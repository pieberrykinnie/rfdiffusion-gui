"""Domain models: the submitted request, and the run.json/progress.json contracts.

See domain-entities.md sections 3-5. All models are pydantic v2, Python
3.9-compatible.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from .modes import DesignMode
from .storage import read_json, write_json_atomic
from .symmetry import SymmetryKind


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

    # Slurm submission (validated in U3, not here -- rfd-core places no
    # constraints on these fields; they travel with the request because the
    # web form submits everything together)
    partition: str
    account: Optional[str] = None
    walltime: str
    gpus: int = 1
    cpus_per_task: int = 6
    mem_per_cpu: str = "6000M"


class StageState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class RunOutputs(BaseModel):
    backbone_pdbs: List[str] = Field(default_factory=list)
    trajectory_pdbs: List[str] = Field(default_factory=list)
    best_pdb: Optional[str] = None
    best_design_pdb: Optional[str] = None
    result_zip: Optional[str] = None


class RunRecord(BaseModel):
    """The durable per-run record ('run.json'). Written by rfd-runner at start
    and completion; read by rfd-web. schema_version exists so a future format
    change can detect old records rather than fail confusingly -- no migration
    logic exists yet because none is needed for v1.
    """

    schema_version: int = 1

    run_id: str
    name: str
    run_dir: str
    created_at: datetime

    request: DesignRequest

    # Only populated once ContigNormaliser (U2b) has run against the real
    # template -- that requires a parsed PDB, which this model has no access to.
    mode: Optional[DesignMode] = None
    normalised_contigs: Optional[List[str]] = None
    copies: Optional[int] = None

    slurm_job_id: Optional[str] = None

    backbone_state: StageState = StageState.PENDING
    validate_state: StageState = StageState.PENDING

    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    exit_code: Optional[int] = None
    error: Optional[str] = None

    outputs: Optional[RunOutputs] = None

    @classmethod
    def load(cls, run_dir: Path) -> RunRecord:
        record = read_json(Path(run_dir) / "run.json", cls)
        if record is None:
            raise FileNotFoundError(f"no readable run.json in {run_dir}")
        return record

    def save(self, run_dir: Path) -> None:
        write_json_atomic(Path(run_dir) / "run.json", self)


class ProgressState(BaseModel):
    """The volatile progress snapshot ('progress.json'). Deliberately separate
    from RunRecord (Application Design DD-4/Q4=A): a partial or stale
    progress write can never corrupt the durable run record.
    """

    schema_version: int = 1

    stage: str  # "backbone" | "validate"
    design_index: int
    total_designs: int
    step: int
    total_steps: int
    frame_path: Optional[str] = None
    updated_at: datetime

    @classmethod
    def load(cls, run_dir: Path) -> Optional[ProgressState]:
        # Absence or corruption is expected (e.g. before the first update) --
        # not an error, hence None rather than raising.
        return read_json(Path(run_dir) / "progress.json", cls)

    def save(self, run_dir: Path) -> None:
        write_json_atomic(Path(run_dir) / "progress.json", self)
