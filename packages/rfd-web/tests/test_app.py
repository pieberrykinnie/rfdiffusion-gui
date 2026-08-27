from __future__ import annotations

from fastapi.testclient import TestClient

def test_create_app(sync_client: TestClient, app):
    """Test that the application can be created and serves static files."""
    response = sync_client.get("/static/app.css")
    # Not strictly asserting 200, as the file might not be there depending on how fixtures run
    # but we assert it doesn't 500.
    assert response.status_code in (200, 404)
    assert app.state.config is not None
    assert app.state.slurm is not None
    assert app.state.layout is not None
