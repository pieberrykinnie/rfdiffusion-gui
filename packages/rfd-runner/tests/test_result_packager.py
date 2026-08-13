import zipfile

import pytest

from rfd_runner.result_packager import ResultPackager


def test_stage_out_does_not_raise_when_invariant_holds(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    ResultPackager().stage_out(scratch, run_dir)  # must not raise


def test_stage_out_raises_when_final_output_leaked_into_scratch(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (scratch / "leaked.pdb").write_text("should not be here")

    with pytest.raises(AssertionError):
        ResultPackager().stage_out(scratch, run_dir)


def test_package_results_contains_exactly_name_and_traj_name_members(tmp_path):
    (tmp_path / "traj").mkdir()

    (tmp_path / "design_0.pdb").write_text("main 0")
    (tmp_path / "design_1.pdb").write_text("main 1")
    (tmp_path / "design").mkdir()
    (tmp_path / "design" / "best.pdb").write_text("best")  # not top-level, must NOT be included
    (tmp_path / "traj" / "design_0_pX0_traj.pdb").write_text("traj 0")
    (tmp_path / "traj" / "design_1_Xt-1_traj.pdb").write_text("traj 1")
    (tmp_path / "other_thing.pdb").write_text("unrelated")  # different name prefix

    zip_path = ResultPackager().package_results(tmp_path, "design")

    assert zip_path == tmp_path / "design.result.zip"
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())

    assert names == {
        "design_0.pdb",
        "design_1.pdb",
        "traj/design_0_pX0_traj.pdb",
        "traj/design_1_Xt-1_traj.pdb",
    }
    assert "other_thing.pdb" not in names


def test_package_results_excludes_its_own_zip_on_rerun(tmp_path):
    (tmp_path / "traj").mkdir()
    (tmp_path / "design_0.pdb").write_text("main 0")

    ResultPackager().package_results(tmp_path, "design")
    zip_path = ResultPackager().package_results(tmp_path, "design")  # second run

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()

    assert "design.result.zip" not in names
