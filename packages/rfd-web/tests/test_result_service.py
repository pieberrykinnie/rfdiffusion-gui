from __future__ import annotations

import pytest
from rfd_web.services.result import ResultService
from rfd_web.persistence.reader import RunDirectoryReader

def test_result_service_get_structure(layout, written_record):
    written_record(run_id="run_123")
    
    run_dir = layout.run_dir("run_123")
    (run_dir / "design_0.pdb").write_text("ATOM")
    
    reader = RunDirectoryReader()
    service = ResultService(layout, reader)
    
    struct_path = service.get_structure("run_123", 0)
    assert struct_path is not None
    assert struct_path.exists()
    
def test_result_service_get_result_zip(layout, written_record):
    written_record(run_id="run_123")
    run_dir = layout.run_dir("run_123")
    (run_dir / "run_123_results.zip").write_text("zipcontent")
    
    reader = RunDirectoryReader()
    service = ResultService(layout, reader)
    
    archive_path = service.get_result_zip("run_123")
    assert archive_path is not None
    assert archive_path.exists()

def test_result_service_get_trajectory(layout, written_record):
    written_record(run_id="run_123")
    run_dir = layout.run_dir("run_123")
    traj_dir = run_dir / "traj"
    traj_dir.mkdir(parents=True)
    (traj_dir / "smoke_0_pX0_traj.pdb").write_text("MODEL 1\nATOM\nENDMDL")
    (traj_dir / "smoke_1_pX0_traj.pdb").write_text("MODEL 1\nATOM\nENDMDL")
    
    reader = RunDirectoryReader()
    service = ResultService(layout, reader)
    
    traj0 = service.get_trajectory("run_123", 0)
    assert traj0 is not None
    assert "smoke_0_pX0_traj.pdb" in traj0.name

    traj1 = service.get_trajectory("run_123", 1)
    assert traj1 is not None
    assert "smoke_1_pX0_traj.pdb" in traj1.name

def test_result_service_get_best_overlay(layout, written_record):
    written_record(run_id="run_123")
    run_dir = layout.run_dir("run_123")
    (run_dir / "smoke_0.pdb").write_text("ATOM 1 CA ALA 1")
    (run_dir / "smoke_1.pdb").write_text("ATOM 1 CA GLY 1")
    
    sub = run_dir / "smoke"
    sub.mkdir()
    (sub / "best.pdb").write_text("REMARK 001 design 1 N 1 RMSD 0.82\nATOM 1 CA GLY 1")
    (sub / "best_design1.pdb").write_text("ATOM 1 CA GLY 1")
    
    reader = RunDirectoryReader()
    service = ResultService(layout, reader)
    
    overlay = service.get_best_overlay("run_123")
    assert overlay is not None
    assert overlay["design_index"] == 1
    assert overlay["rmsd"] == 0.82
    assert "ATOM" in overlay["design_pdb"]
    assert "ATOM" in overlay["af_pdb"]

