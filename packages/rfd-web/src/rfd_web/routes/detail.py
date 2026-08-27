from __future__ import annotations

import dataclasses
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse

router = APIRouter()

@router.get("/runs/{id}")
def get_run_detail(id: str, request: Request):
    service = request.app.state.query_service
    result_service = request.app.state.result_service
    reader = request.app.state.reader
    layout = request.app.state.layout
    
    run = service.get(id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
        
    accept = request.headers.get("accept", "")
    if "application/json" in accept:
        return JSONResponse(dataclasses.asdict(run))
        
    run_dir = layout.run_dir(id)
    error_logs = reader.log_tail(run_dir, lines=100) if run_dir.exists() else ""
    
    results_files = []
    if run_dir.exists():
        for p in sorted(run_dir.rglob("*")):
            if p.is_file() and not p.name.startswith("."):
                results_files.append(p.relative_to(run_dir).as_posix())

    has_zip = result_service.get_result_zip(id) is not None
    has_structure = result_service.get_structure(id, 0) is not None

    context = {
        "run": run,
        "error_logs": error_logs,
        "results_files": results_files,
        "has_zip": has_zip,
        "has_structure": has_structure,
    }
        
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "run_detail.html", context)

@router.get("/runs/{id}/status", response_class=HTMLResponse)
def get_run_status(id: str, request: Request):
    service = request.app.state.query_service
    run = service.get(id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
        
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "fragments/status.html", {"run": run})

@router.get("/runs/{id}/frame")
def get_run_frame(id: str, request: Request):
    service = request.app.state.result_service
    path = service.get_file(id, "current_frame.pdb")
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="Frame not found")
    return FileResponse(path, media_type="text/plain")

@router.post("/runs/{id}/cancel")
def cancel_run(id: str, request: Request):
    service = request.app.state.submission_service
    service.cancel(id)
    return RedirectResponse(url=f"/runs/{id}", status_code=303)

@router.post("/runs/{id}/clone")
def clone_run(id: str, request: Request):
    service = request.app.state.query_service
    run = service.get(id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return RedirectResponse(url=f"/runs/new?clone_from={id}", status_code=303)
