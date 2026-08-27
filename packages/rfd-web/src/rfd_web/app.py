from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional, Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from rfd_web.config import WebConfig
from rfd_web.slurm.adapter import SlurmAdapter
from rfd_core.paths import PathLayout
from rfd_web.persistence.reconcile import RunIndexReconciler
from rfd_web.persistence.reader import RunDirectoryReader
from rfd_web.persistence.repository import RunRepository
from rfd_web.services.query import RunQueryService
from rfd_web.services.submission import SubmissionService
from rfd_web.services.result import ResultService
from rfd_web.slurm.partitions import PartitionCache

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up RFdiffusion Web UI")
    layout: PathLayout = app.state.layout
    repository: RunRepository = app.state.repository
    
    # Reconcile index
    reconciler = RunIndexReconciler(layout, repository)
    reconciler.reconcile_all()
    
    # Initialize PartitionCache
    if app.state.slurm:
        app.state.partition_cache.get(force=True)
    
    yield
    logger.info("Shutting down RFdiffusion Web UI")


def create_app(
    config: Optional[WebConfig] = None,
    slurm: Optional[SlurmAdapter] = None,
    layout: Optional[PathLayout] = None,
) -> FastAPI:
    if config is None:
        config = WebConfig()
    if slurm is None:
        import shutil
        from rfd_web.slurm.adapter import CliSlurmAdapter
        from rfd_web.slurm.fake import FakeSlurmAdapter
        if shutil.which("sinfo"):
            slurm = CliSlurmAdapter()
        else:
            slurm = FakeSlurmAdapter()
    if layout is None:
        layout = PathLayout.from_env()

    app = FastAPI(lifespan=lifespan)
    
    import pathlib
    base_dir = pathlib.Path(__file__).parent
    
    # Mount static files
    app.mount("/static", StaticFiles(directory=base_dir / "static"), name="static")
    
    # Setup Jinja2 templates
    templates = Jinja2Templates(directory=base_dir / "templates")
    
    # Setup services
    reader = RunDirectoryReader(config.log_tail_lines)
    repository = RunRepository(layout.database_path)
    partition_cache = PartitionCache(slurm, config)
    from rfd_web.slurm.script import JobScriptGenerator
    generator = JobScriptGenerator(layout, config)
    query_service = RunQueryService(layout, config, slurm, repository, reader)
    submission_service = SubmissionService(layout, config, slurm, repository, generator, reader)
    result_service = ResultService(layout, reader)
    
    # Register routers
    from rfd_web.routes.runs import runs_router
    from rfd_web.routes.submit import submit_router
    from rfd_web.routes.detail import router as detail_router
    from rfd_web.routes.files import router as files_router
    from rfd_web.routes.help import router as help_router

    app.include_router(runs_router)
    app.include_router(submit_router)
    app.include_router(detail_router)
    app.include_router(files_router)
    app.include_router(help_router)
    
    # Attach to app.state
    app.state.config = config
    app.state.slurm = slurm
    app.state.layout = layout
    app.state.repository = repository
    app.state.query_service = query_service
    app.state.submission_service = submission_service
    app.state.result_service = result_service
    app.state.partition_cache = partition_cache
    app.state.reader = reader
    app.state.templates = templates
    
    return app
