from __future__ import annotations

import pytest
from httpx import AsyncClient
import io

@pytest.mark.asyncio
async def test_get_new_run(client: AsyncClient):
    response = await client.get("/new")
    assert response.status_code == 200
    assert "data-testid=" in response.text
    
@pytest.mark.asyncio
async def test_post_preview_mode(client: AsyncClient):
    response = await client.post("/api/preview-mode", data={"mode": "unconditional"})
    assert response.status_code == 200
    assert "Length" in response.text or "Contigs" in response.text
    
@pytest.mark.asyncio
async def test_post_runs_invalid(client: AsyncClient):
    response = await client.post("/runs", data={
        "mode": "unconditional",
        "contigs": "invalid_contig_string_here",
        "iterations": "50",
        "num_designs": "10",
        "partition": "gpu"
    })
    # Will likely return the form again with errors (so 400 or 200 with error)
    # The current implementation returns 200 with form fragment containing error
    assert response.status_code in (200, 422)

@pytest.mark.asyncio
async def test_post_runs_valid(client: AsyncClient):
    response = await client.post("/runs", data={
        "name": "test_run",
        "mode": "unconditional",
        "contigs": "10-20",
        "iterations": "50",
        "num_designs": "1",
        "partition": "gpu"
    })
    # We should get redirected to the detail page on success
    assert response.status_code in (302, 303)
    assert response.headers.get("location", "").startswith("/runs/")
