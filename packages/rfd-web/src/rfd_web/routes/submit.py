from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional

from starlette.datastructures import UploadFile
from fastapi import APIRouter, Request, Form, Response, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from rfd_core import preview_mode, validate
from ..upload import save_upload
from ..validation import parse_form_to_request

submit_router = APIRouter()

@submit_router.get("/new", response_class=HTMLResponse)
@submit_router.get("/runs/new", response_class=HTMLResponse)
async def new_run_form(request: Request, clone_from: Optional[str] = None) -> Any:
    config = request.app.state.config
    templates = request.app.state.templates
    partition_cache = request.app.state.partition_cache
    query_service = request.app.state.query_service
    
    partitions = partition_cache.get()
    
    ananas_available = shutil.which("ananas") is not None
    
    context: dict[str, Any] = {
        "config": config,
        "partitions": partitions,
        "ananas_available": ananas_available,
        "clone_source": None
    }
    
    if clone_from:
        run_view = query_service.get(clone_from)
        if run_view:
            context["clone_source"] = run_view
            
    return templates.TemplateResponse(request, "new_run.html", context)


@submit_router.post("/api/preview-mode", response_class=HTMLResponse)
async def api_preview_mode(request: Request, contigs: str = Form("")) -> Any:
    mode = preview_mode(contigs)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "fragments/mode_preview.html",
        {"mode": mode}
    )


@submit_router.post("/runs")
async def submit_run(request: Request, response: Response) -> Any:
    config = request.app.state.config
    templates = request.app.state.templates
    submission_service = request.app.state.submission_service
    partition_cache = request.app.state.partition_cache
    
    form_data = await request.form()
    
    # ananas availability check for re-rendering
    ananas_available = shutil.which("ananas") is not None
    
    # 1. Parse form
    try:
        design_request = parse_form_to_request(dict(form_data), config)
    except Exception as e:
        response.status_code = 422
        return templates.TemplateResponse(
            request,
            "new_run.html",
            {
                "errors": [str(e)],
                "config": config,
                "partitions": partition_cache.get(),
                "ananas_available": ananas_available,
            },
            status_code=422,
        )
        
    # 2. Handle template file upload if provided
    template_file = form_data.get("pdb_file") or form_data.get("template_file")
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        template_path = None
        if hasattr(template_file, "filename") and template_file.filename:
            try:
                template_path = await save_upload(template_file, Path(tmp_dir))
                design_request.pdb = "input_template.pdb"
            except HTTPException as e:
                response.status_code = 422
                return templates.TemplateResponse(
                    request,
                    "new_run.html",
                    {
                        "errors": [e.detail],
                        "config": config,
                        "partitions": partition_cache.get(),
                        "ananas_available": ananas_available,
                    },
                    status_code=422,
                )
        
        # 3. Validate request
        validation_outcome = validate(design_request)
        
        if not validation_outcome.ok:
            response.status_code = 422
            return templates.TemplateResponse(
                request,
                "new_run.html",
                {
                    "errors": validation_outcome.errors,
                    "config": config,
                    "partitions": partition_cache.get(),
                    "ananas_available": ananas_available,
                },
                status_code=422,
            )
            
        # 4. Submit
        outcome = submission_service.submit(design_request, template_path)
        
        if not outcome.ok:
            response.status_code = 422
            return templates.TemplateResponse(
                request,
                "new_run.html",
                {
                    "errors": outcome.errors,
                    "config": config,
                    "partitions": partition_cache.get(),
                    "ananas_available": ananas_available,
                },
                status_code=422,
            )
            
        # 5. Redirect to GET /runs/{id}
        return RedirectResponse(
            url=f"/runs/{outcome.run_id}",
            status_code=303
        )
