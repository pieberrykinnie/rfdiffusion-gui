from rfd_core import ProgressState

from rfd_runner.progress_reporter import ProgressReporter


def test_update_step_round_trips_through_rfd_core(tmp_path):
    reporter = ProgressReporter(tmp_path, total_designs=3)
    reporter.update_step("backbone", 1, 5, 50)

    loaded = ProgressState.load(tmp_path)
    assert loaded is not None
    assert loaded.stage == "backbone"
    assert loaded.design_index == 1
    assert loaded.total_designs == 3
    assert loaded.step == 5
    assert loaded.total_steps == 50
    assert loaded.frame_path is None


def test_set_frame_updates_frame_path_and_preserves_other_fields(tmp_path):
    reporter = ProgressReporter(tmp_path, total_designs=1)
    reporter.update_step("backbone", 0, 2, 10)
    reporter.set_frame(tmp_path / "current_frame.pdb")

    loaded = ProgressState.load(tmp_path)
    assert loaded.frame_path == str(tmp_path / "current_frame.pdb")
    assert loaded.step == 2
    assert loaded.total_steps == 10


def test_set_stage_updates_stage_and_preserves_step(tmp_path):
    reporter = ProgressReporter(tmp_path, total_designs=1)
    reporter.update_step("backbone", 0, 3, 10)
    reporter.set_stage("validate")

    loaded = ProgressState.load(tmp_path)
    assert loaded.stage == "validate"
    assert loaded.step == 3
