from __future__ import annotations
"""rfd-web: the login-node half of rfdiffusion-gui.

U3 (this unit) is Slurm submission/tracking/cancellation, the SQLite run index, and
run-state reconciliation. It contains NO HTTP -- routes, templates and the 3Dmol.js
viewer are U4, which builds on the services exported here.

No GPU, no PyTorch, no JAX, and never a dependency on rfd-runner (DD-1, NFR-2).
"""
from .app import create_app
from .config import WebConfig
from .errors import (
    JobScriptError,
    PathContainmentError,
    SlurmError,
    SlurmSubmitError,
    SlurmUnavailable,
)
from .persistence.reader import RunDirectoryReader
from .persistence.reconcile import ReconcileReport, RunIndexReconciler
from .persistence.repository import RunRepository, RunSummary
from .services.query import ProgressView, RunQueryService, RunView
from .services.result import ResultService
from .services.submission import SubmissionOutcome, SubmissionService
from .slurm.adapter import CliSlurmAdapter, SlurmAdapter
from .slurm.fake import FakeSlurmAdapter
from .slurm.partitions import DiscoveryResult, PartitionCache, PartitionInfo, discover_partitions
from .slurm.script import JobScriptGenerator, JobStage, generate_job_script, write_job_script
from .slurm.states import JobStatus, SlurmState
from .status import RunStatus
from .upload import save_upload
from .validation import parse_form_to_request

__all__ = [
    "CliSlurmAdapter",
    "DiscoveryResult",
    "FakeSlurmAdapter",
    "JobScriptError",
    "JobScriptGenerator",
    "JobStage",
    "JobStatus",
    "PartitionCache",
    "PartitionInfo",
    "PathContainmentError",
    "ProgressView",
    "ReconcileReport",
    "RunDirectoryReader",
    "RunIndexReconciler",
    "RunQueryService",
    "RunRepository",
    "RunStatus",
    "RunSummary",
    "RunView",
    "ResultService",
    "SlurmAdapter",
    "SlurmError",
    "SlurmState",
    "SlurmSubmitError",
    "SlurmUnavailable",
    "SubmissionOutcome",
    "SubmissionService",
    "WebConfig",
    "create_app",
    "discover_partitions",
    "generate_job_script",
    "parse_form_to_request",
    "save_upload",
    "write_job_script",
]
