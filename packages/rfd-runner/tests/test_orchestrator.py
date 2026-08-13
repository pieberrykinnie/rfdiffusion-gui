import os
import signal
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from rfd_core import DesignRequest, RunRecord, StageState, SymmetryKind

from rfd_runner import _colabdesign
from rfd_runner.config import RunnerConfig
from rfd_runner.errors import AnanasUnavailableError
from rfd_runner.inference_executor import InferenceExecutor, InferenceResult
from rfd_runner.orchestrator import OrchestratorDeps, Stage, main
from rfd_runner.symmetry_detector import SymmetryDetection

# ---------------------------------------------------------------------------
# Fakes -- every collaborator that would otherwise touch a real subprocess or
# ColabDesign is replaced. No real subprocess and no ColabDesign anywhere in
# this file.
# ---------------------------------------------------------------------------


class FakeTemplateResolver:
    def __init__(self, path):
        self.path = path

    def resolve_template(self, pdb, run_dir, *, fetch=None):
        return self.path


class FakeSymmetryDetector:
    def __init__(self, detection=None, error=None):
        self.detection = detection
        self.error = error
        self.calls = []

    def detect_symmetry(self, pdb_str, run_dir, *, ananas_bin=None, run_cmd=None):
        self.calls.append((pdb_str, ananas_bin))
        if self.error is not None:
            raise self.error
        return self.detection


class FakeContigNormaliser:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def normalise_contigs(self, spec, mode, parsed_pdb, copies):
        self.calls.append((mode, parsed_pdb, copies))
        return self.result


class FakeInferenceExecutor:
    def __init__(self, exit_code=0, stderr_tail=""):
        self.exit_code = exit_code
        self.stderr_tail = stderr_tail
        self.calls = []

    def run_inference(self, argv, total_steps, num_designs, dump_dir, on_step, **kwargs):
        self.calls.append({"argv": argv, "total_steps": total_steps, "num_designs": num_designs})
        # The real InferenceExecutor only calls on_step with a path to a dump file that already
        # exists and ends in "TER" -- FramePublisher.maybe_publish reads it immediately.
        dump_dir.mkdir(parents=True, exist_ok=True)
        frame_path = dump_dir / "0.pdb"
        frame_path.write_text("ATOM ...\nTER")
        on_step(0, 0, frame_path)
        return InferenceResult(exit_code=self.exit_code, stderr_tail=self.stderr_tail)


class FakePdbPostProcessor:
    def __init__(self):
        self.calls = []

    def fix_outputs(self, run_dir, name, num_designs, contigs):
        self.calls.append((name, num_designs, contigs))


class FakeValidationExecutor:
    def __init__(self, exit_code=0, stderr_tail=""):
        self.exit_code = exit_code
        self.stderr_tail = stderr_tail
        self.calls = []

    def run_validation(self, run_dir, name, normalised_contigs, copies, request, **kwargs):
        self.calls.append((name, normalised_contigs, copies))
        return InferenceResult(exit_code=self.exit_code, stderr_tail=self.stderr_tail)


class FakeResultPackager:
    def __init__(self):
        self.stage_out_calls = []
        self.package_calls = []

    def stage_out(self, tmpdir, run_dir):
        self.stage_out_calls.append((tmpdir, run_dir))

    def package_results(self, run_dir, name):
        self.package_calls.append((run_dir, name))
        return run_dir / f"{name}.result.zip"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(tmp_path):
    return RunnerConfig.from_env(
        env={
            "RFD_FORK": str(tmp_path / "fork"),
            "RFD_MODELS": str(tmp_path / "fork" / "models"),
            "RFD_AF_PARAMS": str(tmp_path / "af"),
            "ANANAS_BIN": str(tmp_path / "no-ananas"),
        }
    )


def _make_record(tmp_path, **request_overrides):
    defaults = dict(
        name="design",
        contigs="40",
        partition="gpu",
        walltime="0-01:00:00",
        symmetry=SymmetryKind.NONE,
        num_designs=1,
    )
    defaults.update(request_overrides)
    request = DesignRequest(**defaults)
    record = RunRecord(
        run_id="run-1",
        name=request.name,
        run_dir=str(tmp_path),
        created_at=datetime.now(timezone.utc),
        request=request,
    )
    record.save(tmp_path)
    return record


def _base_deps(tmp_path, **overrides):
    kwargs = dict(
        dump_dir=tmp_path / "scratch",
        config=_make_config(tmp_path),
        template_resolver=FakeTemplateResolver(tmp_path / "template.pdb"),
        symmetry_detector=FakeSymmetryDetector(),
        contig_normaliser=FakeContigNormaliser(["40-40"]),
        inference_executor=FakeInferenceExecutor(),
        pdb_postprocessor=FakePdbPostProcessor(),
        validation_executor=FakeValidationExecutor(),
        result_packager=FakeResultPackager(),
    )
    kwargs.update(overrides)
    return OrchestratorDeps(**kwargs)


@pytest.fixture(autouse=True)
def _fake_colabdesign_bridge(monkeypatch):
    monkeypatch.setattr(_colabdesign, "pdb_to_string", lambda pdb, chains=None: "PDBSTR")
    monkeypatch.setattr(_colabdesign, "parse_pdb", lambda path: "PARSED")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_free_mode_stage_all_happy_path(tmp_path):
    _make_record(tmp_path, contigs="40", symmetry=SymmetryKind.NONE)
    deps = _base_deps(tmp_path)

    rc = main(tmp_path, stage=Stage.ALL, deps=deps)

    assert rc == 0
    final = RunRecord.load(tmp_path)
    assert final.backbone_state == StageState.COMPLETED
    assert final.validate_state == StageState.COMPLETED
    assert final.normalised_contigs == ["40-40"]
    assert final.copies == 1
    assert deps.inference_executor.calls
    assert deps.validation_executor.calls
    # business-logic-model.md section 2 step 7: required before run_inference.py is invoked.
    assert (deps.dump_dir / "schedules").is_dir()
    # step 9: PdbPostProcessor.fix_outputs is called with the final normalised contigs.
    assert deps.pdb_postprocessor.calls == [("design", 1, ["40-40"])]
    # step 10: RunOutputs populated on the backbone side.
    assert final.outputs.backbone_pdbs == ["design_0.pdb"]
    assert final.outputs.trajectory_pdbs == [
        "traj/design_0_pX0_traj.pdb",
        "traj/design_0_Xt-1_traj.pdb",
    ]
    # step 14/15: ResultPackager.package_results called, result_zip populated.
    assert deps.result_packager.package_calls == [(tmp_path, "design")]
    assert final.outputs.result_zip == "design.result.zip"
    assert final.outputs.best_pdb == "design/best.pdb"


def test_fixed_mode_with_template(tmp_path):
    _make_record(tmp_path, contigs="A1-10/20-20", pdb="1abc", symmetry=SymmetryKind.NONE)
    deps = _base_deps(tmp_path)

    rc = main(tmp_path, stage=Stage.ALL, deps=deps)

    assert rc == 0
    final = RunRecord.load(tmp_path)
    assert final.mode == "fixed"
    assert final.backbone_state == StageState.COMPLETED
    assert (tmp_path / "input.pdb").exists()


def test_partial_mode(tmp_path):
    _make_record(tmp_path, contigs="A1-10", pdb="1abc", symmetry=SymmetryKind.NONE)
    deps = _base_deps(tmp_path)

    rc = main(tmp_path, stage=Stage.ALL, deps=deps)

    assert rc == 0
    final = RunRecord.load(tmp_path)
    assert final.mode == "partial"


def test_symmetry_auto_with_ananas_present_folds_back_detected_group(tmp_path):
    _make_record(tmp_path, contigs="A1-10", pdb="1abc", symmetry=SymmetryKind.AUTO)
    detection = SymmetryDetection(group="c3", rmsd=0.2, asymmetric_unit_pdb_str="AU_PDB")
    deps = _base_deps(tmp_path, symmetry_detector=FakeSymmetryDetector(detection=detection))

    rc = main(tmp_path, stage=Stage.ALL, deps=deps)

    assert rc == 0
    final = RunRecord.load(tmp_path)
    assert final.copies == 3
    assert final.backbone_state == StageState.COMPLETED


def test_symmetry_auto_with_ananas_present_but_finds_nothing_continues_unsymmetric(tmp_path):
    # business-rules.md section 1: "AnAnaS runs but detects nothing" is NOT a failure -- the
    # symmetry_plan reverts to none and the run continues, matching the notebook.
    _make_record(tmp_path, contigs="A1-10", pdb="1abc", symmetry=SymmetryKind.AUTO)
    deps = _base_deps(tmp_path, symmetry_detector=FakeSymmetryDetector(detection=None))

    rc = main(tmp_path, stage=Stage.ALL, deps=deps)

    assert rc == 0
    final = RunRecord.load(tmp_path)
    assert final.copies == 1
    assert final.backbone_state == StageState.COMPLETED
    assert deps.inference_executor.calls


def test_symmetry_auto_detects_unsupported_group_fails_with_rfd_core_error(tmp_path):
    # business-rules.md section 1: an unsupported detected group (not c*/d*) fails with rfd-core's
    # own SymmetryError message, verbatim -- and must not be conflated with "found nothing".
    _make_record(tmp_path, contigs="A1-10", pdb="1abc", symmetry=SymmetryKind.AUTO)
    detection = SymmetryDetection(group="s5", rmsd=0.1, asymmetric_unit_pdb_str="AU")
    deps = _base_deps(tmp_path, symmetry_detector=FakeSymmetryDetector(detection=detection))

    rc = main(tmp_path, stage=Stage.ALL, deps=deps)

    assert rc == 1
    final = RunRecord.load(tmp_path)
    assert final.backbone_state == StageState.FAILED
    assert "not supported" in final.error
    assert deps.inference_executor.calls == []


def test_symmetry_auto_with_ananas_absent_fails_fast_without_running_inference(tmp_path):
    _make_record(tmp_path, contigs="A1-10", pdb="1abc", symmetry=SymmetryKind.AUTO)
    deps = _base_deps(
        tmp_path,
        symmetry_detector=FakeSymmetryDetector(
            error=AnanasUnavailableError(str(tmp_path / "no-ananas"))
        ),
    )

    rc = main(tmp_path, stage=Stage.ALL, deps=deps)

    assert rc == 1
    final = RunRecord.load(tmp_path)
    assert final.backbone_state == StageState.FAILED
    assert "auto" in final.error
    # The whole point of the fail-fast rule: the fake InferenceExecutor must never be invoked.
    assert deps.inference_executor.calls == []


def test_stage_backbone_leaves_validate_state_skipped(tmp_path):
    _make_record(tmp_path, contigs="40")
    deps = _base_deps(tmp_path)

    rc = main(tmp_path, stage=Stage.BACKBONE, deps=deps)

    assert rc == 0
    final = RunRecord.load(tmp_path)
    assert final.backbone_state == StageState.COMPLETED
    assert final.validate_state == StageState.SKIPPED
    assert deps.validation_executor.calls == []


def test_stage_validate_without_completed_backbone_rejects_immediately(tmp_path):
    record = _make_record(tmp_path, contigs="40")
    assert record.backbone_state == StageState.PENDING
    deps = _base_deps(tmp_path)

    rc = main(tmp_path, stage=Stage.VALIDATE, deps=deps)

    assert rc == 1
    final = RunRecord.load(tmp_path)
    # Untouched -- rejected before mutating RunRecord or touching Slurm/GPU state.
    assert final.backbone_state == StageState.PENDING
    assert final.validate_state == StageState.PENDING
    assert deps.inference_executor.calls == []
    assert deps.validation_executor.calls == []


def test_failing_backbone_step_leaves_validate_state_pending(tmp_path):
    _make_record(tmp_path, contigs="40")
    deps = _base_deps(
        tmp_path, inference_executor=FakeInferenceExecutor(exit_code=1, stderr_tail="boom")
    )

    rc = main(tmp_path, stage=Stage.ALL, deps=deps)

    assert rc == 1
    final = RunRecord.load(tmp_path)
    assert final.backbone_state == StageState.FAILED
    assert final.error == "boom"
    assert final.validate_state == StageState.PENDING
    assert deps.validation_executor.calls == []


def test_sigterm_during_backbone_writes_failed_state_with_exact_message(tmp_path):
    _make_record(tmp_path, contigs="40")

    def killing_run_inference(argv, total_steps, num_designs, dump_dir, on_step, **kwargs):
        os.kill(os.getpid(), signal.SIGTERM)
        raise AssertionError("SIGTERM was not delivered before run_inference returned")

    deps = _base_deps(
        tmp_path, inference_executor=SimpleNamespace(run_inference=killing_run_inference)
    )

    with pytest.raises(SystemExit) as exc_info:
        main(tmp_path, stage=Stage.ALL, deps=deps)
    assert exc_info.value.code == 1

    final = RunRecord.load(tmp_path)
    assert final.backbone_state == StageState.FAILED
    assert final.error == "terminated (SIGTERM) — likely walltime exceeded"


def test_sigterm_during_validate_writes_failed_validate_state(tmp_path):
    _make_record(tmp_path, contigs="40")
    deps = _base_deps(tmp_path)
    assert main(tmp_path, stage=Stage.BACKBONE, deps=deps) == 0

    def killing_run_validation(run_dir, name, normalised_contigs, copies, request, **kwargs):
        os.kill(os.getpid(), signal.SIGTERM)
        raise AssertionError("SIGTERM was not delivered before run_validation returned")

    deps2 = _base_deps(
        tmp_path, validation_executor=SimpleNamespace(run_validation=killing_run_validation)
    )

    with pytest.raises(SystemExit) as exc_info:
        main(tmp_path, stage=Stage.VALIDATE, deps=deps2)
    assert exc_info.value.code == 1

    final = RunRecord.load(tmp_path)
    assert final.validate_state == StageState.FAILED
    assert final.error == "terminated (SIGTERM) — likely walltime exceeded"


def test_sigterm_handler_swallows_a_failed_final_save(tmp_path, monkeypatch):
    _make_record(tmp_path, contigs="40")

    save_calls = {"n": 0}
    orig_save = RunRecord.save

    def flaky_save(self, run_dir):
        save_calls["n"] += 1
        if save_calls["n"] >= 2:  # let the first (RUNNING) save through; fail the sigterm one
            raise OSError("disk full")
        return orig_save(self, run_dir)

    monkeypatch.setattr(RunRecord, "save", flaky_save)

    def killing_run_inference(argv, total_steps, num_designs, dump_dir, on_step, **kwargs):
        os.kill(os.getpid(), signal.SIGTERM)
        raise AssertionError("SIGTERM was not delivered before run_inference returned")

    deps = _base_deps(
        tmp_path, inference_executor=SimpleNamespace(run_inference=killing_run_inference)
    )

    # The handler's own record.save() failing must not turn into an unhandled OSError --
    # sys.exit(1) must still be what propagates.
    with pytest.raises(SystemExit) as exc_info:
        main(tmp_path, stage=Stage.ALL, deps=deps)
    assert exc_info.value.code == 1


def test_template_fetch_failure_marks_backbone_failed_before_inference(tmp_path):
    _make_record(tmp_path, contigs="A1-10/20-20", pdb="1abc", symmetry=SymmetryKind.NONE)

    class FailingTemplateResolver:
        def resolve_template(self, pdb, run_dir, *, fetch=None):
            raise OSError("network unreachable")

    deps = _base_deps(tmp_path, template_resolver=FailingTemplateResolver())

    rc = main(tmp_path, stage=Stage.ALL, deps=deps)

    assert rc == 1
    final = RunRecord.load(tmp_path)
    assert final.backbone_state == StageState.FAILED
    assert "network unreachable" in final.error
    assert deps.inference_executor.calls == []


def test_sigterm_terminates_the_actual_tracked_subprocess(tmp_path, monkeypatch):
    # Unlike the other SIGTERM tests, this one uses the REAL InferenceExecutor (not a fake) so
    # that orchestrator's tracker.factory(subprocess.Popen) wiring -- which forwards SIGTERM to
    # whatever real child process is currently tracked -- is actually exercised, not bypassed.
    import rfd_runner.inference_executor as ie_module
    import rfd_runner.orchestrator as orch_module

    _make_record(tmp_path, contigs="40")

    class NeverExitingProc:
        def __init__(self, *args, **kwargs):
            self.terminated = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            return None

        def communicate(self):
            return (None, "")

    spawned = []

    def fake_popen(*args, **kwargs):
        proc = NeverExitingProc()
        spawned.append(proc)
        return proc

    monkeypatch.setattr(orch_module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(ie_module.time, "sleep", lambda seconds: os.kill(os.getpid(), signal.SIGTERM))

    deps = _base_deps(tmp_path, inference_executor=InferenceExecutor())

    with pytest.raises(SystemExit) as exc_info:
        main(tmp_path, stage=Stage.ALL, deps=deps)
    assert exc_info.value.code == 1

    assert len(spawned) == 1
    assert spawned[0].terminated is True
    final = RunRecord.load(tmp_path)
    assert final.backbone_state == StageState.FAILED
    assert final.error == "terminated (SIGTERM) — likely walltime exceeded"


def test_proc_tracker_records_the_process_created_by_the_wrapped_factory():
    from rfd_runner.orchestrator import _ProcTracker

    tracker = _ProcTracker()
    created = object()
    calls = []

    def base_factory(*args, **kwargs):
        calls.append((args, kwargs))
        return created

    wrapped = tracker.factory(base_factory)
    result = wrapped("argv", stdout="PIPE")

    assert result is created
    assert tracker.current is created
    assert calls == [(("argv",), {"stdout": "PIPE"})]


def test_failing_validation_leaves_backbone_completed(tmp_path):
    _make_record(tmp_path, contigs="40")
    deps = _base_deps(
        tmp_path, validation_executor=FakeValidationExecutor(exit_code=2, stderr_tail="af failed")
    )

    rc = main(tmp_path, stage=Stage.ALL, deps=deps)

    assert rc == 1
    final = RunRecord.load(tmp_path)
    assert final.backbone_state == StageState.COMPLETED
    assert final.validate_state == StageState.FAILED
    assert final.error == "af failed"


def test_stage_validate_resumes_from_saved_record(tmp_path):
    _make_record(tmp_path, contigs="40")
    deps = _base_deps(tmp_path)
    assert main(tmp_path, stage=Stage.BACKBONE, deps=deps) == 0

    # Fresh process invocation, fresh deps -- reads normalised_contigs/copies from the saved
    # RunRecord rather than from memory (FR-11 retry path).
    deps2 = _base_deps(tmp_path)
    rc = main(tmp_path, stage=Stage.VALIDATE, deps=deps2)

    assert rc == 0
    final = RunRecord.load(tmp_path)
    assert final.validate_state == StageState.COMPLETED
    assert deps2.validation_executor.calls[0][1] == ["40-40"]
