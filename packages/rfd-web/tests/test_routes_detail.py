from __future__ import annotations

import pytest
from httpx import AsyncClient
from rfd_core import StageState

@pytest.mark.asyncio
async def test_get_run_detail(client: AsyncClient, written_record):
    written_record(run_id="run_123")
    response = await client.get("/runs/run_123")
    assert response.status_code == 200
    assert "run_123" in response.text
    
@pytest.mark.asyncio
async def test_get_run_status(client: AsyncClient, written_record):
    written_record(run_id="run_123", backbone_state=StageState.RUNNING)
    response = await client.get("/runs/run_123/status")
    assert response.status_code == 200
    assert "queued" in response.text.lower()
    
@pytest.mark.asyncio
async def test_get_run_frame(client: AsyncClient, written_record, layout):
    written_record(run_id="run_123")
    run_dir = layout.run_dir("run_123")
    (run_dir / "current_frame.pdb").write_text("ATOM ...")
    response = await client.get("/runs/run_123/frame")
    assert response.status_code == 200
    assert "ATOM" in response.text

@pytest.mark.asyncio
async def test_cancel_run(client: AsyncClient, written_record):
    written_record(run_id="run_123", backbone_state=StageState.RUNNING)
    response = await client.post("/runs/run_123/cancel")
    # Redirects back to detail or returns fragment
    assert response.status_code in (200, 302, 303)

@pytest.mark.asyncio
async def test_clone_run(client: AsyncClient, written_record):
    written_record(run_id="run_123")
    response = await client.post("/runs/run_123/clone")
    # Redirects to /new with pre-filled state
    assert response.status_code in (302, 303)
    assert "/new" in response.headers.get("location", "")
