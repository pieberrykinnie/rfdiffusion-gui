"""PipelineOrchestrator -- the full control flow, implementing business-logic-model.md section 2
verbatim. Entry point for containers/rfdiffusion.def's %runscript (via __main__.py).

OrchestratorDeps bundles every collaborator behind one injectable parameter, which is the seam
unit-of-work.md's "partially testable without cluster" claim for this unit depends on: the entire
flow below is unit-testable against fakes/spies, with zero real subprocess and zero ColabDesign
installed.
"""
from __future__ import annotations

import signal
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from rfd_core import (
    ContigSpec,
    DesignMode,
    RunOutputs,
    RunRecord,
    StageState,
    SymmetryError,
    apply_detected_group,
    build_inference_argv,
    infer_mode,
    plan_iterations,
    resolve_symmetry,
)

from . import _colabdesign
from .config import RunnerConfig
from .contig_normaliser import ContigNormaliser
from .errors import (
    AnanasUnavailableError,
    NoCompletedBackboneError,
    SymmetryDetectionError,
)
from .frame_publisher import FramePublisher
from .inference_executor import InferenceExecutor
from .pdb_postprocessor import PdbPostProcessor
from .progress_reporter import ProgressReporter
from .result_packager import ResultPackager
from .symmetry_detector import SymmetryDetector
from .template import TemplateResolver
from .validation_executor import ValidationExecutor


class Stage(str, Enum):
    ALL = "all"
    BACKBONE = "backbone"
    VALIDATE = "validate"


class _ProcTracker:
    """Records the most recently spawned Popen so the SIGTERM handler can forward the signal."""

    def __init__(self) -> None:
        self.current: Optional["subprocess.Popen[str]"] = None

    def factory(self, base_factory: Callable[..., Any]) -> Callable[..., Any]:
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            proc = base_factory(*args, **kwargs)
            self.current = proc
            return proc

        return wrapped


@dataclass
class OrchestratorDeps:
    # /scratch is the container's bind target for $TMPDIR (containers/rfdiffusion.def, deployment
    # architecture) -- a fixed in-container path in production, not derived from an env var.
    # Overridable here (rather than a bare module constant) so the full control flow -- including
    # the mandatory `mkdir schedules` step -- is testable without touching the real filesystem
    # root.
    dump_dir: Path = field(default_factory=lambda: Path("/scratch"))
    config: RunnerConfig = field(default_factory=RunnerConfig.from_env)
    template_resolver: TemplateResolver = field(default_factory=TemplateResolver)
    symmetry_detector: SymmetryDetector = field(default_factory=SymmetryDetector)
    contig_normaliser: ContigNormaliser = field(default_factory=ContigNormaliser)
    inference_executor: InferenceExecutor = field(default_factory=InferenceExecutor)
    pdb_postprocessor: PdbPostProcessor = field(default_factory=PdbPostProcessor)
    validation_executor: ValidationExecutor = field(default_factory=ValidationExecutor)
    result_packager: ResultPackager = field(default_factory=ResultPackager)
    frame_publisher_factory: Callable[..., FramePublisher] = FramePublisher
    progress_reporter_factory: Callable[..., ProgressReporter] = ProgressReporter


def _run_backbone(
    run_dir: Path,
    record: RunRecord,
    deps: OrchestratorDeps,
    tracker: _ProcTracker,
    stage_ref: Dict[str, Optional[str]],
) -> int:
    config = deps.config
    request = record.request

    stage_ref["value"] = "backbone"
    record.backbone_state = StageState.RUNNING
    record.started_at = record.started_at or datetime.now(timezone.utc)
    record.save(run_dir)

    spec = ContigSpec.parse(request.contigs)
    mode = infer_mode(spec)
    symmetry_plan = resolve_symmetry(request.symmetry, request.order, request.add_potential)

    if mode in (DesignMode.FIXED, DesignMode.PARTIAL):
        try:
            template_path = deps.template_resolver.resolve_template(request.pdb, run_dir)
            pdb_str = _colabdesign.pdb_to_string(str(template_path), chains=(request.chains or None))
        except (OSError, subprocess.CalledProcessError) as e:
            record.backbone_state = StageState.FAILED
            record.error = str(e)
            record.save(run_dir)
            return 1

        if symmetry_plan.deferred:  # symmetry == AUTO
            try:
                detection = deps.symmetry_detector.detect_symmetry(
                    pdb_str, run_dir, ananas_bin=config.ananas_bin
                )
                symmetry_plan = apply_detected_group(
                    symmetry_plan, detection.group if detection else None
                )
            except (AnanasUnavailableError, SymmetryDetectionError, SymmetryError) as e:
                record.backbone_state = StageState.FAILED
                record.error = str(e)
                record.save(run_dir)
                return 1
            if detection is not None:
                pdb_str = detection.asymmetric_unit_pdb_str
        elif mode == DesignMode.FIXED:
            pdb_str = _colabdesign.pdb_to_string(pdb_str, chains=spec.fixed_chains)

        input_pdb_path = run_dir / "input.pdb"
        input_pdb_path.write_text(pdb_str)
        parsed_pdb = _colabdesign.parse_pdb(str(input_pdb_path))

        normalised_contigs = deps.contig_normaliser.normalise_contigs(
            spec, mode, parsed_pdb, symmetry_plan.copies
        )
    else:  # mode == FREE
        normalised_contigs = deps.contig_normaliser.normalise_contigs(
            spec, mode, None, symmetry_plan.copies
        )

    iteration_plan = plan_iterations(mode, request.iterations, request.partial_T)

    # U1 finding: the fork does os.mkdir() on this symlinked path at import time, which raises
    # FileExistsError on a dangling symlink -- must exist before run_inference.py is invoked.
    (deps.dump_dir / "schedules").mkdir(parents=True, exist_ok=True)

    argv = build_inference_argv(
        mode=mode,
        symmetry=symmetry_plan,
        iteration=iteration_plan,
        normalised_contigs=normalised_contigs,
        output_prefix=str(run_dir / request.name),  # PERSISTENT (business-logic-model.md 1.3)
        num_designs=request.num_designs,
        dump_pdb_path=str(deps.dump_dir),  # EPHEMERAL (business-logic-model.md 1.3)
        input_pdb=(str(input_pdb_path) if mode != DesignMode.FREE else None),
        hotspot=request.hotspot,
        use_beta_model=request.use_beta_model,
        beta_ckpt_path=str(config.models_dir / "Complex_beta_ckpt.pt"),
    )
    full_argv = [str(config.python_bin), str(config.fork_root / "run_inference.py")] + argv

    frame_publisher = deps.frame_publisher_factory(
        run_dir, every_n=config.frame_every_n, enabled=request.live_preview
    )
    progress_reporter = deps.progress_reporter_factory(run_dir, request.num_designs)

    def on_step(design_i: int, step: int, frame_path: Path) -> None:
        progress_reporter.update_step("backbone", design_i, step, iteration_plan.steps)
        if request.live_preview:
            frame_publisher.maybe_publish(step, frame_path)

    result = deps.inference_executor.run_inference(
        full_argv,
        total_steps=iteration_plan.steps,
        num_designs=request.num_designs,
        dump_dir=deps.dump_dir,
        on_step=on_step,
        popen_factory=tracker.factory(subprocess.Popen),
        timeout_seconds=config.step_timeout_seconds,
        poll_interval_ms=config.poll_interval_ms,
    )

    if result.exit_code != 0:
        record.backbone_state = StageState.FAILED
        record.error = result.stderr_tail
        record.exit_code = result.exit_code
        record.save(run_dir)
        return 1

    deps.pdb_postprocessor.fix_outputs(run_dir, request.name, request.num_designs, normalised_contigs)
    deps.result_packager.stage_out(deps.dump_dir, run_dir)  # G-13 invariant check, not a copy

    record.mode = mode
    record.normalised_contigs = normalised_contigs
    record.copies = symmetry_plan.copies
    record.backbone_state = StageState.COMPLETED
    record.outputs = record.outputs or RunOutputs()
    record.outputs.backbone_pdbs = [f"{request.name}_{n}.pdb" for n in range(request.num_designs)]
    record.outputs.trajectory_pdbs = [
        p
        for n in range(request.num_designs)
        for p in (
            f"traj/{request.name}_{n}_pX0_traj.pdb",
            f"traj/{request.name}_{n}_Xt-1_traj.pdb",
        )
    ]
    record.save(run_dir)
    return 0


def _run_validate(
    run_dir: Path,
    record: RunRecord,
    deps: OrchestratorDeps,
    tracker: _ProcTracker,
    stage_ref: Dict[str, Optional[str]],
) -> int:
    config = deps.config
    request = record.request

    stage_ref["value"] = "validate"
    record.validate_state = StageState.RUNNING
    record.save(run_dir)

    assert record.normalised_contigs is not None and record.copies is not None  # checked by caller

    result = deps.validation_executor.run_validation(
        run_dir,
        request.name,
        record.normalised_contigs,
        record.copies,
        request,
        popen_factory=tracker.factory(subprocess.Popen),
        cwd=config.af_params_dir,
    )

    if result.exit_code != 0:
        record.validate_state = StageState.FAILED
        record.error = result.stderr_tail
        record.save(run_dir)
        return 1

    zip_path = deps.result_packager.package_results(run_dir, request.name)

    record.validate_state = StageState.COMPLETED
    record.outputs = record.outputs or RunOutputs()
    record.outputs.best_pdb = f"{request.name}/best.pdb"
    record.outputs.best_design_pdb = f"{request.name}/best_design.pdb"
    record.outputs.result_zip = zip_path.name
    record.finished_at = datetime.now(timezone.utc)
    record.save(run_dir)
    return 0


def main(run_dir: Path, stage: Stage = Stage.ALL, deps: Optional[OrchestratorDeps] = None) -> int:
    run_dir = Path(run_dir)
    deps = deps if deps is not None else OrchestratorDeps()
    record = RunRecord.load(run_dir)

    if stage == Stage.VALIDATE:
        if (
            record.backbone_state != StageState.COMPLETED
            or record.normalised_contigs is None
            or record.copies is None
        ):
            # Rejected immediately, before touching Slurm/GPU state or mutating RunRecord --
            # this is a caller-contract violation (retry against a run that never finished
            # backbone), not a run failure.
            print(str(NoCompletedBackboneError(record.run_id)), file=sys.stderr)
            return 1

    tracker = _ProcTracker()
    stage_ref: Dict[str, Optional[str]] = {"value": None}

    def _sigterm_handler(signum: int, frame: Any) -> None:
        # Best-effort (business-rules.md section 4): a subsequent SIGKILL leaves RunRecord in
        # whatever state it was last saved in, which RunQueryService (U3) reconciles against
        # Slurm's own terminal state.
        if tracker.current is not None and tracker.current.poll() is None:
            tracker.current.terminate()
        current = stage_ref["value"]
        if current == "backbone":
            record.backbone_state = StageState.FAILED
        elif current == "validate":
            record.validate_state = StageState.FAILED
        record.error = "terminated (SIGTERM) — likely walltime exceeded"
        record.finished_at = datetime.now(timezone.utc)
        try:
            record.save(run_dir)
        except OSError:
            pass
        sys.exit(1)

    previous_handler = signal.signal(signal.SIGTERM, _sigterm_handler)
    try:
        if stage in (Stage.ALL, Stage.BACKBONE):
            rc = _run_backbone(run_dir, record, deps, tracker, stage_ref)
            if rc != 0:
                return rc
            if stage == Stage.BACKBONE:
                record.validate_state = StageState.SKIPPED
                record.save(run_dir)
                return 0

        return _run_validate(run_dir, record, deps, tracker, stage_ref)
    finally:
        signal.signal(signal.SIGTERM, previous_handler)
