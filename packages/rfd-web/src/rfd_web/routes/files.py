from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter()

@router.get("/runs/{id}/structure/{n}")
def get_structure(id: str, n: int, request: Request):
    service = request.app.state.result_service
    path = service.get_structure(id, n)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="Structure not found")
    return FileResponse(path, media_type="text/plain")

@router.get("/runs/{id}/trajectory/{n}")
def get_trajectory(id: str, n: int, request: Request):
    service = request.app.state.result_service
    path = service.get_trajectory(id, n)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="Trajectory not found")
    return FileResponse(path, media_type="text/plain")

@router.get("/runs/{id}/best")
def get_best_overlay(id: str, request: Request):
    service = request.app.state.result_service
    data = service.get_best_overlay(id)
    if data is None:
        raise HTTPException(status_code=404, detail="Best overlay not found")
    return JSONResponse(data)

@router.get("/runs/{id}/download")
def download_results(id: str, request: Request):
    service = request.app.state.result_service
    path = service.get_result_zip(id)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="Result archive not found")
    return FileResponse(
        path,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{id}.result.zip"'}
    )

@router.get("/runs/{id}/file/{path:path}")
def get_run_file(id: str, path: str, request: Request):
    service = request.app.state.result_service
    file_path = service.get_file(id, path)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)
