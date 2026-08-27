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
