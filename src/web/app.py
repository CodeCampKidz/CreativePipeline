"""FastAPI application factory — assembles routes, middleware, and static mounts."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.service.core.logger import setup_logging
from src.shared.config import get_settings

from .routes import campaigns_router, jobs_router, pipeline_router, ui_router

__all__ = ["create_app"]


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI instance with all routes and middleware.
    """
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(
        title="Creative Automation Pipeline API",
        description="Generate social ad campaign creatives with GenAI",
        version="1.0.0",
        openapi_tags=[
            {
                "name": "UI & Health",
                "description": "HTML page, health check, and static content",
            },
            {
                "name": "Pipeline",
                "description": "Validate briefs and submit generation requests",
            },
            {
                "name": "Jobs",
                "description": "Poll job status, manage job-scoped versions, and regenerate",
            },
            {
                "name": "Campaigns",
                "description": "Browse, download, and delete campaigns persisted on disk",
            },
        ],
    )

    # CORS middleware
    origins = [o.strip() for o in settings.cors_origins.split(",")]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Static files and generated output
    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    output_dir = Path(settings.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/output", StaticFiles(directory=str(output_dir)), name="output")

    # Routes
    app.include_router(ui_router)
    app.include_router(pipeline_router)
    app.include_router(jobs_router)
    app.include_router(campaigns_router)

    return app


# Default app instance for uvicorn
app = create_app()
