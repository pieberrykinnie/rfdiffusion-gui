"""rfd-core: pure domain logic for rfdiffusion-gui.

No PyTorch, no ColabDesign, no filesystem access beyond run.json/progress.json.
Importable on Python 3.9 (the container's interpreter) with no heavy
dependencies (NFR-1, NFR-2).
"""
from .argv import build_inference_argv, format_hotspot
from .contigs import ContigParseError, ContigSpec, Segment, get_Ls
from .iterations import IterationError, IterationPlan, plan_iterations
from .models import DesignRequest, ProgressState, RunOutputs, RunRecord, StageState
from .modes import DesignMode, infer_mode
from .paths import PathLayout
from .storage import read_json, write_json_atomic
from .symmetry import (
    SymmetryError,
    SymmetryKind,
    SymmetryPlan,
    apply_detected_group,
    resolve_symmetry,
)
from .validation import MAX_SYMMETRY_ORDER, ValidationOutcome, preview_mode, validate

__all__ = [
    "MAX_SYMMETRY_ORDER",
    "ContigParseError",
    "ContigSpec",
    "DesignMode",
    "DesignRequest",
    "IterationError",
    "IterationPlan",
    "PathLayout",
    "ProgressState",
    "RunOutputs",
    "RunRecord",
    "Segment",
    "StageState",
    "SymmetryError",
    "SymmetryKind",
    "SymmetryPlan",
    "ValidationOutcome",
    "apply_detected_group",
    "build_inference_argv",
    "format_hotspot",
    "get_Ls",
    "infer_mode",
    "plan_iterations",
    "preview_mode",
    "read_json",
    "resolve_symmetry",
    "validate",
    "write_json_atomic",
]
