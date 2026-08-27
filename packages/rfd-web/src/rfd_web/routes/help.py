from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.get("/help/contigs", response_class=HTMLResponse)
def get_contigs_help(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "contig_help.html")
