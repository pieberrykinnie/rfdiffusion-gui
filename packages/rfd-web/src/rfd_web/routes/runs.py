from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

runs_router = APIRouter()

@runs_router.get("/", response_class=HTMLResponse)
async def list_runs(request: Request) -> Any:
    service = request.app.state.query_service
    runs = service.list_runs()
    
    sorted_runs = sorted(
        runs,
        key=lambda r: r.created_at.timestamp() if r.created_at else 0,
        reverse=True
    )
    
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "run_list.html",
        {"runs": sorted_runs}
    )
