from __future__ import annotations

import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_get_help_contigs(client: AsyncClient):
    response = await client.get("/help/contigs")
    assert response.status_code == 200
    assert "contig" in response.text.lower()
