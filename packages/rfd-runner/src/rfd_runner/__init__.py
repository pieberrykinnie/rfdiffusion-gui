"""rfd-runner: in-container pipeline orchestrator for rfdiffusion-gui.

Runs inside the U1 Apptainer image on a GPU node. Depends on rfd-core for all pure logic; every
call into ColabDesign or the RFdiffusion fork goes through _colabdesign.py, a lazy-import bridge
so this package imports cleanly with zero ColabDesign/torch/JAX installed.
"""
from .config import RunnerConfig
from .contig_normaliser import ContigNormaliser
from .errors import (
    AnanasUnavailableError,
    NoCompletedBackboneError,
    RunnerError,
    SymmetryDetectionError,
)
from .frame_publisher import FramePublisher
from .inference_executor import InferenceExecutor, InferenceResult
from .orchestrator import OrchestratorDeps, Stage, main
from .pdb_postprocessor import PdbPostProcessor
from .progress_reporter import ProgressReporter
from .result_packager import ResultPackager
from .symmetry_detector import SymmetryDetection, SymmetryDetector
from .template import TemplateResolver
from .validation_executor import ValidationExecutor

__all__ = [
    "AnanasUnavailableError",
    "ContigNormaliser",
    "FramePublisher",
    "InferenceExecutor",
    "InferenceResult",
    "NoCompletedBackboneError",
    "OrchestratorDeps",
    "PdbPostProcessor",
    "ProgressReporter",
    "ResultPackager",
    "RunnerConfig",
    "RunnerError",
    "Stage",
    "SymmetryDetection",
    "SymmetryDetectionError",
    "SymmetryDetector",
    "TemplateResolver",
    "ValidationExecutor",
    "main",
]
