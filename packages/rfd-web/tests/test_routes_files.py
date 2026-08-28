from __future__ import annotations

import pytest
from httpx import AsyncClient
from rfd_core import StageState

@pytest.mark.asyncio
async def test_get_file_path_containment(client: AsyncClient, written_record):
    written_record(run_id="run_123")
    # Trying to escape run directory
    response = await client.get("/runs/run_123/file/../secrets.txt")
    assert response.status_code in (400, 403, 404, 422)

@pytest.mark.asyncio
async def test_get_structure(client: AsyncClient, written_record, layout):
    record = written_record(run_id="run_123", backbone_state=StageState.COMPLETED)
    run_dir = layout.run_dir("run_123")
    pdb = run_dir / "design_0.pdb"
    pdb.write_text("ATOM  ...")
    
    response = await client.get("/runs/run_123/structure/0")
    assert response.status_code == 200
    assert response.text == "ATOM  ..."

@pytest.mark.asyncio
async def test_get_trajectory(client: AsyncClient, written_record, layout):
    record = written_record(run_id="run_123", backbone_state=StageState.COMPLETED)
    run_dir = layout.run_dir("run_123")
    trj = run_dir / "trajectory_0.pdb"
    trj.write_text("MODEL  ...")
    
    response = await client.get("/runs/run_123/trajectory/0")
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_download_all(client: AsyncClient, written_record, layout):
    written_record(run_id="run_123", backbone_state=StageState.COMPLETED)
    run_dir = layout.run_dir("run_123")
    (run_dir / "run_123_results.zip").write_text("PK\x03\x04")
    response = await client.get("/runs/run_123/download")
    assert response.status_code == 200
    assert response.headers["content-type"] in ("application/zip", "application/x-zip-compressed")

@pytest.mark.asyncio
async def test_get_best_overlay(client: AsyncClient, written_record, layout):
    written_record(run_id="run_123", backbone_state=StageState.COMPLETED, validate_state=StageState.COMPLETED)
    run_dir = layout.run_dir("run_123")
    (run_dir / "smoke_0.pdb").write_text("ATOM 1 CA ALA 1")
    sub = run_dir / "smoke"
    sub.mkdir()
    (sub / "best.pdb").write_text("REMARK 001 design 0 N 0 RMSD 0.75\nATOM 1 CA ALA 1")
    (sub / "best_design0.pdb").write_text("ATOM 1 CA ALA 1")

    response = await client.get("/runs/run_123/best")
    assert response.status_code == 200
    data = response.json()
    assert data["design_index"] == 0
    assert data["rmsd"] == 0.75
    assert "ATOM" in data["design_pdb"]
    assert "ATOM" in data["af_pdb"]

@pytest.mark.asyncio
async def test_get_best_overlay_not_found(client: AsyncClient, written_record, layout):
    written_record(run_id="run_456", backbone_state=StageState.RUNNING)
    response = await client.get("/runs/run_456/best")
    assert response.status_code == 404

