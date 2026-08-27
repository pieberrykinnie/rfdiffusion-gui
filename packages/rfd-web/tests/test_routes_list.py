from __future__ import annotations

import pytest
from httpx import AsyncClient
from rfd_core import StageState
from rfd_web.services.query import RunStatus

@pytest.mark.asyncio
async def test_get_run_list_empty(client: AsyncClient):
    response = await client.get("/")
    assert response.status_code == 200
    assert "No runs found" in response.text or "recent designs" in response.text.lower()
    
@pytest.mark.asyncio
async def test_get_run_list_with_records(client: AsyncClient, written_record, app):
    record1 = written_record(run_id="run_one", backbone_state=StageState.PENDING)
    record2 = written_record(run_id="run_two", backbone_state=StageState.COMPLETED)
    
    app.state.query_service.repository.upsert_from_record(record1, RunStatus.QUEUED)
    app.state.query_service.repository.upsert_from_record(record2, RunStatus.COMPLETED)
    
    response = await client.get("/")
    assert response.status_code == 200
    assert "run_one" in response.text
    assert "run_two" in response.text
